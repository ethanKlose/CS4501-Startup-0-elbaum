from app.services.timing import timed_sessions,deadline_errors


def session(name,minutes,slot='dinner',cook_day=0,eat_day=0):
    return dict(cook_day=cook_day,name=name,minutes=minutes,servings=1,eats=[dict(day=eat_day,slot=slot)])


def test_evening_window_can_end_after_the_old_cutoff():
    meals=[session('Dinner',20)]
    times={'dinner':21*60};windows={'0':[[19*60,20*60+30]]}
    s=timed_sessions(meals,windows,times)[0]
    assert 19*60<=s['start'] and s['start']+s['minutes']<=20*60+30
    assert not deadline_errors(meals,windows,times)


def test_late_sessions_do_not_overlap_and_do_not_run_past_the_meal():
    sessions=[session('A',20),session('B',25)]
    out=sorted(timed_sessions(sessions,{'0':[[19*60,21*60]]},{'dinner':21*60}),key=lambda s:s['start'])
    assert out[0]['start']>=19*60
    assert out[0]['start']+out[0]['minutes']<=out[1]['start']
    assert all(s['start']+s['minutes']<=21*60 for s in out)


def test_explicit_late_prep_and_planning_start_are_respected():
    meals=[session('Prep',30,eat_day=1)]
    out=timed_sessions(meals,{'0':[[19*60,21*60]]},{'dinner':22*60},0,20*60)[0]
    assert out['start']>=20*60
    assert not deadline_errors(meals,{'0':[[19*60,21*60]]},{'dinner':22*60},0,20*60)


def test_too_short_late_window_is_still_rejected():
    assert deadline_errors([session('Dinner',40)],{'0':[[1200,1220]]},{'dinner':1260})
