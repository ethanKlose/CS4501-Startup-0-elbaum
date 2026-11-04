from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import current_user
from app.models import User
from app.services import planner
from app.services.llm import get_llm

router = APIRouter()


@router.post("/plan/generate")
def generate_plan(request: Request, user: User = Depends(current_user), db: Session = Depends(get_db), llm=Depends(get_llm)):
    try:
        planner.generate(db, user, llm)
    except planner.PlanFailed as e:
        request.session["flash_error"] = {"message": e.message, "conflicts": e.conflicts}
    return RedirectResponse("/", 303)
