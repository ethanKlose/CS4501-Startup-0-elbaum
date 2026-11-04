"""RFC 5545 calendar export with deterministic UIDs and escaped text."""
import datetime as dt
from app.services.weeks import plan_week_start
from app.services.schedule import build_sessions
from app.services.timing import EAT,timed_sessions
from app.config import settings


def escape(text):
    return str(text).replace('\\','\\\\').replace('\r','').replace('\n','\\n').replace(';','\\;').replace(',','\\,')


def fold(line):
    parts=[];current='';size=0
    for char in line:
        length=len(char.encode('utf-8'))
        if size+length>74:
            parts.append(current);current=' '+char;size=1+length
        else:current+=char;size+=length
    return '\r\n'.join(parts+[current])


def export(plan):
    st=plan.settings or {};start=plan_week_start(plan);zone=settings.timezone
    rows=['BEGIN:VCALENDAR','VERSION:2.0','PRODID:-//PlateJoy//Meal planner//EN','CALSCALE:GREGORIAN','X-WR-TIMEZONE:'+escape(zone)]
    stamp=dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    def event(uid,day,minute,duration,title,description=''):
        begins=dt.datetime.combine(start+dt.timedelta(days=day),dt.time())+dt.timedelta(minutes=minute)
        ends=begins+dt.timedelta(minutes=duration)
        rows.extend(['BEGIN:VEVENT','UID:'+uid+'@platejoy.local','DTSTAMP:'+stamp,'DTSTART;TZID='+zone+':'+begins.strftime('%Y%m%dT%H%M%S'),'DTEND;TZID='+zone+':'+ends.strftime('%Y%m%dT%H%M%S'),'SUMMARY:'+escape(title),'DESCRIPTION:'+escape(description),'END:VEVENT'])
    for meal in plan.meals:
        if meal.status=='skipped':continue
        minute=st.get('meal_times',{}).get(meal.slot,EAT[meal.slot][0])
        event(f'plan-{plan.id}-meal-{meal.id}',meal.day,minute,EAT[meal.slot][1],meal.name,'\n'.join(meal.steps))
    saved=[dict(m.as_dict(),cook_day=m.cook_day,frozen=m.frozen) for m in plan.meals]
    timing=dict(cooking_windows=st.get('cooking_windows',{}),meal_times=st.get('meal_times',{}),earliest_day=st.get('earliest_day',-1),earliest_minute=st.get('earliest_minute',0))
    for index,session in enumerate(timed_sessions(build_sessions(saved),**timing)):
        if session['start']>=0:event(f'plan-{plan.id}-cook-{index}',session['cook_day'],session['start'],session['minutes'],'Cook '+session['name'],f"Prepare {session['servings']} serving(s).")
    for index,external in enumerate(st.get('external_slots',[])):
        if not external.get('past'):
            event(f'plan-{plan.id}-external-{index}',external['day'],st.get('meal_times',{}).get(external['slot'],EAT[external['slot']][0]),EAT[external['slot']][1],external['source'])
    rows.append('END:VCALENDAR')
    return '\r\n'.join(fold(row) for row in rows)+'\r\n'
