@echo off
REM Simple runner for Windows
setlocal

REM Create venv if missing
if not exist .venv (
  py -3 -m venv .venv
)

call .venv\Scripts\activate

python -m pip install --upgrade pip
pip install --no-cache-dir -r requirements.txt

echo.
echo Sunucu basliyor: http://127.0.0.1:8000
start "" "http://127.0.0.1:8000"
uvicorn app.main:app --host 127.0.0.1 --port 8000
