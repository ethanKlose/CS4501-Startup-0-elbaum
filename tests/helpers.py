def signup(client, email="a@b.co", password="password123"):
    return client.post("/register", data={"email": email, "password": password}, follow_redirects=False)


def set_budget(client, value):
    """Set the saved budget directly (the survey form enforces a minimum, tests sometimes need tiny budgets)."""
    from app.models import Profile

    with client.app.state.session_factory() as s:
        p = s.query(Profile).first()
        p.budget = value
        s.commit()
