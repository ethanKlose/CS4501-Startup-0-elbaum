"""Owner-operated export; only consented numerical data, no emails or notes."""
import hashlib
import hmac
import json
import secrets
from sqlalchemy import select
from app.db import SessionLocal
from app.models import UserPreference
from app.config import settings


def export(db):
    rows=[]
    for profile in db.scalars(select(UserPreference)):
        participant=hmac.new(settings.secret_key.encode(),str(profile.user_id).encode(),hashlib.sha256).hexdigest()[:16] if settings.production else secrets.token_hex(8)
        for entry in (profile.data or {}).get('study_entries',[]):
            if entry.get('consent'):
                safe={k:entry.get(k) for k in ['actual_spend','actual_minutes','baseline_minutes','ease','planned_meals','cooked_meals','checkout_estimate']}
                safe['plan_correct']=entry.get('plan_correct','not_reviewed')
                safe['correctness_source']='student self-review'
                safe['failed_constraints']=[v for v in entry.get('failed_constraints',[]) if v in {'budget','diet','schedule','equipment','nutrition','coverage','extra_notes'}]
                rows.append(dict(participant=participant,**safe))
    return {'source':'consented student self-reports','results':rows}


if __name__=='__main__':
    with SessionLocal() as db:print(json.dumps(export(db),indent=2))
