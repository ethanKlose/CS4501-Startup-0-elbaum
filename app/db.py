from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings


class Base(DeclarativeBase):
    pass


def make_engine(url: str = None):
    url = url or settings.database_url
    kwargs = {"connect_args": {"check_same_thread": False}} if url.startswith("sqlite") else {}
    if url in ("sqlite://", "sqlite:///:memory:"):
        from sqlalchemy.pool import StaticPool

        kwargs["poolclass"] = StaticPool
    return create_engine(url, **kwargs)


engine = make_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def check_schema(eng) -> None:
    """Alpha has no migrations: fail loudly (not with a mysterious 500) when a local DB predates the models."""
    from sqlalchemy import inspect

    insp = inspect(eng)
    problems = []
    for table in Base.metadata.sorted_tables:
        if not insp.has_table(table.name):
            continue  # create_all will make it
        have = {c["name"] for c in insp.get_columns(table.name)}
        missing = sorted(c.name for c in table.columns if c.name not in have)
        if missing:
            problems.append(f"{table.name}: {', '.join(missing)}")
    if problems:
        raise RuntimeError(
            "Your local database is from an older version (missing columns -> " + "; ".join(problems) + "). "
            "Back up this database and apply a migration for the missing columns. No data was deleted."
        )


def init_db():
    from app import models  # noqa: F401  (register tables)

    from alembic import command
    from alembic.config import Config
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent
    config = Config(str(root / 'alembic.ini'))
    config.set_main_option('script_location', str(root / 'migrations'))
    with engine.begin() as connection:
        config.attributes['connection'] = connection
        command.upgrade(config, 'head')
    check_schema(engine)
