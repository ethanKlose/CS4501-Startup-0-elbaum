from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse

from app.deps import current_user_optional, render

router = APIRouter()


@router.get("/")
def home(request: Request, user=Depends(current_user_optional)):
    if user is None:
        return RedirectResponse("/login", 303)
    return render(request, "home.html", user)
