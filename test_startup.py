#!/usr/bin/env python3
"""
Test script to check if the app can be imported
"""

import sys
from pathlib import Path

BASE_DIR = Path(__file__).parent
sys.path.insert(0, str(BASE_DIR))

try:
    print("Testing imports...")
    from app.main import app
    print("✅ App import successful!")
    print(f"App: {app}")
except Exception as e:
    print(f"❌ Import error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

