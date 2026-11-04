import pytest
from sqlalchemy import text

from app import models  # noqa: F401
from app.db import Base, check_schema, make_engine


def test_fresh_and_current_databases_pass():
    eng = make_engine("sqlite://")
    check_schema(eng)  # nothing exists yet
    Base.metadata.create_all(eng)
    check_schema(eng)


def test_old_database_gets_a_clear_message():
    eng = make_engine("sqlite://")
    with eng.begin() as c:
        c.execute(text("CREATE TABLE meals (id INTEGER PRIMARY KEY, plan_id INTEGER, day INTEGER)"))
    with pytest.raises(RuntimeError, match="make reset"):
        check_schema(eng)
