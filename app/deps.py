from pathlib import Path
from typing import Optional

from fastapi import Depends, HTTPException, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.db import get_db
from app.config import settings
from app.models import User

templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


class LoginRequired(Exception):
    pass


def current_user_optional(request: Request, db: Session = Depends(get_db)) -> Optional[User]:
    uid = request.session.get("user_id")
    return db.get(User, uid) if uid else None


def current_user(user: Optional[User] = Depends(current_user_optional)) -> User:
    if user is None:
        raise LoginRequired()
    return user


def render(request: Request, name: str, user: Optional[User] = None, status_code: int = 200, **ctx):
    ctx.update(user=user, request=request, offline_mode=not bool(settings.anthropic_api_key.strip()))
    return templates.TemplateResponse(request, name, ctx, status_code=status_code)
