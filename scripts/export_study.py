"""Owner-operated export; only consented numerical data, no emails or notes."""
import hashlib
import hmac
import json
from sqlalchemy import select
from app.db import SessionLocal
from app.models import UserPreference
from app.config import settings


def export(db):
    rows=[]
    for profile in db.scalars(select(UserPreference)):
        participant=hmac.new(settings.secret_key.encode(),str(profile.user_id).encode(),hashlib.sha256).hexdigest()[:16]
        for entry in (profile.data or {}).get('study_entries',[]):
            if entry.get('consent'):
                safe={k:entry.get(k) for k in ['actual_spend','actual_minutes','baseline_minutes','ease','planned_meals','cooked_meals','checkout_estimate']}
                rows.append(dict(participant=participant,**safe))
    return {'source':'consented student self-reports','results':rows}


if __name__=='__main__':
    with SessionLocal() as db:print(json.dumps(export(db),indent=2))
