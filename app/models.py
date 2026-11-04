import datetime as dt
from typing import Optional

from sqlalchemy import JSON, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[dt.datetime] = mapped_column(default=dt.datetime.utcnow)


class Profile(Base):
    """One row per user: the survey answers."""

    __tablename__ = "profiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True)
    budget: Mapped[Optional[float]] = mapped_column(default=None)
    restrictions: Mapped[list] = mapped_column(JSON, default=list)
    goal: Mapped[str] = mapped_column(String(32), default="none")  # none | high_protein | calorie_target
    calorie_target: Mapped[Optional[int]] = mapped_column(default=None)
    free_text: Mapped[str] = mapped_column(String(1000), default="")


class DaySetting(Base):
    """Per-weekday availability (0=Monday ... 6=Sunday)."""

    __tablename__ = "day_settings"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    weekday: Mapped[int]
    busy: Mapped[bool] = mapped_column(default=False)
    minutes: Mapped[int] = mapped_column(default=45)
