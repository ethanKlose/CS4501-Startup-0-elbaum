"""Actions enter through HTTP; snapshots use separate committed DB sessions."""
import copy

from sqlalchemy import select

from app.models import Plan, User

EMAIL = "integration@example.test"
PASSWORD = "IntegrationPass123!"


def post(client, path, data=None, **kwargs):
    """Submit the same session-bound CSRF form field used by server-rendered forms."""
    if not client.cookies.get("csrf_token"):
        assert client.get("/health").status_code == 200
    return client.post(path, data={"csrf_token": client.cookies["csrf_token"], **(data or {})}, **kwargs)


def register(client, email=EMAIL):
    response = post(client, "/register", {"email": email, "password": PASSWORD})
    assert response.status_code == 303, response.text
    assert response.headers["location"] == "/"
    return email


def onboard(client, email=EMAIL, **survey):
    register(client, email)
    response = post(client, "/survey", {"budget": "200", **survey})
    assert response.status_code == 303, response.text


def generate(client, path="/plan/generate", **data):
    response = post(client, path, data)
    assert response.status_code == 303, response.text
    page = client.get("/")
    assert page.status_code == 200
    assert 'id="meals-data"' in page.text, page.text
    return page


def snapshot(application, email=EMAIL):
    with application.sessions() as db:
        plan = db.scalar(select(Plan).join(User).where(User.email == email).order_by(Plan.id.desc()))
        assert plan is not None
        return dict(id=plan.id, user_id=plan.user_id, budget=plan.budget, total_cost=plan.total_cost,
                    settings=copy.deepcopy(plan.settings), warnings=list(plan.warnings), attempts=plan.attempts,
                    days=copy.deepcopy(plan.days),
                    meals=[dict(m.as_dict(), id=m.id, status=m.status, rating=m.rating,
                                pinned=m.pinned, cook_day=m.cook_day, frozen=m.frozen) for m in plan.meals])


def pantry(application, user_id):
    from app.models import PantryItem
    with application.sessions() as db:
        return {(row.name, row.unit): row.quantity for row in db.scalars(
            select(PantryItem).where(PantryItem.user_id == user_id))}


def shopping(application, plan_id):
    from app.services.inventory import shopping_items
    with application.sessions() as db:
        return shopping_items(db, db.get(Plan, plan_id))
