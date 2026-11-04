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
