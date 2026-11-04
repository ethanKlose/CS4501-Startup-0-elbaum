"""A database-backed per-user write lock works across tabs and workers."""
from sqlalchemy import update
from app.models import User


def lock_user(db, user_id):
    # An UPDATE obtains a write/row lock until commit or rollback on SQLite and
    # PostgreSQL. Flush first so refreshes cannot discard this request's work.
    db.flush()
    db.execute(update(User).where(User.id == user_id).values(id=User.id).execution_options(synchronize_session=False))
