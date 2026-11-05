"""Shared meal deadlines and cooking times used by validation and the calendar."""
from collections import defaultdict

EAT = {'breakfast': (8 * 60, 60), 'lunch': (12 * 60 + 30, 60), 'dinner': (18 * 60 + 30, 75)}
COOK_END = 18 * 60 + 15
PREP_START = 10 * 60
MIN_VISUAL = 36


def timed_sessions(sessions, cooking_windows=None, meal_times=None, earliest_day=-1, earliest_minute=0):
    """Place each batch before its earliest same-day meal, without overlaps.

    A batch for future days can finish before dinner. Reserve a little extra
    space for short events so their labels remain readable on the time grid.
    """
    cooking_windows=cooking_windows or {}
    meal_times=meal_times or {}
    groups = defaultdict(list)
    for session in sessions:
        s = dict(session)
        prep_deadline=min(1440,meal_times.get('dinner',EAT['dinner'][0])-15)
        window=cooking_windows.get(str(s['cook_day']),cooking_windows.get('6') if s['cook_day']<0 else None)
        if window is not None or (s['cook_day']==earliest_day and earliest_minute):prep_deadline=1440
        s['deadline'] = min([meal_times.get(e['slot'], EAT[e['slot']][0]) for e in s['eats'] if e['day'] == s['cook_day']] or [prep_deadline])
        groups[s['cook_day']].append(s)
    out = []
    for day, group in sorted(groups.items()):
        group.sort(key=lambda s: (s['deadline'], s['name']))
        explicit=cooking_windows.get(str(day),cooking_windows.get(str(6)) if day<0 else None)
        if day==earliest_day and earliest_minute:
            explicit=explicit or [[earliest_minute,1440]]
        if day < 0 and explicit is None:
            cursor = PREP_START
            for s in group:
                s['start'], s['deadline'] = cursor, 24 * 60
                cursor += max(s['minutes'], MIN_VISUAL)
        else:
            # Start from the real latest deadline, not a fixed 18:15 cutoff.
            cursor = 1440 if day<0 else max(s['deadline'] for s in group) if explicit is not None or meal_times else COOK_END
            for s in reversed(group):
                deadline=1440 if day<0 else s['deadline']
                s['deadline']=deadline
                finish=min(cursor,deadline)
                reserve=s['minutes'] if explicit is not None else max(s['minutes'],MIN_VISUAL)
                options=[]
                for begin,end in (explicit if explicit is not None else [[0,1440]]):
                    begin=max(begin,earliest_minute if day==earliest_day else 0)
                    candidate=min(finish,end)-reserve
                    if candidate>=begin:options.append(candidate)
                s['start']=max(options) if options else -1
                cursor=s['start']
        out.extend(sorted(group, key=lambda s: s['start']))
    return out


def deadline_errors(sessions, cooking_windows=None, meal_times=None, earliest_day=-1, earliest_minute=0):
    from app.services.schedule import day_label

    return [f"{day_label(s['cook_day'])}: cannot finish cooking '{s['name']}' before its meal. Choose a shorter recipe or cook it on an earlier day."
            for s in timed_sessions(sessions,cooking_windows,meal_times,earliest_day,earliest_minute) if s['start'] < 0 or s['start'] + s['minutes'] > s['deadline']]
