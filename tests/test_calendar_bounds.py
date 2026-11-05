import datetime as dt
import re
from app.services.calview import build_columns,grid_bounds,fmt_time
from tests.helpers import signup


def test_grid_bounds_include_early_meals_and_late_end_times():
    cols=build_columns([],[],[],dt.date(2026,11,9),meal_times={'breakfast':360,'dinner':1439},external_slots=[{'day':0,'slot':'breakfast','source':'Breakfast elsewhere'},{'day':0,'slot':'dinner','source':'Late dinner'}])
    assert grid_bounds(cols)==(6,26)
    assert fmt_time(25*60)=='1:00 AM (+1 day)'


def test_external_events_have_positions_and_late_meals_fit_the_grid(client):
    signup(client);client.post('/survey',data={'budget':'150'})
    client.post('/preferences/lifestyle',data={'equipment':['stove','oven','toaster','blender','fridge','freezer'],'external_0_lunch':'on'})
    client.post('/preferences/schedule',data={'time_breakfast':'06:00','time_lunch':'13:00','time_dinner':'22:00'})
    html=client.post('/plan/generate',data={'start_mode':'next_week'}).text
    match=re.search(r'data-testid="external-event" style="([^"]+)"',html)
    assert match
    first_hour=int(re.search(r'class="gutter".*?<span[^>]*>(\d+) AM</span>',html,re.S).group(1))
    top=float(re.search(r'--top:([\d.]+)px',match.group(1)).group(1))
    assert top==(13-first_hour)*75
    grid=float(re.search(r'--grid:([\d.]+)px',html).group(1))
    for top,height in re.findall(r'style="--top:([\d.]+)px;--h:([\d.]+)px;',html):
        assert float(top)>=0 and float(top)+float(height)<=grid
