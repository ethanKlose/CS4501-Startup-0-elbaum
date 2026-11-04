"""Shared meal deadlines and cooking times used by validation and the calendar."""
from collections import defaultdict

EAT = {'breakfast': (8 * 60, 60), 'lunch': (12 * 60 + 30, 60), 'dinner': (18 * 60 + 30, 75)}
COOK_END = 18 * 60 + 15
PREP_START = 10 * 60
MIN_VISUAL = 36


def timed_sessions(sessions):
    """Place each batch before its earliest same-day meal, without overlaps.

    A batch for future days can finish before dinner. Reserve a little extra
    space for short events so their labels remain readable on the time grid.
    """
    groups = defaultdict(list)
    for session in sessions:
        s = dict(session)
        s['deadline'] = min([EAT[e['slot']][0] for e in s['eats'] if e['day'] == s['cook_day']] or [COOK_END])
        groups[s['cook_day']].append(s)
    out = []
    for day, group in sorted(groups.items()):
        group.sort(key=lambda s: (s['deadline'], s['name']))
        if day < 0:
            cursor = PREP_START
            for s in group:
                s['start'], s['deadline'] = cursor, 24 * 60
                cursor += max(s['minutes'], MIN_VISUAL)
        else:
            cursor = COOK_END
            for s in reversed(group):
                finish = min(cursor, s['deadline'])
                s['start'] = finish - max(s['minutes'], MIN_VISUAL)
                cursor = s['start']
        out.extend(sorted(group, key=lambda s: s['start']))
    return out


def deadline_errors(sessions):
    from app.services.schedule import day_label

    return [f"{day_label(s['cook_day'])}: cannot finish cooking '{s['name']}' before its meal. Choose a shorter recipe or cook it on an earlier day."
            for s in timed_sessions(sessions) if s['start'] < 0 or s['start'] + s['minutes'] > s['deadline']]
