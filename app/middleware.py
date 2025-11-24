"""
Error handling middleware
"""

from fastapi import Request, status
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
import traceback
import sys

async def catch_exceptions_middleware(request: Request, call_next):
    """Exception handler middleware"""
    try:
        response = await call_next(request)
        return response
    except Exception as e:
        # Log the error
        print(f"\n{'='*60}")
        print(f"ERROR: {type(e).__name__}: {str(e)}")
        print(f"Path: {request.url.path}")
        print(f"{'='*60}")
        traceback.print_exc()
        print(f"{'='*60}\n")
        
        # Return error response
        if "text/html" in request.headers.get("accept", ""):
            error_html = f"""
            <html>
            <head><title>Internal Server Error</title></head>
            <body>
                <h1>Internal Server Error</h1>
                <h2>{type(e).__name__}: {str(e)}</h2>
                <pre>{traceback.format_exc()}</pre>
            </body>
            </html>
            """
            return HTMLResponse(content=error_html, status_code=500)
        else:
            return JSONResponse(
                status_code=500,
                content={
                    "error": type(e).__name__,
                    "message": str(e),
                    "traceback": traceback.format_exc()
                }
            )

async def session_role_refresh_middleware(request: Request, call_next):
    """Session role refresh middleware - frissíti a session-t, ha a felhasználó rangja változott"""
    # Alapértelmezett: üres lista az Ark játékokhoz
    request.state.ark_games = []
    
    # Csak akkor ellenőrizzük, ha van session-ben user_id
    user_id = request.session.get("user_id")
    if user_id:
        try:
            # Csak akkor csinálunk adatbázis lekérdezést, ha van session-ben user_id
            # és nem API endpoint vagy statikus fájl (hogy ne lassítsuk az API-t)
            if (not request.url.path.startswith("/api/") and 
                not request.url.path.startswith("/static/") and
                not request.url.path.startswith("/_") and
                request.method == "GET"):  # Csak GET request-eknél, hogy ne lassítsuk a POST-okat
                from app.database import SessionLocal, User, Game
                
                # Adatbázis session létrehozása
                db = SessionLocal()
                try:
                    current_user = db.query(User).filter(User.id == user_id).first()
                    if current_user:
                        # Ellenőrizzük, hogy változott-e a rang
                        current_role = request.session.get("user_role")
                        if current_role != current_user.role.value:
                            # Frissítjük a session-t
                            request.session["user_role"] = current_user.role.value
                    
                    # Ark játékok lekérése a template-ekhez (sidebar-hoz)
                    ark_games = db.query(Game).filter(
                        Game.name.ilike("%ark%"),
                        Game.is_active == True
                    ).order_by(Game.name).all()
                    request.state.ark_games = ark_games
                finally:
                    db.close()
        except Exception:
            # Ha hiba történik, ne akadályozza a request feldolgozását
            # Üres lista marad (már beállítottuk az elején)
            pass
    
    response = await call_next(request)
    return response

