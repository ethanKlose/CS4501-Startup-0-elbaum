"""Report scoped checks against the saved plan, including unverifiable legacy data."""
from app.services.planner import plan_ctx
from app.services import validators as v


def summary(plan):
    ctx=plan_ctx(plan);raw={'meals':[m.as_dict() for m in plan.meals]};st=plan.settings or {}
    rows=[]
    def add(label,checks,known=True,requested=True):
        errors=[e for check in checks for e in check(raw,ctx)] if known and requested else []
        status='Not recorded' if not known else 'Not requested' if not requested else 'Needs review' if errors else 'Passed'
        rows.append(dict(label=label,status=status,details=errors))
    add('Meal coverage',[v.check_coverage])
    add('Budget estimate',[v.check_budget,v.check_checkout_budget],known=bool(st.get('checkout_budget')) and 'pantry' in st)
    add('Diet and kitchen rules',[v.check_diet],known='restrictions' in st and 'excluded' in st)
    add('Cooking schedule',[v.check_schedule,v.check_cooking_deadlines])
    add('Nutrition goal',[v.check_goal],requested=ctx.goal!='none')
    rows.append(dict(label='Extra notes',status='Needs review' if ctx.preference_warnings else 'Passed',details=ctx.preference_warnings))
    review=bool(plan.warnings) or any(r['status'] in {'Needs review','Not recorded'} for r in rows)
    return dict(label='Needs review' if review else 'Checks passed',needs_review=review,checks=rows)
