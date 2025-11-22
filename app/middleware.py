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

