from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.config import settings
from app.db import init_db
from app.deps import LoginRequired
from app.routers import auth, pages
from fastapi.responses import RedirectResponse

BASE = Path(__file__).parent


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="PlateJoy (alpha)", lifespan=lifespan)
    app.add_middleware(SessionMiddleware, secret_key=settings.secret_key, same_site="lax")
    app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")

    @app.exception_handler(LoginRequired)
    async def _login_required(request, exc):
        return RedirectResponse("/login", 303)

    app.include_router(auth.router)
    app.include_router(pages.router)

    @app.get("/health")
    def health():
        return {"status": "ok"}

    return app


app = create_app()
