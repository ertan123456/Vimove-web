# app/main.py  — sade, Render uyumlu sürüm (harici process YOK)
from pathlib import Path
import json
from typing import Optional

from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

# -------------------------------------------------
# Temel FastAPI yapılandırması
# -------------------------------------------------
app = FastAPI(title="NöroHareket App")

APP_DIR = Path(__file__).resolve().parent           # .../app
TEMPLATES_DIR = APP_DIR / "templates"               # .../app/templates
STATIC_DIR = APP_DIR / "static"                     # .../app/static
BASE_DIR = APP_DIR.parent                           # .../proje kökü

DATA_FILE = BASE_DIR / "last_selection.json"

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# -------------------------------------------------
# Health check (Render için zorunlu)
# -------------------------------------------------
@app.get("/health")
def health():
    return {"status": "ok"}

# -------------------------------------------------
# Ana sayfa
# -------------------------------------------------
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
            "last": last,
            "last_json": last_json
        }
        return templates.TemplateResponse("index.html", ctx)
    except Exception as e:
        return HTMLResponse(f"<pre>Template error:\n{e}</pre>", status_code=500)

# -------------------------------------------------
# /start — Form POST'u al, doğrula, kaydet, OYUNA YÖNLENDİR
# (Harici .py süreci başlatmak YOK)
# -------------------------------------------------
@app.post("/start", response_class=HTMLResponse)
def start(
    request: Request,
    age: int = Form(...),
    gender: str = Form(...),
    disease: str = Form(...),
):
    gender = (gender or "").lower()
    disease = (disease or "").lower()

    # Basit doğrulamalar (eski mantığı koruyoruz)
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

    # Seçimi kaydet (isterseniz oyunda da okunabilir)
    DATA_FILE.write_text(json.dumps(
        {"age": age, "gender": gender, "disease": disease},
        ensure_ascii=False, indent=2
    ), encoding="utf-8")

    # Tarayıcı tabanlı oyun sayfasına gönder
    return RedirectResponse(url="/static/game/game.html", status_code=302)

# -------------------------------------------------
# Eski alışkanlık: GET /start → oyun sayfasına gönder
# -------------------------------------------------
@app.get("/start")
def start_get_redirect():
    return RedirectResponse(url="/static/game/game.html", status_code=302)
