import cv2
import mediapipe as mp
import numpy as np
from math import dist
from PIL import ImageFont, ImageDraw, Image
import time
from collections import deque
 
# ---------------------------
# CONFIG
# ---------------------------
FONT_PATH = "C:/Windows/Fonts/arial.ttf"
FONT_SIZE = 28
CALIBRATION_FRAMES = 60  # ilk kaç frame'i referans ayakta durma yüksekliği için toplayalım
SMOOTHING_WINDOW = 5     # yükseklik ortalaması için pencere
DEBOUNCE_FRAME = 10
 
# Dinamik eşik oranları (referans_yukseklik'e göre)
OTURMA_ORANI = 0.75   # referans yüksekliğin yüzde kaçı altına inince oturma kabul edilsin
KALKMA_ORANI = 0.92   # referans yüksekliğin yüzde kaçı üzerine çıkınca kalkma kabul edilsin
 
# Diz açısı eşikleri (derece)
DIZ_OTURMA_ACI = 110   # diz açısı bu değerin altına inerse dizlerin büküldüğü kabul edilsin
DIZ_KALKMA_ACI = 150   # diz açısı bu değerin üzerine çıkarsa dikleşme kabul edilsin
 
# ---------------------------
# Mediapipe setup
# ---------------------------
mp_hands = mp.solutions.hands
mp_pose = mp.solutions.pose
mp_face_mesh = mp.solutions.face_mesh
mp_drawing = mp.solutions.drawing_utils
 
hands = mp_hands.Hands(max_num_hands=2, min_detection_confidence=0.6, min_tracking_confidence=0.6)
pose = mp_pose.Pose(min_detection_confidence=0.6, min_tracking_confidence=0.6)
face_mesh = mp_face_mesh.FaceMesh(max_num_faces=1, min_detection_confidence=0.6, min_tracking_confidence=0.6)
 
# Font
font = ImageFont.truetype(FONT_PATH, FONT_SIZE)
 
# Exercise list (orijinal)
egzersizler = [
    {"ad": "Right Hand Open - Close", "hedef": 10},
    {"ad": "Left Hand Open - Close", "hedef": 10},
    {"ad": "Mouth Open - Close", "hedef": 5},
    {"ad": "Right Eye Blink", "hedef": 5},
    {"ad": "Left Eye Blink", "hedef": 5},
    {"ad": "Right Leg Extension", "hedef": 8},
    {"ad": "Left Leg Extension", "hedef": 8},
    {"ad": "Right Arm Raise", "hedef": 5},
    {"ad": "Left Arm Raise", "hedef": 5},
    {"ad": "Sit Down, Stand Up", "hedef": 8}
]
 
mevcut_index = 0
tekrar_sayisi = 0
frame_son_tekrar = DEBOUNCE_FRAME
 
# Durum değişkenleri (debounce için)
parmak_acik_sag = False
parmak_acik_sol = False
agiz_acik = False
goz_kirpma_sag = False
goz_kirpma_sol = False
bacak_acik_sag = False
bacak_acik_sol = False
oturukalk = False
kol_kaldirma_sag = False
kol_kaldirma_sol = False
 
# Oturup-kalkma için dinamik referans ve smoothing
referans_yukseklik = None
calib_count = 0
son_yukseklikler = deque(maxlen=SMOOTHING_WINDOW)
 
# ---------------------------
# Yardımcı fonksiyonlar
# ---------------------------
 
def mesafe(a, b):
    return dist((a.x, a.y), (b.x, b.y))
 
 
def aci_hesapla(a, b, c):
    """b noktasında açıyı (a-b-c) derece cinsinden döndürür."""
    ba = np.array([a.x - b.x, a.y - b.y])
    bc = np.array([c.x - b.x, c.y - b.y])
    denom = (np.linalg.norm(ba) * np.linalg.norm(bc))
    if denom == 0:
        return 180.0
    cosang = np.dot(ba, bc) / denom
    cosang = np.clip(cosang, -1.0, 1.0)
    return np.degrees(np.arccos(cosang))
 
 
def agiz_acma_kapama(lm):
    ust_dudak = lm[13]
    alt_dudak = lm[14]
    mes = dist((ust_dudak.x, ust_dudak.y), (alt_dudak.x, alt_dudak.y))
    return mes > 0.03
 
 
def goz_kirpma(lm, sag=True):
    if sag:
        ust = lm[159]
        alt = lm[145]
    else:
        ust = lm[386]
        alt = lm[374]
    mes = dist((ust.x, ust.y), (alt.x, alt.y))
    return mes < 0.015
 
 
def bacak_acma(landmarks, sag=True):
    if sag:
        hip = landmarks[24]
        ankle = landmarks[28]
    else:
        hip = landmarks[23]
        ankle = landmarks[27]
    yan_mesafe = abs(ankle.x - hip.x)
    return yan_mesafe > 0.15
 
 
# ---------------------------
# Geliştirilmiş oturup_kalkma fonksiyonu
# ---------------------------
 
def oturup_kalkma(landmarks):

    global referans_yukseklik, calib_count, son_yukseklikler, oturukalk
 
    # Gerekli anahtar noktalar
    # landmarks indeksleri: 0 - nose (baş referansı), 23 - left_hip, 24 - right_hip
    # 25 - left_knee, 26 - right_knee, 27 - left_ankle, 28 - right_ankle
    try:
        bas = landmarks[0]
        ayak_sag = landmarks[28]
        ayak_sol = landmarks[27]
    except Exception:
        return False
 
    ayak_ort_y = (ayak_sag.y + ayak_sol.y) / 2.0
    yukseklik = abs(bas.y - ayak_ort_y)
 
    # Smoothing
    son_yukseklikler.append(yukseklik)
    yukseklik_ortalama = sum(son_yukseklikler) / len(son_yukseklikler)
 
    # Calibration (ilk birkaç frame'de referans ayakta yüksekliğini al)
    if referans_yukseklik is None and calib_count < CALIBRATION_FRAMES:
        # Sadece pose varsa say
        calib_count += 1
        # Biriken ortalama'ları kullan
        if calib_count == CALIBRATION_FRAMES:
            # referans olarak medyan veya ortalama al (ayakta durulmuş varsayımı)
            referans_yukseklik = np.median(list(son_yukseklikler)) if len(son_yukseklikler) > 0 else yukseklik
            # Eğer referans çok küçükse (kamera çok yakın) bunu kabul etme, biraz artır
            if referans_yukseklik < 0.2:
                referans_yukseklik = max(referans_yukseklik, 0.25)
        return False
 
    # Eğer referans ayarlanmadıysa hemen False dön
    if referans_yukseklik is None:
        return False
 
    oturma_esigi = referans_yukseklik * OTURMA_ORANI
    kalkma_esigi = referans_yukseklik * KALKMA_ORANI
 
    # Diz açısını hesapla (her iki bacak için)
    try:
        # Sağ: hip(24), knee(26), ankle(28)
        hip_r = landmarks[24]
        knee_r = landmarks[26]
        ankle_r = landmarks[28]
        aci_r = aci_hesapla(hip_r, knee_r, ankle_r)
    except Exception:
        aci_r = 180.0
 
    try:
        # Sol: hip(23), knee(25), ankle(27)
        hip_l = landmarks[23]
        knee_l = landmarks[25]
        ankle_l = landmarks[27]
        aci_l = aci_hesapla(hip_l, knee_l, ankle_l)
    except Exception:
        aci_l = 180.0
 
    # Diz açılarından küçük olanı al (dizlerden biri bükülürse oturma olabilir)
    diz_acisi_min = min(aci_r, aci_l)
 
    # Karar (hem yükseklik hem de diz açısı kombinasyonu)
    # Oturma: ortalama yükseklik < oturma_esigi veya diz açısı < DIZ_OTURMA_ACI
    # Kalkma: ortalama yükseklik > kalkma_esigi ve diz açısı > DIZ_KALKMA_ACI
 
    if not oturukalk and (yukseklik_ortalama < oturma_esigi or diz_acisi_min < DIZ_OTURMA_ACI):
        oturukalk = True
    elif oturukalk and (yukseklik_ortalama > kalkma_esigi and diz_acisi_min > DIZ_KALKMA_ACI):
        oturukalk = False
        return True
 
    return False
 
 
def kol_kaldirma(landmarks, sag=True):
    if sag:
        omuz = landmarks[12]
        el_bil = landmarks[16]
    else:
        omuz = landmarks[11]
        el_bil = landmarks[15]
    return el_bil.y < omuz.y - 0.1
 
 
def hareket_tespit_et(results_hands, results_face, results_pose):
    global parmak_acik_sag, parmak_acik_sol, agiz_acik, goz_kirpma_sag, goz_kirpma_sol
    global bacak_acik_sag, bacak_acik_sol, oturukalk, kol_kaldirma_sag, kol_kaldirma_sol
 
    ad = egzersizler[mevcut_index]["ad"]
 
    # El hareketleri (orijinal mantık)
    if "Right Hand" in ad or "Left Hand" in ad:
        if results_hands.multi_hand_landmarks and results_hands.multi_handedness:
            for hand_landmarks, hand_handedness in zip(results_hands.multi_hand_landmarks, results_hands.multi_handedness):
                lm = hand_landmarks.landmark
                el_tipi = hand_handedness.classification[0].label  # "Right" veya "Left"
                mesafe_parmak = mesafe(lm[8], lm[0])
                acik = mesafe_parmak > 0.25
                kapali = mesafe_parmak < 0.15
 
                if "Left Hand" in ad and el_tipi == "Right":
                    if not parmak_acik_sag and acik:
                        parmak_acik_sag = True
                    elif parmak_acik_sag and kapali:
                        parmak_acik_sag = False
                        return True
 
                elif "Right Hand" in ad and el_tipi == "Left":
                    if not parmak_acik_sol and acik:
                        parmak_acik_sol = True
                    elif parmak_acik_sol and kapali:
                        parmak_acik_sol = False
                        return True
 
    elif ad == "Mouth Open - Close":
        if results_face.multi_face_landmarks:
            lm = results_face.multi_face_landmarks[0].landmark
            agz_durum = agiz_acma_kapama(lm)
            if not agiz_acik and agz_durum:
                agiz_acik = True
            elif agiz_acik and not agz_durum:
                agiz_acik = False
                return True
 
    elif ad == "Right Eye Blink":
        if results_face.multi_face_landmarks:
            lm = results_face.multi_face_landmarks[0].landmark
            kirpma = goz_kirpma(lm, sag=True)
            if not goz_kirpma_sag and kirpma:
                goz_kirpma_sag = True
            elif goz_kirpma_sag and not kirpma:
                goz_kirpma_sag = False
                return True
 
    elif ad == "Left Eye Blink":
        if results_face.multi_face_landmarks:
            lm = results_face.multi_face_landmarks[0].landmark
            kirpma = goz_kirpma(lm, sag=False)
            if not goz_kirpma_sol and kirpma:
                goz_kirpma_sol = True
            elif goz_kirpma_sol and not kirpma:
                goz_kirpma_sol = False
                return True
 
    elif ad == "Right Leg Extension":
        if results_pose.pose_landmarks:
            lm = results_pose.pose_landmarks.landmark
            bacak = bacak_acma(lm, sag=True)
            if not bacak_acik_sag and bacak:
                bacak_acik_sag = True
            elif bacak_acik_sag and not bacak:
                bacak_acik_sag = False
                return True
 
    elif ad == "Left Leg Extension":
        if results_pose.pose_landmarks:
            lm = results_pose.pose_landmarks.landmark
            bacak = bacak_acma(lm, sag=False)
            if not bacak_acik_sol and bacak:
                bacak_acik_sol = True
            elif bacak_acik_sol and not bacak:
                bacak_acik_sol = False
                return True
 
    elif ad == "Right Arm Raise":
        if results_pose.pose_landmarks:
            lm = results_pose.pose_landmarks.landmark
            kol_kaldir = kol_kaldirma(lm, sag=True)
            if not kol_kaldirma_sag and kol_kaldir:
                kol_kaldirma_sag = True
            elif kol_kaldirma_sag and not kol_kaldir:
                kol_kaldirma_sag = False
                return True
 
    elif ad == "Left Arm Raise":
        if results_pose.pose_landmarks:
            lm = results_pose.pose_landmarks.landmark
            kol_kaldir = kol_kaldirma(lm, sag=False)
            if not kol_kaldirma_sol and kol_kaldir:
                kol_kaldirma_sol = True
            elif kol_kaldirma_sol and not kol_kaldir:
                kol_kaldirma_sol = False
                return True
 
    elif ad == "Sit Down, Stand Up":
        if results_pose.pose_landmarks:
            lm = results_pose.pose_landmarks.landmark
            if oturup_kalkma(lm):
                return True
 
    return False
 
 
# ---------------------------
# MAIN LOOP
# ---------------------------
cap = cv2.VideoCapture(0)
 
frame_son_tekrar = DEBOUNCE_FRAME
 
print("Please stand upright for the first 5 seconds for calibration.")
 
while cap.isOpened():
    success, frame = cap.read()
    if not success:
        break
 
    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
 
    results_hands = hands.process(frame_rgb)
    results_face = face_mesh.process(frame_rgb)
    results_pose = pose.process(frame_rgb)
 
    hareket_basarili = hareket_tespit_et(results_hands, results_face, results_pose)
 
    if frame_son_tekrar < DEBOUNCE_FRAME:
        frame_son_tekrar += 1
 
    if hareket_basarili and frame_son_tekrar >= DEBOUNCE_FRAME:
        tekrar_sayisi += 1
        frame_son_tekrar = 0
        hedef = egzersizler[mevcut_index]["hedef"]
 
        if hedef and tekrar_sayisi >= hedef:
            tekrar_sayisi = 0
            mevcut_index += 1
            if mevcut_index >= len(egzersizler):
                print("Tüm egzersizler tamamlandı!")
                mevcut_index = 0
            else:
                print(f"Yeni egzersiz: {egzersizler[mevcut_index]['ad']}")
 
    # ELLERİN, YÜZÜN, VÜCUDUN ÇİZGİLERİ (linearlar)
  
 
    # Siyah metin
    img_pil = Image.fromarray(frame)
    draw = ImageDraw.Draw(img_pil)
    renk = (0, 0, 0)
 
    # Durum bilgileri
    kalibrasyon_durum = f"Calibrate: {calib_count}/{CALIBRATION_FRAMES}" if referans_yukseklik is None else f"Referans: {referans_yukseklik:.3f}"
    draw.text((10, 10), f"Exercise: {egzersizler[mevcut_index]['ad']}", font=font, fill=renk)
    hedef_goster = egzersizler[mevcut_index]['hedef'] if egzersizler[mevcut_index]['hedef'] else "Time"
    draw.text((10, 50), f"Set: {tekrar_sayisi}/{hedef_goster}", font=font, fill=renk)
    draw.text((10, 90), kalibrasyon_durum, font=font, fill=renk)
 
    frame = np.array(img_pil)
 
    cv2.imshow("Exercise tracking", frame)
 
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break
 
cap.release()
cv2.destroyAllWindows()