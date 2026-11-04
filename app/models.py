import datetime as dt
from typing import Optional

from sqlalchemy import JSON, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

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
    onboarded: Mapped[bool] = mapped_column(default=False)
    free_text: Mapped[str] = mapped_column(String(1000), default="")


class DaySetting(Base):
    """Per-weekday availability (0=Monday ... 6=Sunday)."""

    __tablename__ = "day_settings"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    weekday: Mapped[int]
    busy: Mapped[bool] = mapped_column(default=False)
    minutes: Mapped[int] = mapped_column(default=45)


class PantryItem(Base):
    __tablename__ = "pantry_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(100))  # stored lowercase
    quantity: Mapped[Optional[float]] = mapped_column(default=None)
    unit: Mapped[str] = mapped_column(String(20), default="")


class Plan(Base):
    __tablename__ = "plans"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[dt.datetime] = mapped_column(default=dt.datetime.utcnow)
    status: Mapped[str] = mapped_column(String(16), default="ok")  # ok | failed
    message: Mapped[str] = mapped_column(String(2000), default="")  # user-facing explanation when failed
    attempts: Mapped[int] = mapped_column(default=1)
    budget: Mapped[float] = mapped_column(default=0)
    total_cost: Mapped[float] = mapped_column(default=0)
    seed: Mapped[int] = mapped_column(default=0)
    days: Mapped[list] = mapped_column(JSON, default=list)  # snapshot of per-day availability: weekday/minutes/busy/skipped

    meals = relationship("Meal", back_populates="plan", cascade="all, delete-orphan", order_by="Meal.day, Meal.id")


class Meal(Base):
    __tablename__ = "meals"

    id: Mapped[int] = mapped_column(primary_key=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("plans.id"), index=True)
    day: Mapped[int]
    slot: Mapped[str] = mapped_column(String(16))
    name: Mapped[str] = mapped_column(String(120))
    cook_minutes: Mapped[int] = mapped_column(default=0)
    calories: Mapped[int] = mapped_column(default=0)
    protein: Mapped[float] = mapped_column(default=0)
    cost: Mapped[float] = mapped_column(default=0)
    steps: Mapped[list] = mapped_column(JSON, default=list)
    ingredients: Mapped[list] = mapped_column(JSON, default=list)
    pinned: Mapped[bool] = mapped_column(default=False)

    plan = relationship("Plan", back_populates="meals")

    def as_dict(self) -> dict:
        return dict(day=self.day, slot=self.slot, name=self.name, cook_minutes=self.cook_minutes, calories=self.calories,
                    protein=self.protein, cost=self.cost, steps=self.steps, ingredients=self.ingredients)
