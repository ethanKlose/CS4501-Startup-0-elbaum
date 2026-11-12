"""User-initiated account connection, calendar synchronization and status."""
import os

import httpx
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse

from app.db import get_db
from app.deps import current_user, render
from app.services import google_calendar as google, planner, kroger
from app.routers.kroger import MESSAGES as KROGER_MESSAGES
from app.services.locking import lock_user
from app.services.preferences import get_preferences, save_preferences

router = APIRouter()
MESSAGES = {
    'configuration': 'Google Calendar needs local setup. You can still use Export calendar on your plan.',
    'connected': 'Google Calendar connected. Choose Sync current week to add your meals and prep blocks.',
    'cancelled': 'Google connection cancelled. Your plan has not changed.',
    'state': 'The connection request expired or could not be verified. Start Connect again.',
    'reconnect': 'Reconnect Google Calendar to continue. Your local plan is safe.',
    'provider': 'Google could not be reached. Try connecting again later.',
    'response': 'Google returned an unexpected response. Try again later.',
    'permission': 'Google did not allow this calendar operation. Check Calendar API access and reconnect.',
    'quota': 'Google Calendar is temporarily limiting requests. Wait before syncing again.',
    'partial': 'Sync did not finish. Some events may already be saved. Retry to complete it without duplicates.',
    'collision': 'An event ID conflict prevented syncing. No unrelated event was changed.',
    'disconnected': 'Google disconnected and credentials removed. Previously synced events remain in Google Calendar.',
    'local_disconnect': 'Credentials removed locally. Google could not confirm revocation; remove PlateJoy access in your Google account too.',
}


def result(request, code, **details):
    request.session['integration_result'] = dict(code=code, **details)
    return RedirectResponse('/integrations', 303)


@router.get('/integrations')
def integrations(request: Request, user=Depends(current_user), db=Depends(get_db)):
    data = get_preferences(db, user.id)
    flash = request.session.pop('integration_result', {})
    message = MESSAGES.get(flash.get('code'))
    if flash.get('code') == 'synced':
        counts = flash['counts']
        message = f"Calendar synced: {counts['created']} added, {counts['updated']} updated, {counts['deleted']} removed, {counts['unchanged']} unchanged."
    return render(request, 'integrations.html', user,
        kroger_configured=kroger.configured(), kroger_connected=bool(data.get('kroger_connection')),
        kroger_message=KROGER_MESSAGES.get(request.session.pop('kroger_result','')),
        google_configured=google.configured(),
        google_connected=bool(data.get('google_connection')), instacart_configured=bool(os.environ.get('INSTACART_API_KEY', '').strip()),
        plan=planner.latest_plan(db, user), message=message, last_sync=data.get('google_last_sync'),
        calendar_styles=google.EVENT_STYLES.values())


@router.post('/integrations/google/connect')
def connect(request: Request, user=Depends(current_user), db=Depends(get_db)):
    lock_user(db, user.id)
    data = get_preferences(db, user.id)
    try:
        url = google.begin(data, request.session, user.id)
    except google.CalendarError as exc:
        return result(request, str(exc))
    save_preferences(db, user.id, data)
    db.commit()
    return RedirectResponse(url, 303)


@router.get('/integrations/google/callback')
def callback(request: Request, state: str = '', code: str = '', error: str = '', user=Depends(current_user), db=Depends(get_db)):
    lock_user(db, user.id)
    data = get_preferences(db, user.id)
    try:
        verifier = google.consume_state(data, request.session, state, user.id)
    except google.CalendarError as exc:
        save_preferences(db, user.id, data)
        db.commit()
        return result(request, str(exc))
    # A callback is one-use even if the provider times out during exchange.
    save_preferences(db, user.id, data)
    db.commit()
    if error:
        return result(request, 'cancelled')
    try:
        token = google.exchange(code, verifier)
    except google.CalendarError as exc:
        return result(request, str(exc))
    lock_user(db, user.id)
    data = get_preferences(db, user.id)
    data['google_connection'] = google.seal(token, user.id)
    data.pop('google_last_sync', None)
    save_preferences(db, user.id, data)
    db.commit()
    return result(request, 'connected')


@router.post('/integrations/google/sync')
def sync(request: Request, plan_id: int = Form(...), user=Depends(current_user), db=Depends(get_db)):
    lock_user(db, user.id)
    plan = planner.latest_plan(db, user)
    if not plan or plan.id != plan_id or plan.status != 'ok':
        raise HTTPException(409, 'Your current plan changed. Reload before syncing.')
    data = get_preferences(db, user.id)
    try:
        token = google.access_token(data, user.id)
        # Persist any rotated refresh token before making calendar requests.
        save_preferences(db, user.id, data)
        db.commit()
        # Recheck under the per-user lock after the refresh transaction.
        lock_user(db, user.id)
        db.expire_all()
        data = get_preferences(db, user.id)
        current = planner.latest_plan(db, user)
        if not current or current.id != plan_id:
            raise HTTPException(409, 'Your current plan changed. Reload before syncing.')
        counts = google.sync(current, user.id, token)
    except google.CalendarError as exc:
        if str(exc) == 'reconnect':
            data.pop('google_connection', None)
        save_preferences(db, user.id, data)
        db.commit()
        return result(request, str(exc))
    data = get_preferences(db, user.id)
    data['google_last_sync'] = dict(plan_id=plan_id, at=google.dt.datetime.now(google.dt.timezone.utc).isoformat(), counts=counts)
    save_preferences(db, user.id, data)
    db.commit()
    return result(request, 'synced', counts=counts)


@router.post('/integrations/google/disconnect')
def disconnect(request: Request, user=Depends(current_user), db=Depends(get_db)):
    lock_user(db, user.id)
    data = get_preferences(db, user.id)
    token = None
    if data.get('google_connection'):
        try:
            token = google.unseal(data['google_connection'], user.id).get('refresh_token')
        except google.CalendarError:
            pass
    for key in ('google_connection', 'google_pending', 'google_last_sync'):
        data.pop(key, None)
    request.session.pop('google_oauth_state', None)
    save_preferences(db, user.id, data)
    db.commit()
    if token:
        try:
            with httpx.Client(timeout=8, follow_redirects=False) as client:
                response = client.post('https://oauth2.googleapis.com/revoke', data={'token': token})
            if response.status_code not in (200, 400):
                return result(request, 'local_disconnect')
        except httpx.HTTPError:
            return result(request, 'local_disconnect')
    return result(request, 'disconnected')
