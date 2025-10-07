import os
import json
import subprocess
import sys
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse

@app.get("/start")
def start_get_redirect():
    # /start URL’sine girenleri yeni web-oyun sayfasına yönlendir
    return RedirectResponse(url="/static/game/game.html", status_code=302)


app = FastAPI(title="NöroHareket App")

# --- KLASÖR YOLLARI DOĞRU AYARLANIYOR ---
APP_DIR = Path(__file__).resolve().parent           # ...\elderly_exercise_site\app
TEMPLATES_DIR = APP_DIR / "templates"               # ...\elderly_exercise_site\app\templates
STATIC_DIR = APP_DIR / "static"                     # ...\elderly_exercise_site\app\static
BASE_DIR = APP_DIR.parent                           # ...\elderly_exercise_site

GAME_PATH = BASE_DIR / "game.py"
PID_FILE = BASE_DIR / "game.pid"
DATA_FILE = BASE_DIR / "last_selection.json"

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

def is_running() -> bool:
    if PID_FILE.exists():
        try:
            pid = int(PID_FILE.read_text().strip())
        except Exception:
            return False
        # Check process existence in a cross-platform way
        try:
            if os.name == "nt":
                # On Windows, this will throw OSError if not running
                import ctypes
                SYNCHRONIZE = 0x00100000
                process_handle = ctypes.windll.kernel32.OpenProcess(SYNCHRONIZE, False, pid)
                if process_handle == 0:
                    return False
                ctypes.windll.kernel32.CloseHandle(process_handle)
                return True
            else:
                os.kill(pid, 0)
                return True
        except Exception:
            return False
    return False

def launch_game():
        python_exe = sys.executable
        proc = subprocess.Popen([python_exe, str(GAME_PATH)], cwd=str(BASE_DIR))
        PID_FILE.write_text(str(proc.pid))
  
def stop_game():
    if not PID_FILE.exists():
        return False
    try:
        pid = int(PID_FILE.read_text().strip())
    except Exception:
        PID_FILE.unlink(missing_ok=True)
        return False
    try:
        if os.name == "nt":
            subprocess.call(["taskkill", "/F", "/PID", str(pid)])
        else:
            os.kill(pid, 9)
    except Exception:
        pass
    PID_FILE.unlink(missing_ok=True)
    return True

@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    try:
        last = None
        last_json = None
        if DATA_FILE.exists():
            txt = DATA_FILE.read_text(encoding="utf-8")
            last_json = txt
            try:
                last = json.loads(txt)
            except Exception:
                last = None

        ctx = {
            "request": request,
            "running": is_running(),
            "last": last,
            "last_json": last_json
        }
        return templates.TemplateResponse("index.html", ctx)
    except Exception as e:
        # Şablon patlarsa direkt sayfada hatayı gör
        return HTMLResponse(f"<pre>Template error:\n{e}</pre>", status_code=500)


@app.post("/start", response_class=HTMLResponse)
def start(
    request: Request,
    age: int = Form(...),
    gender: str = Form(...),
    disease: str = Form(...),
):
    # Basic validation
    gender = gender.lower()
    disease = disease.lower()
    if disease != "parkinson":
        return templates.TemplateResponse(
            "error.html",
            {"request": request, "msg": "Hastalık olarak demo sürecimizde Parkinson mevcuttur."},
            status_code=400
        )
    if gender not in ["male", "female", "other"]:
        return templates.TemplateResponse(
            "error.html",
            {"request": request, "msg": "Cinsiyet seçeneklerinden birini seçiniz."},
            status_code=400
        )

    # Seçimleri kaydet
    DATA_FILE.write_text(json.dumps(
        {"age": age, "gender": gender, "disease": disease},
        ensure_ascii=False, indent=2
    ))

    # Stale PID dosyası varsa temizle
    if PID_FILE.exists() and not is_running():
        PID_FILE.unlink(missing_ok=True)

    # OpenCV oyununu başlat (zaten açıksa tekrar başlatma)
    if not is_running():
        try:
            launch_game()
            note = "The Application has been started."
        except Exception as e:
            note = f"Başlatma hatası: {e}"
    else:
        note = "Uygulama zaten çalışıyor."

    # Aynı sekmede onay sayfasını göster
    return templates.TemplateResponse("started.html", {"request": request, "note": note})


@app.post("/stop")
def stop(request: Request):
    ok = stop_game()
    msg = "Uygulama kapatıldı." if ok else "Çalışan uygulama bulunamadı."
    return templates.TemplateResponse("stopped.html", {"request": request, "msg": msg})

@app.get("/health")
def health():
    return {"status": "ok"}
