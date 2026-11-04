"""Record actual purchase quantities and settle a plan's inventory once.

The ledger lives in Plan.settings so existing alpha databases need no destructive
schema reset. Stock changes are deltas against the current pantry, preserving
manual corrections made after a plan was generated.
"""
from sqlalchemy import select
from app.models import PantryItem
from app.services import grocery
from app.services.locking import lock_user


def state(plan):
    return (plan.settings or {}).get('inventory', {})


def closed(plan):
    return bool(plan and state(plan).get('settled'))


def write_state(plan, value):
    plan.settings = dict(plan.settings or {}, inventory=value)


def pantry(db, user_id):
    return list(db.scalars(select(PantryItem).where(PantryItem.user_id == user_id)))


def stock_dicts(rows):
    return [dict(name=p.name, quantity=p.quantity, unit=p.unit) for p in rows]


def shopping_items(db, plan):
    if not plan or plan.status != 'ok':
        return []
    if closed(plan):
        return state(plan).get('shopping_items', [])
    needed = grocery.build_list(m.as_dict() for m in plan.meals if m.status != 'skipped')
    return grocery.apply_pantry(needed, stock_dicts(pantry(db, plan.user_id)))


def purchases(plan):
    return {p['key']: p for p in state(plan).get('purchases', [])}


def checked_keys(plan, items):
    bought = purchases(plan)
    return {i['key'] for i in items if bought.get(i['key'], {}).get('quantity', 0) >= i['quantity']}


def record_purchase(db, plan, item, checked=True):
    lock_user(db, plan.user_id)
    db.refresh(plan)
    ledger = dict(state(plan))
    if ledger.get('settled'):
        raise ValueError('This plan is closed. Inventory has already been updated.')
    if 'opening_stock' not in ledger:
        ledger['opening_stock'] = stock_dicts(pantry(db, plan.user_id))
    bought = purchases(plan)
    if checked:
        # Capture the quantity at purchase time, not whatever a later swap needs.
        previous = bought.get(item['key'])
        if not previous or previous['quantity'] < item['quantity']:
            bought[item['key']] = {k: item[k] for k in ('key', 'name', 'unit', 'quantity', 'cost')}
    else:
        bought.pop(item['key'], None)
    ledger['purchases'] = list(bought.values())
    write_state(plan, ledger)


def confirm_all_purchases(db, plan):
    for item in shopping_items(db, plan):
        previous = purchases(plan).get(item['key'])
        # Never shrink an actual purchase after a swap removed a requirement.
        if not previous or previous['quantity'] < item['quantity']:
            record_purchase(db, plan, item)


def settle(db, plan):
    """Apply purchases minus consumed ingredients exactly once; return new leftovers.

    No check-offs means no confirmed purchases. Unknown-quantity pantry entries
    mean 'I have plenty' and remain unknown. Units are never implicitly converted.
    """
    lock_user(db, plan.user_id)
    db.refresh(plan)
    if closed(plan):
        return state(plan).get('leftovers', [])
    shopping_snapshot = shopping_items(db, plan)
    bought = purchases(plan)
    used = {i['key']: i for i in grocery.build_list(m.as_dict() for m in plan.meals if m.status == 'cooked')}
    rows = pantry(db, plan.user_id)
    changes, leftovers = [], []
    for key in sorted(set(bought) | set(used)):
        source = bought.get(key) or used[key]
        name, unit = source['name'], source['unit']
        same_food = [p for p in rows if grocery._same_food(p.name, name)]
        item = next((p for p in same_food if (p.unit or '').lower().strip() == unit.lower().strip()), None)
        if any(p.quantity is None for p in same_food):
            continue
        purchased = bought.get(key, {}).get('quantity', 0)
        consumed = used.get(key, {}).get('quantity', 0)
        before = item.quantity if item else 0
        after = round(max(0, before + purchased - consumed), 2)
        if not item and after > 0:
            # Pantry entries are keyed by name in the alpha. Keep different units
            # distinct instead of silently dropping purchased leftovers.
            item = PantryItem(user_id=plan.user_id, name=name, unit=unit, quantity=after)
            db.add(item)
            rows.append(item)
        elif item:
            item.quantity = after
        if after != before:
            changes.append(dict(name=name, unit=unit, before=before, after=after))
        extra = round(max(0, after - before), 2)
        if extra > 0:
            leftovers.append(dict(name=name, unit=unit, quantity=extra))
    write_state(plan, dict(state(plan), settled=True, changes=changes, leftovers=leftovers, shopping_items=shopping_snapshot))
    db.flush()
    return leftovers


def reopen(db, plan):
    """Reverse this plan's deltas against current stock, preserving manual edits."""
    lock_user(db,plan.user_id);db.refresh(plan)
    ledger=dict(state(plan))
    if not ledger.get('settled'):return
    rows=pantry(db,plan.user_id)
    adjustments=[]
    for change in ledger.get('changes',[]):
        item=next((p for p in rows if p.name==change['name'] and p.unit==change['unit']),None)
        if item is None or item.quantity is None:
            raise ValueError('Pantry entries changed since check-in. Restore those entries before undoing it.')
        new=round(item.quantity-(change['after']-change['before']),2)
        if new<0:
            raise ValueError('Some of these leftovers have already been used. Undo cannot remove more stock than you have.')
        adjustments.append((item,new))
    for item,new in adjustments:item.quantity=new
    ledger['settled']=False
    ledger['reopen_count']=ledger.get('reopen_count',0)+1
    for key in ('changes','leftovers','shopping_items'):ledger.pop(key,None)
    write_state(plan,ledger)
