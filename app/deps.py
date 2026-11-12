from pathlib import Path
from typing import Optional

from fastapi import Depends, HTTPException, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.db import get_db
from app.config import settings
from app.models import User
from app.services.preferences import get_preferences

templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


class LoginRequired(Exception):
    pass


def current_user_optional(request: Request, db: Session = Depends(get_db)) -> Optional[User]:
    uid = request.session.get("user_id")
    user = db.get(User, uid) if uid else None
    if user and request.session.get("auth_version",0) != get_preferences(db,user.id).get("auth_version",0):
        request.session.clear()
        return None
    return user


def current_user(user: Optional[User] = Depends(current_user_optional)) -> User:
    if user is None:
        raise LoginRequired()
    return user


def render(request: Request, name: str, user: Optional[User] = None, status_code: int = 200, **ctx):
    plan=ctx.get("plan")
    closest=(plan.settings or {}).get("closest",{}) if plan else {}
    ctx["local_fallback_plan"]=closest.get("source")=="catalog_fallback" and closest.get("requested_engine") not in {"fake",None}
    ctx.update(user=user, request=request, csrf_token=request.session.get("csrf_token", ""), offline_mode=not (settings.openai_api_key.strip() or settings.anthropic_api_key.strip()))
    return templates.TemplateResponse(request, name, ctx, status_code=status_code)
