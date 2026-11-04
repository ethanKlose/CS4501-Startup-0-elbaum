import re
from typing import Optional

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import current_user_optional, render
from app.models import User
from app.security import hash_password, verify_password

router = APIRouter()
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@router.get("/register")
def register_form(request: Request, user=Depends(current_user_optional)):
    return render(request, "register.html", user)


@router.post("/register")
def register(request: Request, email: str = Form(""), password: str = Form(""), db: Session = Depends(get_db)):
    email = email.strip().lower()
    error = None
    if not EMAIL_RE.match(email):
        error = "Enter a valid email."
    elif len(password) < 8:
        error = "Password must be at least 8 characters."
    elif db.scalar(select(User).where(User.email == email)):
        error = "That email is already registered."
    if error:
        return render(request, "register.html", None, 400, error=error, email=email)
    user = User(email=email, password_hash=hash_password(password))
    db.add(user)
    db.commit()
    request.session["user_id"] = user.id
    return RedirectResponse("/", 303)


@router.get("/login")
def login_form(request: Request, user=Depends(current_user_optional)):
    return render(request, "login.html", user)


@router.post("/login")
def login(request: Request, email: str = Form(""), password: str = Form(""), db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == email.strip().lower()))
    if not user or not verify_password(password, user.password_hash):
        return render(request, "login.html", None, 401, error="Invalid email or password.", email=email)
    request.session["user_id"] = user.id
    return RedirectResponse("/", 303)


@router.post("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", 303)
