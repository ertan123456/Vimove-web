// Tüm egzersizler: El, Yüz (Ağız/Göz), Pose (Bacak/Kol), Otur-Kalk (kalibrasyonlu)
// MediaPipe Tasks Vision (JS/WASM) ile çalışır.

import {
  FilesetResolver,
  HandLandmarker,
  FaceLandmarker,
  PoseLandmarker
} from "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.8";

const video = document.getElementById("video");
const canvas = document.getElementById("overlay");
const ctx = canvas.getContext("2d");
const btnStart = document.getElementById("btnStart");
const btnReset = document.getElementById("btnReset");
const statusEl = document.getElementById("status");
const infoEl = document.getElementById("info");
const fpsEl = document.getElementById("fps");
const LstateEl = document.getElementById("Lstate");
const RstateEl = document.getElementById("Rstate");
const exerciseNameEl = document.getElementById("exerciseName");
const repsEl = document.getElementById("reps");
const targetEl = document.getElementById("target");
const barEl = document.getElementById("bar");
const planListEl = document.getElementById("planList");
const diagEl = document.getElementById("diag");

canvas.width = 640; canvas.height = 480;

// ------- Python'daki parametrelerin JS karşılığı -------
const FONT_SIZE = 28; // UI için değil; sadece referans
const CALIBRATION_FRAMES = 60;
const SMOOTHING_WINDOW = 5;
const DEBOUNCE_FRAME = 10;

const OTURMA_ORANI = 0.75;
const KALKMA_ORANI = 0.92;
const DIZ_OTURMA_ACI = 110;  // altına inerse oturma
const DIZ_KALKMA_ACI = 150;  // üstüne çıkarsa dikleşme

// ------- Egzersiz Planı (senin listedeki sıralama) -------
const PLAN = [
  { ad: "Left Hand Open - Close", hedef: 10 },
  { ad: "Right Hand Open - Close",  hedef: 10 },
  { ad: "Mouth Open - Close",      hedef: 5  },
  { ad: "Right Eye Blink",         hedef: 5  },
  { ad: "Left Eye Blink",          hedef: 5  },
  { ad: "Right Leg Extension",     hedef: 8  },
  { ad: "Left Leg Extension",      hedef: 8  },
  { ad: "Right Arm Raise",         hedef: 5  },
  { ad: "Left Arm Raise",          hedef: 5  },
  { ad: "Sit Down, Stand Up",      hedef: 8  },
];

let ix = 0;                 // aktif egzersiz
let reps = 0;               // tekrar sayacı
let running = false;
let handLandmarker, faceLandmarker, poseLandmarker;
let lastTime = performance.now(), frameCount = 0;

// El durumları (debounce)
let parmak_acik_sag = false;
let parmak_acik_sol = false;
// Yüz
let agiz_acik = false;
let goz_kirpma_sag = false;
let goz_kirpma_sol = false;
// Bacak/kol
let bacak_acik_sag = false;
let bacak_acik_sol = false;
let kol_kaldirma_sag = false;
let kol_kaldirma_sol = false;

// Otur-kalk kalibrasyon
let referans_yukseklik = null;
let calib_count = 0;
let son_yukseklikler = [];

// Debounce frame
let frame_son_tekrar = DEBOUNCE_FRAME;

// ---------------- Helpers ----------------
function dist2(a, b) {
  const dx = a.x - b.x, dy = a.y - b.y;
  return Math.hypot(dx, dy);
}
function angleDeg(a, b, c) {
  const ba = {x: a.x - b.x, y: a.y - b.y};
  const bc = {x: c.x - b.x, y: c.y - b.y};
  const denom = (Math.hypot(ba.x, ba.y) * Math.hypot(bc.x, bc.y));
  if (!denom) return 180.0;
  let cosang = (ba.x*bc.x + ba.y*bc.y) / denom;
  cosang = Math.min(1, Math.max(-1, cosang));
  return Math.acos(cosang) * (180/Math.PI);
}
// El açık/kapalı eşiği (işaret parmağı ucu (8) – bilek (0))
function elAcikMi(lm) {
  return dist2(lm[8], lm[0]) > 0.24; // 0.22–0.27 arası ortamına göre
}
// Ağız açık mı (Face Mesh 468 index: 13 üst iç dudak, 14 alt iç dudak)
function agizAcikMi(lm) {
  const u = lm[13], d = lm[14];
  return dist2(u, d) > 0.03;
}
// Göz kırpma (468 index: sağ=159/145, sol=386/374)
function gozKirpmaMi(lm, sag = true) {
  let ust, alt;
  if (sag) { ust = lm[159]; alt = lm[145]; }
  else     { ust = lm[386]; alt = lm[374]; }
  return dist2(ust, alt) < 0.015;
}
// Bacağı yana açma: ankle-hip x farkı (Pose 33 index: L:23/27, R:24/28)
function bacakAcmaMi(lm, sag = true) {
  let hip, ankle;
  if (sag) { hip = lm[24]; ankle = lm[28]; }
  else     { hip = lm[23]; ankle = lm[27]; }
  return Math.abs(ankle.x - hip.x) > 0.15;
}
// Kol kaldırma: bilek y omuz y'den belirgin yukarıda (küçük y = yukarı)
function kolKaldirmaMi(lm, sag = true) {
  let omuz, el_bil;
  if (sag) { omuz = lm[12]; el_bil = lm[16]; }
  else     { omuz = lm[11]; el_bil = lm[15]; }
  return el_bil.y < (omuz.y - 0.1);
}

// Oturup-kalkma (kalibrasyon + smoothing + diz açısı)
function oturupKalkmaTick(lm) {
  // 0 nose, 27 left_ankle, 28 right_ankle
  const bas = lm[0], ayak_sag = lm[28], ayak_sol = lm[27];
  if (!bas || !ayak_sag || !ayak_sol) return false;

  const ayak_ort_y = (ayak_sag.y + ayak_sol.y) / 2.0;
  const yukseklik = Math.abs(bas.y - ayak_ort_y);

  // smoothing
  son_yukseklikler.push(yukseklik);
  if (son_yukseklikler.length > SMOOTHING_WINDOW) son_yukseklikler.shift();
  const avg = son_yukseklikler.reduce((a,b)=>a+b,0) / son_yukseklikler.length;

  // calibration
  if (referans_yukseklik === null && calib_count < CALIBRATION_FRAMES) {
    calib_count++;
    if (calib_count === CALIBRATION_FRAMES) {
      const med = median(son_yukseklikler.length ? son_yukseklikler : [yukseklik]);
      referans_yukseklik = Math.max(med, 0.25);
    }
    return false;
  }
  if (referans_yukseklik === null) return false;

  const oturma_esigi = referans_yukseklik * OTURMA_ORANI;
  const kalkma_esigi = referans_yukseklik * KALKMA_ORANI;

  // diz açısı min (R: 24-26-28, L: 23-25-27)
  const aci_r = angleOrDefault(lm[24], lm[26], lm[28], 180);
  const aci_l = angleOrDefault(lm[23], lm[25], lm[27], 180);
  const diz_min = Math.min(aci_r, aci_l);

  // durum makinesi: oturma (true) / ayakta (false)
  // global oturukalk mantığını burada yerelleştiriyoruz
  if (!state.oturukalk && (avg < oturma_esigi || diz_min < DIZ_OTURMA_ACI)) {
    state.oturukalk = true;
  } else if (state.oturukalk && (avg > kalkma_esigi && diz_min > DIZ_KALKMA_ACI)) {
    state.oturukalk = false;
    return true; // bir tekrar say
  }
  return false;
}
function angleOrDefault(a,b,c,defv){ if(!a||!b||!c) return defv; return angleDeg(a,b,c); }
function median(arr){ const s=[...arr].sort((x,y)=>x-y); const m=Math.floor(s.length/2); return s.length%2? s[m]:(s[m-1]+s[m])/2; }

// ---------------- UI helpers ----------------
function setExerciseUI() {
  const ex = PLAN[ix];
  exerciseNameEl.textContent = ex.ad;
  targetEl.textContent = ex.hedef;
  repsEl.textContent = reps;
  barEl.style.width = `${Math.min(100, Math.round((reps/ex.hedef)*100))}%`;
  const items = PLAN.map((e,i)=> `<li class="${i<ix?'done':''}">${i===ix?'👉 ':''}${e.ad} — hedef ${e.hedef}</li>`).join("");
  planListEl.innerHTML = items;

  // küçük ipucu metni
  let hint = "İpucu: El/poz/yüz hareketini bir ‘açık→kapalı’ döngüsü olarak tamamla.";
  if (ex.ad.includes("Mouth")) hint = "İpucu: Ağız açık→kapalı bir tekrar sayılır.";
  if (ex.ad.includes("Blink")) hint = "İpucu: Tam kapanıp açılınca 1 tekrar.";
  if (ex.ad.includes("Leg"))   hint = "İpucu: Ayağı yana belirgin açıp geri getir.";
  if (ex.ad.includes("Arm"))   hint = "İpucu: Bilek omuzun hayli üstüne çıkıp geri insin.";
  if (ex.ad.includes("Sit"))   hint = "İpucu: İlk 5 sn ayakta dur (kalibrasyon), sonra otur→kalk döngüsü 1 tekrar.";
  document.getElementById("hint").textContent = hint;
}
function resetExercise() {
  reps = 0;
  frame_son_tekrar = DEBOUNCE_FRAME;
  // el/yüz/poz bayrakları sıfırla
  parmak_acik_sag = false; parmak_acik_sol = false;
  agiz_acik = false; goz_kirpma_sag = false; goz_kirpma_sol = false;
  bacak_acik_sag = false; bacak_acik_sol = false;
  kol_kaldirma_sag = false; kol_kaldirma_sol = false;
  // otur-kalk
  state.oturukalk = false;
  setExerciseUI();
}
function nextExerciseAuto() {
  if (ix < PLAN.length - 1) {
    ix += 1;
    resetExercise();
    infoEl.textContent = `Sıradaki egzersiz: ${PLAN[ix].ad}`;
  } else {
    infoEl.textContent = "Tebrikler! Tüm egzersizler tamamlandı 🎉";
  }
}

// ---------------- MediaPipe init ----------------
async function initModels() {
const vision = await FilesetResolver.forVisionTasks(
  "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.8/wasm"
);

// ✨ DOĞRU model yolları (latest kanalı):
handLandmarker = await HandLandmarker.createFromOptions(vision, {
  baseOptions: {
    modelAssetPath:
      "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/latest/hand_landmarker.task"
  },
  numHands: 2,
  runningMode: "VIDEO"
});

faceLandmarker = await FaceLandmarker.createFromOptions(vision, {
  baseOptions: {
    modelAssetPath:
      "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/latest/face_landmarker.task"
  },
  outputFaceBlendshapes: false,
  runningMode: "VIDEO",
  numFaces: 1
});

poseLandmarker = await PoseLandmarker.createFromOptions(vision, {
  baseOptions: {
    modelAssetPath:
      "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_full/float16/latest/pose_landmarker_full.task"
  },
  runningMode: "VIDEO",
  numPoses: 1
});

}

// ---------------- Kamera ----------------
async function startCam() {
  if (location.protocol !== "https:" && location.hostname !== "localhost") {
    throw new Error("Kamera için HTTPS gerekli.");
  }
  if (!navigator.mediaDevices?.getUserMedia) {
    throw new Error("Tarayıcın getUserMedia desteklemiyor.");
  }
  const stream = await navigator.mediaDevices.getUserMedia({ video: { width: 640, height: 480 } });
  video.srcObject = stream;
  await new Promise(r => video.onloadedmetadata = r);
  try { await video.play(); } catch {}
}

// ---------------- Ana döngü ----------------
const state = { oturukalk: false };

function drawLandmarks(dots, color="#5ddcff") {
  ctx.strokeStyle = color;
  ctx.lineWidth = 2;
  for (const lm of dots) {
    ctx.beginPath();
    ctx.arc(lm.x * canvas.width, lm.y * canvas.height, 3, 0, Math.PI*2);
    ctx.stroke();
  }
}

function tick() {
  if (!running) return;
  const now = performance.now();
  frameCount++;
  if (now - lastTime > 1000) {
    fpsEl.textContent = `FPS: ${frameCount}`;
    frameCount = 0; lastTime = now;
  }

  ctx.clearRect(0,0,canvas.width,canvas.height);

  // detect
  const handsRes = handLandmarker.detectForVideo(video, now);
  const faceRes  = faceLandmarker.detectForVideo(video, now);
  const poseRes  = poseLandmarker.detectForVideo(video, now);

  // ---- görsel çizim (isteğe bağlı basit noktalar) ----
  if (handsRes?.landmarks?.length) {
    for (const lms of handsRes.landmarks) drawLandmarks(lms, "#5ddcff");
  }
  const faceLms = (faceRes && (faceRes.faceLandmarks || faceRes.landmarks))?.[0];
  if (faceLms) drawLandmarks(faceLms, "#ffa1a1");
  const poseLms = poseRes?.landmarks?.[0];
  if (poseLms) drawLandmarks(poseLms, "#a1ffa1");

  // ----- tekrar sayma -----
  let hareket_basarili = false;

  // aktif egzersiz adı
  const ad = PLAN[ix].ad;

  // El egzersizleri
  if (ad.includes("Right Hand") || ad.includes("Left Hand")) {
    if (handsRes?.landmarks?.length && handsRes.handedness) {
      for (let i=0;i<handsRes.landmarks.length;i++){
        const lm = handsRes.landmarks[i];
        const handed = handsRes.handedness[i]?.[0]?.categoryName || ""; // "Left"/"Right"
        const acik = elAcikMi(lm);
        const kapali = !acik;

        if (ad.includes("Left Hand") && handed === "Right") { // ayna düzeltmesi
          if (!parmak_acik_sag && acik) parmak_acik_sag = true;
          else if (parmak_acik_sag && kapali) { parmak_acik_sag = false; hareket_basarili = true; }
        } else if (ad.includes("Right Hand") && handed === "Left") {
          if (!parmak_acik_sol && acik) parmak_acik_sol = true;
          else if (parmak_acik_sol && kapali) { parmak_acik_sol = false; hareket_basarili = true; }
        }
      }
    }
  }
  // Ağız
  else if (ad === "Mouth Open - Close") {
    if (faceLms) {
      const durum = agizAcikMi(faceLms);
      if (!agiz_acik && durum) agiz_acik = true;
      else if (agiz_acik && !durum) { agiz_acik = false; hareket_basarili = true; }
    }
  }
  // Sağ göz
  else if (ad === "Right Eye Blink") {
    if (faceLms) {
      const kirpma = gozKirpmaMi(faceLms, true);
      if (!goz_kirpma_sag && kirpma) goz_kirpma_sag = true;
      else if (goz_kirpma_sag && !kirpma) { goz_kirpma_sag = false; hareket_basarili = true; }
    }
  }
  // Sol göz
  else if (ad === "Left Eye Blink") {
    if (faceLms) {
      const kirpma = gozKirpmaMi(faceLms, false);
      if (!goz_kirpma_sol && kirpma) goz_kirpma_sol = true;
      else if (goz_kirpma_sol && !kirpma) { goz_kirpma_sol = false; hareket_basarili = true; }
    }
  }
  // Sağ bacak
  else if (ad === "Right Leg Extension") {
    if (poseLms) {
      const b = bacakAcmaMi(poseLms, true);
      if (!bacak_acik_sag && b) bacak_acik_sag = true;
      else if (bacak_acik_sag && !b) { bacak_acik_sag = false; hareket_basarili = true; }
    }
  }
  // Sol bacak
  else if (ad === "Left Leg Extension") {
    if (poseLms) {
      const b = bacakAcmaMi(poseLms, false);
      if (!bacak_acik_sol && b) bacak_acik_sol = true;
      else if (bacak_acik_sol && !b) { bacak_acik_sol = false; hareket_basarili = true; }
    }
  }
  // Sağ kol
  else if (ad === "Right Arm Raise") {
    if (poseLms) {
      const k = kolKaldirmaMi(poseLms, true);
      if (!kol_kaldirma_sag && k) kol_kaldirma_sag = true;
      else if (kol_kaldirma_sag && !k) { kol_kaldirma_sag = false; hareket_basarili = true; }
    }
  }
  // Sol kol
  else if (ad === "Left Arm Raise") {
    if (poseLms) {
      const k = kolKaldirmaMi(poseLms, false);
      if (!kol_kaldirma_sol && k) kol_kaldirma_sol = true;
      else if (kol_kaldirma_sol && !k) { kol_kaldirma_sol = false; hareket_basarili = true; }
    }
  }
  // Otur kalk
  else if (ad === "Sit Down, Stand Up") {
    if (poseLms) {
      if (oturupKalkmaTick(poseLms)) hareket_basarili = true;
    }
  }

  // Debounce + sayaç
  if (frame_son_tekrar < DEBOUNCE_FRAME) frame_son_tekrar++;
  if (hareket_basarili && frame_son_tekrar >= DEBOUNCE_FRAME) {
    reps++;
    frame_son_tekrar = 0;
    const hedef = PLAN[ix].hedef;
    // UI güncelle
    repsEl.textContent = reps;
    barEl.style.width = `${Math.min(100, Math.round((reps/hedef)*100))}%`;
    infoEl.textContent = `Tetik: ${PLAN[ix].ad} (+1)`;

    if (reps >= hedef) {
      reps = 0;
      nextExerciseAuto();
    }
  }

  // anlık el durumu göstergeleri (sadece görsel)
  // burada açık/kapalı durumunu son elde edilen lm'e göre tahmini göstereceğiz
  let leftOpen=false, rightOpen=false;
  if (handsRes?.landmarks?.length && handsRes.handedness) {
    for (let i=0;i<handsRes.landmarks.length;i++){
      const lm = handsRes.landmarks[i];
      const handed = handsRes.handedness[i]?.[0]?.categoryName || "";
      const open = elAcikMi(lm);
      if (handed === "Left") rightOpen = open;   // aynalı akış
      if (handed === "Right") leftOpen  = open;
    }
  }
  LstateEl.textContent = leftOpen ? "Açık" : "Kapalı";
  RstateEl.textContent = rightOpen ? "Açık" : "Kapalı";

  requestAnimationFrame(tick);
}

// ---------------- Events ----------------
btnStart.addEventListener("click", async () => {
  btnStart.disabled = true;
  statusEl.textContent = "Kamera başlatılıyor..."; statusEl.className = "pill warn";
  diagEl.textContent = "";
  try {
    await startCam();             // kullanıcı gesture'ı -> izin prompt'u burada çıkmalı
    await initModels();           // el + yüz + pose modelleri
    // plan başlat
    ix = 0;
    referans_yukseklik = null; calib_count = 0; son_yukseklikler = [];
    state.oturukalk = false;
    resetExercise();
    setExerciseUI();
    statusEl.textContent = "Kayıt başladı"; statusEl.className = "pill ok";
    running = true; tick();
  } catch (e) {
    console.error(e);
    statusEl.textContent = "Hata"; statusEl.className = "pill bad";
    infoEl.textContent = "Kamera/model açılamadı.";
    diagEl.textContent = "Detay: " + (e?.message || e);
    btnStart.disabled = false;
  }
});

btnReset.addEventListener("click", () => {
  resetExercise();
  infoEl.textContent = "Sayaç sıfırlandı.";
});
