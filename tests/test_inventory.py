import pytest
from app.models import Meal, PantryItem, Plan, Profile
from app.services import grocery, inventory
from tests.helpers import signup


@pytest.fixture
def planned(client):
    signup(client)
    client.post('/survey', data={'budget': '150'})
    client.post('/plan/generate')
    return client


def data(client):
    with client.app.state.session_factory() as s:
        p = s.query(Plan).order_by(Plan.id.desc()).first()
        return p, list(p.meals)


def quantities(client):
    with client.app.state.session_factory() as s:
        return {(p.name, p.unit): p.quantity for p in s.query(PantryItem)}


def test_uncooked_stock_is_not_added_twice(planned):
    p, ms = data(planned)
    item = grocery.build_list(m.as_dict() for m in ms)[0]
    amount = item['quantity'] + 10
    planned.post('/pantry/add', data={'name': item['name'], 'quantity': amount, 'unit': item['unit']})
    assert f'data-item="{item["name"]}"' not in planned.get('/grocery').text
    planned.post('/checkin', data={'bought_all': 'true'})
    assert quantities(planned)[(item['name'], item['unit'])] == amount
    planned.post('/checkin', data={'bought_all': 'true'})
    assert quantities(planned)[(item['name'], item['unit'])] == amount


def test_no_checkoffs_does_not_invent_purchases(planned):
    planned.post('/checkin', data={})
    assert quantities(planned) == {}


def test_cooked_ingredients_are_debited_once(planned):
    _, ms = data(planned)
    meal = ms[0]
    ing = meal.ingredients[0]
    planned.post('/pantry/add', data={'name': ing['name'], 'quantity': 100, 'unit': ing['unit']})
    planned.post(f'/meals/{meal.id}/status', data={'status': 'cooked'})
    planned.post('/checkin', data={})
    assert quantities(planned)[(ing['name'], ing['unit'])] == round(100 - ing['quantity'], 2)
    assert planned.post(f'/meals/{meal.id}/status', data={'status': 'planned'}).status_code == 409
    planned.post('/checkin', data={})
    assert quantities(planned)[(ing['name'], ing['unit'])] == round(100 - ing['quantity'], 2)


def test_purchase_quantity_is_a_snapshot_not_current_recipe_amount(planned):
    p, ms = data(planned)
    item = grocery.build_list(m.as_dict() for m in ms)[0]
    planned.post('/grocery/toggle', data={'key': item['key'], 'checked': 'true', 'plan_id': p.id})
    with planned.app.state.session_factory() as s:
        for m in s.query(Meal).filter_by(plan_id=p.id):
            m.ingredients = [dict(i, quantity=i['quantity'] * 2) for i in m.ingredients]
        s.commit()
    planned.post('/checkin', data={})
    assert quantities(planned)[(item['name'], item['unit'])] == item['quantity']


def test_failed_regeneration_rolls_back_inventory_settlement(planned):
    p, ms = data(planned)
    item = grocery.build_list(m.as_dict() for m in ms)[0]
    planned.post('/grocery/toggle', data={'key': item['key'], 'checked': 'true'})
    with planned.app.state.session_factory() as s:
        profile = s.query(Profile).first()
        profile.budget = 1
        s.commit()
    planned.post('/plan/regenerate')
    assert quantities(planned) == {}
    with planned.app.state.session_factory() as s:
        assert not inventory.closed(s.get(Plan, p.id))


def test_stale_tab_cannot_update_new_plan_purchases(planned):
    old, ms = data(planned)
    key = grocery.build_list(m.as_dict() for m in ms)[0]['key']
    planned.post('/plan/regenerate')
    assert planned.post('/grocery/toggle', data={'key': key, 'checked': 'true', 'plan_id': old.id}).status_code == 409
    assert planned.post('/checkin', data={'plan_id': old.id}).status_code == 409


def test_unknown_quantities_and_different_units_remain_distinct(planned):
    planned.post('/pantry/add', data={'name': 'rice', 'quantity': 2, 'unit': 'cup'})
    planned.post('/pantry/add', data={'name': 'rice', 'quantity': 1, 'unit': 'lb'})
    planned.post('/pantry/add', data={'name': 'salt'})
    planned.post('/checkin', data={})
    q = quantities(planned)
    assert q[('rice', 'cup')] == 2 and q[('rice', 'lb')] == 1 and q[('salt', '')] is None


def test_partial_stock_plus_purchases_minus_consumption_balances(planned):
    p, ms = data(planned)
    item = grocery.build_list(m.as_dict() for m in ms)[0]
    stock = round(item['quantity'] / 2, 2)
    planned.post('/pantry/add', data={'name': item['name'], 'quantity': stock, 'unit': item['unit']})
    planned.post('/grocery/toggle', data={'key': item['key'], 'checked': 'true'})
    for m in ms:
        planned.post(f'/meals/{m.id}/status', data={'status': 'cooked'})
    planned.post('/checkin', data={})
    assert quantities(planned)[(item['name'], item['unit'])] == 0


def test_regenerations_settle_purchases_only_once(planned):
    p, ms = data(planned)
    item = grocery.build_list(m.as_dict() for m in ms)[0]
    planned.post('/grocery/toggle', data={'key': item['key'], 'checked': 'true'})
    planned.post('/plan/regenerate')
    once = quantities(planned)
    assert once[(item['name'], item['unit'])] == item['quantity']
    planned.post('/plan/regenerate')
    assert quantities(planned) == once


def test_completed_day_cannot_be_deleted_before_inventory_is_settled(planned):
    p, ms = data(planned)
    target = ms[0]
    planned.post(f'/meals/{target.id}/status', data={'status': 'cooked'})
    result = planned.post(f'/plan/days/{target.day}/skip')
    assert 'A day with completed meals cannot be removed' in result.text
    with planned.app.state.session_factory() as s:
        assert s.get(Meal, target.id).status == 'cooked'
