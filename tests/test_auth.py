def signup(client, email="a@b.co", password="password123"):
    return client.post("/register", data={"email": email, "password": password}, follow_redirects=False)


def test_home_requires_login(client):
    r = client.get("/", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/login"


def test_register_logs_in(client):
    assert signup(client).status_code == 303
    assert "a@b.co" in client.get("/").text


def test_register_validation(client):
    assert signup(client, email="bad").status_code == 400
    assert signup(client, password="short").status_code == 400
    signup(client)
    client.post("/logout")
    assert signup(client).status_code == 400  # duplicate


def test_login_logout(client):
    signup(client)
    client.post("/survey", data={"budget": "50"})  # finish onboarding
    client.post("/logout")
    assert client.post("/login", data={"email": "a@b.co", "password": "wrongwrong"}).status_code == 401
    r = client.post("/login", data={"email": "A@b.co", "password": "password123"}, follow_redirects=False)
    assert r.status_code == 303
    assert client.get("/", follow_redirects=False).status_code == 200
