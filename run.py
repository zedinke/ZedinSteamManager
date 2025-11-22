#!/usr/bin/env python3
"""
ZedinArkManager - FastAPI szerver indító script
"""

import sys
from pathlib import Path

# Virtual environment ellenőrzése
BASE_DIR = Path(__file__).parent
venv_python = BASE_DIR / "venv" / "bin" / "python"

if venv_python.exists() and sys.executable != str(venv_python):
    print("⚠️  Figyelem: Virtual environment nem aktiválva!")
    print(f"   Aktiváld: source venv/bin/activate")
    print(f"   Vagy futtasd: {venv_python} run.py")
    print()

import uvicorn
from app.main import app

if __name__ == "__main__":
    # Production módban ne használjunk reload-ot (systemd service esetén)
    import os
    use_reload = os.getenv("UVICORN_RELOAD", "false").lower() == "true"
    
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=use_reload
    )
