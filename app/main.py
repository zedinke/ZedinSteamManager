"""
ZedinArkManager - FastAPI fő alkalmazás
"""

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from pathlib import Path
from app.config import settings
from app.middleware import catch_exceptions_middleware

# Projekt gyökér
BASE_DIR = Path(__file__).parent.parent

# FastAPI app
app = FastAPI(
    title="ZedinArkManager",
    description="Játék szerver kezelő manager rendszer",
    version="2.0.0",
    debug=True
)

# Exception handler middleware (legelső)
app.middleware("http")(catch_exceptions_middleware)

# Session middleware
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.session_secret_key,
    max_age=3600 * 24 * 7  # 7 nap
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Statikus fájlok
static_dir = BASE_DIR / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# Template-ek
templates_dir = BASE_DIR / "templates"
if not templates_dir.exists():
    templates_dir.mkdir(exist_ok=True)
templates = Jinja2Templates(directory=str(templates_dir))

# Routers importálása
from app.routers import auth, dashboard, tokens, admin, notifications, api, notifications_admin, update, system

# Routers regisztrálása
app.include_router(auth.router, tags=["Auth"])
app.include_router(dashboard.router, tags=["Dashboard"])
app.include_router(tokens.router, tags=["Tokens"])
app.include_router(admin.router, tags=["Admin"])
app.include_router(notifications.router, tags=["Notifications"])
app.include_router(notifications_admin.router, tags=["Admin Notifications"])
app.include_router(update.router, tags=["Update"])
app.include_router(system.router, tags=["System"])
app.include_router(api.router, prefix="/api", tags=["API"])

# Updating oldal router
from fastapi.responses import HTMLResponse

@app.get("/updating", response_class=HTMLResponse)
async def updating_page(request: Request):
    """Updating oldal - frissítés közben"""
    return templates.TemplateResponse("updating.html", {"request": request})

# Template globális elérhetővé tétele
def get_templates():
    return templates

@app.get("/")
async def root(request: Request):
    """Főoldal - átirányítás login-ra"""
    return RedirectResponse(url="/login", status_code=302)

@app.get("/health")
async def health():
    """Health check endpoint"""
    return {"status": "ok", "version": "2.0.0"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )
