# ViMove Deploy (Render)

## Neler değişti?
- Python tabanlı oyun yerine **tarayıcı tabanlı** (JS + MediaPipe Tasks) oyun eklendi.
- FastAPI sadece sayfaları ve statikleri servis ediyor (Render uyumlu).
- `app/static/game/game.html` ve `game.js`: tarayıcıda çalışan oyun.
- `requirements.txt`: Sunucu için minimal (mediapipe/opencv çıkarıldı). Tüm bağımlılıkların yedeği `requirements_all.txt`.

## Nasıl deploy edilir?
1. Bu klasörü GitHub'a pushla.
2. Render Dashboard → New → Web Service
3. Repo'yu seç → `render.yaml` otomatik algılanır (ya da Python env seçip start komutu: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`).
4. Deploy bitince oyun sayfası: `/static/game/game.html`

## Notlar
- Kamera için **HTTPS** gereklidir. Render bunu sağlar.
- Eşik değeri `game.js` içinde `isOpen()` fonksiyonunda `0.24` — ortamına göre 0.22–0.27 arası deneyebilirsin.
- Ana arayüz dosyalarına **dokunulmadı**. İstersen ana sayfana sadece bir link ekleyebilirsin:
  `<a href="/static/game/game.html">Oyunu başlat</a>`
