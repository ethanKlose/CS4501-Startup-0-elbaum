"""Create tables and a demo user: demo@platejoy.dev / demo-password"""
from sqlalchemy import select

from app.db import SessionLocal, init_db
from app.models import User
from app.security import hash_password

DEMO_EMAIL, DEMO_PASSWORD = "demo@platejoy.dev", "demo-password"


def main():
    init_db()
    with SessionLocal() as db:
        if not db.scalar(select(User).where(User.email == DEMO_EMAIL)):
            db.add(User(email=DEMO_EMAIL, password_hash=hash_password(DEMO_PASSWORD)))
            db.commit()
            print(f"Created demo user {DEMO_EMAIL} / {DEMO_PASSWORD}")
        else:
            print("Demo user already exists")


if __name__ == "__main__":
    main()
