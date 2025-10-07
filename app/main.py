# app/main.py  — tam, Render-uyumlu, eksiksiz FastAPI uygulaması
from __future__ import annotations

from pathlib import Path
import json
from typing import Optional

from fastapi import FastAPI, Request, Form, status
from fastapi.responses import (
    HTMLResponse,
    RedirectResponse,
    JSONResponse,
    PlainTextResponse,
)
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

# ---------------------------------------------------------------------
# Yol/klasörler
# ---------------------------------------------------------------------
APP_DIR = Path(__file__).resolve().parent           # .../app
TEMPLATES_DIR = APP_DIR / "templates"               # .../app/templates
STATIC_DIR = APP_DIR / "static"                     # .../app/static
BASE_DIR = APP_DIR.parent                           # .../proje kökü
DATA_FILE = BASE_DIR / "last_selection.json"        # form verisi burada saklanır

# ---------------------------------------------------------------------
# Uygulama
# ---------------------------------------------------------------------
app = FastAPI(
    title="NöroHareket App",
    description="Tarayıcı tabanlı egzersiz oyunu için FastAPI sunucusu",
    version="1.0.0",
)

# Statik ve şablonlar
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# ---------------------------------------------------------------------
# Basit ama gerekli güvenlik başlıkları (CSP: jsDelivr + Google Storage izinli)
# Çok sert yapmıyoruz; aksi halde model/WASM dosyaları bloklanabilir.
# ---------------------------------------------------------------------
@app.middleware("http")
async def add_security_headers(request, call_next):
    resp = await call_next(request)
    resp.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        # WASM için 'unsafe-eval' / 'wasm-unsafe-eval' ve blob: ekledik
        "script-src 'self' https://cdn.jsdelivr.net 'unsafe-eval' 'wasm-unsafe-eval' blob:; "
        "connect-src 'self' https://cdn.jsdelivr.net https://storage.googleapis.com; "
        "img-src 'self' data: blob:; "
        "style-src 'self' 'unsafe-inline'; "
        "media-src 'self' blob:; "
        "worker-src 'self' blob:; "
        "frame-ancestors 'self'; "
        "object-src 'none';"
    )
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    return resp

# ---------------------------------------------------------------------
# Sağlık kontrolü (Render health check)
# ---------------------------------------------------------------------
@app.get("/health")
def health():
    return {"status": "ok"}

# Basit ping
@app.get("/api/ping")
def api_ping():
    return {"pong": True}

# Son seçim JSON
@app.get("/api/selection")
def api_selection():
    if DATA_FILE.exists():
        try:
            data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
        except Exception:
            data = None
    else:
        data = None
    return {"selection": data}

# ---------------------------------------------------------------------
# Ana sayfa
# ---------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    """
    templates/index.html varsa onu render eder; yoksa basit bir fallback HTML döner.
    """
    if (TEMPLATES_DIR / "index.html").exists():
        last = None
        last_json = None
        if DATA_FILE.exists():
            txt = DATA_FILE.read_text(encoding="utf-8")
            last_json = txt
            try:
                last = json.loads(txt)
            except Exception:
                last = None
        ctx = {"request": request, "last": last, "last_json": last_json}
        return templates.TemplateResponse("index.html", ctx)

    # Fallback minimal HTML (şablon yoksa)
    html = """
    <h1>NöroHareket</h1>
    <p><a href="/static/game/game.html">Oyunu Başlat</a></p>
    <p><a href="/health">/health</a></p>
    """
    return HTMLResponse(html)

# ---------------------------------------------------------------------
# /start — Form POST: doğrula, kaydet, oyuna yönlendir
# ---------------------------------------------------------------------
@app.post("/start", response_class=HTMLResponse)
def start_post(
    request: Request,
    age: int = Form(...),
    gender: str = Form(...),
    disease: str = Form(...),
):
    gender = (gender or "").lower().strip()
    disease = (disease or "").lower().strip()

    # Basit doğrulamalar (mevcut davranışı koruyoruz)
    if disease != "parkinson":
        if (TEMPLATES_DIR / "error.html").exists():
            return templates.TemplateResponse(
                "error.html",
                {"request": request, "msg": "Hastalık olarak demo sürecimizde Parkinson mevcuttur."},
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        return HTMLResponse("Hastalık olarak yalnızca Parkinson destekleniyor.", status_code=400)

    if gender not in ["male", "female", "other"]:
        if (TEMPLATES_DIR / "error.html").exists():
            return templates.TemplateResponse(
                "error.html",
                {"request": request, "msg": "Cinsiyet seçeneklerinden birini seçiniz."},
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        return HTMLResponse("Cinsiyet seçeneklerinden birini seçiniz.", status_code=400)

    # Seçimi kaydet (oyun gerekirse bunu okuyabilir)
    DATA_FILE.write_text(
        json.dumps({"age": age, "gender": gender, "disease": disease}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # Tarayıcı tabanlı oyun sayfasına gönder
    return RedirectResponse(url="/static/game/game.html", status_code=status.HTTP_302_FOUND)

# ---------------------------------------------------------------------
# /start — GET: direkt oyuna yönlendir (eski alışkanlık)
# ---------------------------------------------------------------------
@app.get("/start")
def start_get():
    return RedirectResponse(url="/static/game/game.html", status_code=status.HTTP_302_FOUND)

# ---------------------------------------------------------------------
# 404 için basit bir fallback (opsiyonel)
# ---------------------------------------------------------------------
@app.exception_handler(404)
def not_found(request: Request, exc):
    # Şablon varsa kullan; yoksa düz metin
    if (TEMPLATES_DIR / "404.html").exists():
        return templates.TemplateResponse("404.html", {"request": request}, status_code=404)
    return PlainTextResponse("404 Not Found", status_code=404)
