#!/usr/bin/env python3
"""
ZedinArkManager - FastAPI szerver indító script
"""

import sys
import os
from pathlib import Path

# Virtual environment ellenőrzése
BASE_DIR = Path(__file__).parent
venv_python = BASE_DIR / "venv" / "bin" / "python"

# Systemd service esetén ne írjunk stdout-ra (csak stderr-re)
is_systemd = os.getenv("INVOCATION_ID") is not None

if venv_python.exists() and sys.executable != str(venv_python):
    if not is_systemd:
        print("⚠️  Figyelem: Virtual environment nem aktiválva!", file=sys.stderr)
        print(f"   Aktiváld: source venv/bin/activate", file=sys.stderr)
        print(f"   Vagy futtasd: {venv_python} run.py", file=sys.stderr)

try:
    import uvicorn
except ImportError as e:
    print(f"❌ HIBA: uvicorn nincs telepítve: {e}", file=sys.stderr)
    sys.exit(1)

try:
    from app.main import app
except Exception as e:
    print(f"❌ HIBA: App import sikertelen: {e}", file=sys.stderr)
    import traceback
    traceback.print_exc(file=sys.stderr)
    sys.exit(1)

if __name__ == "__main__":
    # Production módban ne használjunk reload-ot (systemd service esetén)
    use_reload = os.getenv("UVICORN_RELOAD", "false").lower() == "true"
    
    try:
        uvicorn.run(
            "app.main:app",
            host="0.0.0.0",
            port=8000,
            reload=use_reload,
            log_level="info"
        )
    except Exception as e:
        print(f"❌ HIBA: Uvicorn indítás sikertelen: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)
