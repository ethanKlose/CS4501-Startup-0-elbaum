from app.services.timing import timed_sessions,deadline_errors


def test_breakfast_uses_only_available_morning_window():
    session=dict(cook_day=0,name='Oatmeal',minutes=8,servings=1,eats=[{'day':0,'slot':'breakfast'}])
    result=timed_sessions([session],{'0':[[420,435],[1020,1140]]})[0]
    assert 420<=result['start'] and result['start']+8<=435
    assert deadline_errors([session],{'0':[[1020,1140]]})


def test_custom_meal_times_change_cooking_deadline():
    session=dict(cook_day=0,name='Lunch',minutes=20,servings=1,eats=[{'day':0,'slot':'lunch'}])
    result=timed_sessions([session],{'0':[[660,720]]},{'lunch':720})[0]
    assert result['start']==700
