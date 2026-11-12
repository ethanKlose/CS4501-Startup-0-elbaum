from app.models import UserPreference


def get_preferences(db, user_id):
    row=db.get(UserPreference,user_id)
    return dict(row.data or {}) if row else {}


def save_preferences(db,user_id,data):
    row=db.get(UserPreference,user_id)
    if row is None:
        row=UserPreference(user_id=user_id,data=dict(data));db.add(row)
    else:row.data=dict(data)
    db.flush()
    return row


def signature(db,user_id):
    """Hash planning inputs; never include integration credentials or auth state."""
    import hashlib,json
    from sqlalchemy import select
    from app.models import Profile,DaySetting,PantryItem
    profile=db.scalar(select(Profile).where(Profile.user_id==user_id))
    values={c.name:getattr(profile,c.name) for c in Profile.__table__.columns if c.name not in {'id','user_id'}} if profile else {}
    days=[{c.name:getattr(day,c.name) for c in DaySetting.__table__.columns if c.name not in {'id','user_id'}} for day in db.scalars(select(DaySetting).where(DaySetting.user_id==user_id).order_by(DaySetting.weekday))]
    prefs=get_preferences(db,user_id)
    lifestyle={k:prefs[k] for k in ('equipment','cooking_skill','external_slots','cooking_windows','meal_times','price_offers') if k in prefs}
    pantry=[dict(name=p.name,quantity=p.quantity,unit=p.unit) for p in db.scalars(select(PantryItem).where(PantryItem.user_id==user_id).order_by(PantryItem.name,PantryItem.unit))]
    return hashlib.sha256(json.dumps([values,days,lifestyle,pantry],sort_keys=True,default=str).encode()).hexdigest()
