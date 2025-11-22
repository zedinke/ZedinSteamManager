#!/bin/bash
# ZedinArkManager - Szerver indító script

cd "$(dirname "$0")"

# Virtual environment aktiválása ha létezik
if [ -d "venv" ]; then
    echo "Virtual environment aktiválása..."
    source venv/bin/activate
fi

# Python parancs meghatározása
if [ -f "venv/bin/python" ]; then
    PYTHON_CMD="venv/bin/python"
elif command -v python3 &> /dev/null; then
    PYTHON_CMD="python3"
else
    PYTHON_CMD="python"
fi

echo "Szerver indítása: $PYTHON_CMD run.py"
$PYTHON_CMD run.py

