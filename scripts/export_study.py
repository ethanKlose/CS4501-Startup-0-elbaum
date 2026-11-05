"""Owner-operated export; only consented numerical data, no emails or notes."""
import hashlib
import hmac
import json
import secrets
import math
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


def correctness_summary(db,expected_participants=20):
    """One latest consented observation per account, never count repeat forms as people."""
    correct=reviewed=unreviewed=0
    for profile in db.scalars(select(UserPreference)):
        entries=[e for e in (profile.data or {}).get('study_entries',[]) if e.get('consent')]
        if not entries:continue
        outcome=entries[-1].get('plan_correct','not_reviewed')
        if outcome not in {'yes','no'}:unreviewed+=1;continue
        reviewed+=1;correct+=outcome=='yes'
    complete=reviewed==expected_participants and unreviewed==0
    return dict(source='consented student self-reviews; not independent reviewer judgments',
                expected_participants=expected_participants,reviewed_accounts=reviewed,
                unreviewed_accounts=unreviewed,correct_accounts=correct,
                threshold_count=math.ceil(.75*expected_participants),
                meets_threshold=(correct>=math.ceil(.75*expected_participants)) if complete else None,
                status='complete' if complete else 'not_collected' if reviewed+unreviewed==0 else 'incomplete')


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--correctness-only',action='store_true');args=parser.parse_args()
    with SessionLocal() as db:print(json.dumps(correctness_summary(db) if args.correctness_only else export(db),indent=2))
