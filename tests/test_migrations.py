from sqlalchemy import inspect, text
from alembic import command
from alembic.config import Config
from app.db import make_engine


def test_baseline_adopts_existing_data_and_can_be_run_twice(tmp_path):
    engine=make_engine('sqlite:///'+str(tmp_path/'old.db'))
    with engine.begin() as c:
        c.execute(text('CREATE TABLE users (id INTEGER PRIMARY KEY, email VARCHAR(255) NOT NULL, password_hash VARCHAR(255) NOT NULL, created_at DATETIME NOT NULL)'))
        c.execute(text("INSERT INTO users VALUES (1, 'kept@example.test', 'hash', '2026-11-04')"))
        config=Config('alembic.ini'); config.attributes['connection']=c
        command.upgrade(config,'head');command.upgrade(config,'head')
        assert c.execute(text('SELECT email FROM users')).scalar()=='kept@example.test'
        assert 'user_preferences' in inspect(c).get_table_names()
