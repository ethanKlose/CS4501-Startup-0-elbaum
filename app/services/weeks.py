"""Explicit plan weeks; old plans retain their original calendar dates."""
import datetime as dt
from zoneinfo import ZoneInfo
from app.config import settings


def planning_now():
    return dt.datetime.now(ZoneInfo(settings.timezone))


def planning_today():
    return planning_now().date()


def next_monday(today):
    return today + dt.timedelta(days=7 - today.weekday())


def plan_week_start(plan):
    saved = (plan.settings or {}).get('week_start')
    if saved:
        return dt.date.fromisoformat(saved)
    from app.services.calview import week_start_for
    return week_start_for(plan.created_at.date())


def target_week(previous, new_week=False):
    today = planning_today()
    upcoming = next_monday(today)
    if previous and previous.status == 'ok':
        previous_start = plan_week_start(previous)
        if new_week:
            return max(upcoming, previous_start + dt.timedelta(days=7))
        if previous_start + dt.timedelta(days=7) > today:
            return previous_start
    return upcoming
