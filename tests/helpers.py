def signup(client, email="a@b.co", password="password123"):
    return client.post("/register", data={"email": email, "password": password}, follow_redirects=False)
