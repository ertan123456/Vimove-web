import {
  FilesetResolver,
  HandLandmarker
} from "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.8";

const video = document.getElementById("video");
const canvas = document.getElementById("overlay");
const ctx = canvas.getContext("2d");
const btnStart = document.getElementById("btnStart");
const statusEl = document.getElementById("status");
const infoEl = document.getElementById("info");
const fpsEl = document.getElementById("fps");
const LstateEl = document.getElementById("Lstate");
const RstateEl = document.getElementById("Rstate");

canvas.width = 640;
canvas.height = 480;

let handLandmarker;
let running = false;
let lastTime = performance.now(), frameCount = 0;

let leftOpen = false, rightOpen = false;
let leftToggleArmed = false, rightToggleArmed = false;
let leftToggled = false, rightToggled = false;

function dist2D(a, b) {
  const dx = a.x - b.x, dy = a.y - b.y;
  return Math.hypot(dx, dy);
}

function isOpen(landmarks) {
  const tip = landmarks[8];
  const wrist = landmarks[0];
  const d = dist2D(tip, wrist);
  return d > 0.24; // gerekirse 0.22-0.27 aralığında ayarla
}

function sideGuess(landmarks) {
  return landmarks[5].x < 0.5 ? "Left" : "Right";
}

async function initHand() {
  const vision = await FilesetResolver.forVisionTasks(
    "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.8/wasm"
  );
  handLandmarker = await HandLandmarker.createFromOptions(vision, {
    baseOptions: {
      modelAssetPath:
        "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task"
    },
    numHands: 2,
    runningMode: "VIDEO"
  });
}

async function startCam() {
  const stream = await navigator.mediaDevices.getUserMedia({ video: { width: 640, height: 480 } });
  video.srcObject = stream;
  await new Promise(r => video.onloadedmetadata = r);
}

function drawLandmarks(landmarks) {
  ctx.lineWidth = 2;
  for (const lm of landmarks) {
    ctx.beginPath();
    ctx.arc(lm.x * canvas.width, lm.y * canvas.height, 3, 0, Math.PI * 2);
    ctx.stroke();
  }
}

function loop() {
  if (!running) return;
  const now = performance.now();
  frameCount++;
  if (now - lastTime > 1000) {
    fpsEl.textContent = `FPS: ${frameCount}`;
    frameCount = 0; lastTime = now;
  }

  ctx.clearRect(0, 0, canvas.width, canvas.height);
  if (video.readyState >= 2) {
    const results = handLandmarker.detectForVideo(video, now);
    leftToggled = false; rightToggled = false;

    if (results && results.landmarks && results.landmarks.length) {
      for (const lms of results.landmarks) {
        drawLandmarks(lms);

        const open = isOpen(lms);
        const side = sideGuess(lms);

        if (side === "Left") {
          if (open && !leftOpen) { leftOpen = true; leftToggleArmed = true; }
          if (!open && leftOpen) {
            leftOpen = false;
            if (leftToggleArmed) { leftToggled = true; leftToggleArmed = false; }
          }
        } else {
          if (open && !rightOpen) { rightOpen = true; rightToggleArmed = true; }
          if (!open && rightOpen) {
            rightOpen = false;
            if (rightToggleArmed) { rightToggled = true; rightToggleArmed = false; }
          }
        }
      }
    }

    LstateEl.textContent = leftOpen ? "Açık" : "Kapalı";
    RstateEl.textContent = rightOpen ? "Açık" : "Kapalı";
    if (leftToggled || rightToggled) {
      infoEl.textContent = `Tetik: ${leftToggled ? "Sol" : ""} ${rightToggled ? "Sağ" : ""} el “açık→kapalı” yakalandı.`;
      statusEl.textContent = "Oyun çalışıyor";
      statusEl.className = "pill ok";
    }
  }

  requestAnimationFrame(loop);
}

btnStart.addEventListener("click", async () => {
  btnStart.disabled = true;
  statusEl.textContent = "Kamera başlatılıyor...";
  try {
    await startCam();
    await initHand();
    statusEl.textContent = "Kayıt başladı";
    statusEl.className = "pill ok";
    running = true;
    loop();
  } catch (e) {
    console.error(e);
    statusEl.textContent = "Hata: kamera/model";
    statusEl.className = "pill bad";
    btnStart.disabled = false;
  }
});
