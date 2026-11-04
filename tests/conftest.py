import os

os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ["ANTHROPIC_API_KEY"] = ""  # tests never hit the real API
os.environ["OPENAI_API_KEY"] = ""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.db import Base, get_db, make_engine
from app.main import create_app


@pytest.fixture()
def session_factory():
    engine = make_engine("sqlite://")  # in-memory, shared via StaticPool
    from app import models  # noqa: F401

    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@pytest.fixture()
def client(session_factory):
    app = create_app()

    def override():
        s = session_factory()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = override
    app.state.session_factory = session_factory
    with TestClient(app) as c:
        yield c
