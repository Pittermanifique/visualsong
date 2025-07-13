import sys
import time
import serial
import numpy as np
import pyaudiowpatch as pa
import pyqtgraph as pg
from PyQt6.QtWidgets import QApplication,QGraphicsRectItem
from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QBrush, QColor
from scipy.signal import butter, lfilter

#initialisation serie pour la comunication avec l'esp 32
ser = serial.Serial(port="COM7", baudrate=115200)

# 1. Paramètres audio
RATE   = 44100
CHUNK  = 512               # moitié de la taille précédente → ~11.6 ms/frame
HOP    = CHUNK // 2        # 50% overlap → ~5.8 ms de recouvrement

# 2. Paramètres de détection via Spectral Flux
HIST_SEC       = 1.0
HISTORY_FRAMES = int(HIST_SEC / (HOP / RATE))  # env. 171 frames
K_HIGH         = 1.3
K_LOW          = 0.8
MIN_INTERVAL   = 0.18      # 180 ms entre deux beats min

# Seuil RMS minimal pour autoriser la détection (ajuster selon votre micro / loopback)
RMS_THRESHOLD = 0.01

# Seuil absolu minimal de flux spectral
ABS_FLUX_THRESHOLD = 0.05

# Buffers et états globaux
prev_spectrum  = np.zeros(CHUNK//2 + 1, dtype=np.float32)
flux_history   = []
intervals      = []
last_beat_time = 0.0
is_armed       = True     # pour l’hystérésis

# 3. Filtre passe-bande pour isoler basses & kicks
BP_LOW, BP_HIGH, BP_ORDER = 40, 80, 1
b_bp, a_bp = butter(BP_ORDER,[BP_LOW/(RATE/2), BP_HIGH/(RATE/2)],btype='band')

def detect_beat(now, flux, high, abs_threshold):
    global intervals, last_beat_time
    if (flux > high and flux > abs_threshold and (now - last_beat_time) > MIN_INTERVAL):
        if last_beat_time != 0.0:
            interval = now - last_beat_time
            intervals.append(interval)
            if len(intervals) > 8:
                intervals.pop(0)
            bpm = 60.0 / (sum(intervals) / len(intervals))
            print(f"KICK détecté ! BPM : {bpm:.1f}")
        last_beat_time = now
        return True
    return False


# 4. Initialisation loopback WASAPI
p       = pa.PyAudio()
wasapi  = p.get_host_api_info_by_type(pa.paWASAPI)
out_dev = p.get_device_info_by_index(wasapi['defaultOutputDevice'])

loop_dev = next((d for d in p.get_loopback_device_info_generator()
                 if out_dev['name'] in d['name']), None)
if loop_dev is None:
    raise RuntimeError("Device loopback introuvable.")

channels = loop_dev['maxInputChannels']
fs       = int(loop_dev['defaultSampleRate'])
print(f"Loopback sur '{loop_dev['name']}', index={loop_dev['index']} • canaux={channels}")

stream = p.open(format            = pa.paInt16,
                channels          = channels,
                rate              = fs,
                input             = True,
                frames_per_buffer = HOP,                 # on lit HOP à chaque itération
                input_device_index= loop_dev['index'])

# 5. Préparation de la fenêtre PyQtGraph
app  = QApplication(sys.argv)
win  = pg.GraphicsLayoutWidget(show=True, title="Spectre Audio")
win.resize(800,400)
plot = win.addPlot(title="Spectre en temps réel")
plot.setXRange(20, RATE/2, padding=0)
plot.setYRange(0, 20)
plot.showGrid(x=True, y=True, alpha=0.3)
plot.setLabel('bottom','Fréquence',units='Hz')
plot.setLabel('left','Amplitude')

beat = pg.QtWidgets.QGraphicsRectItem(0, 0, 1000, 5)
beat.setBrush(QBrush(QColor("red")))
beat.setPos(20000, 10)  # X=1000 Hz, Y=10 dB
plot.addItem(beat)


freqs = np.fft.rfftfreq(CHUNK, 1.0/RATE)
curve = plot.plot(freqs, np.zeros_like(freqs), pen=pg.mkPen(color='red', width=2))

# 6. Fonction de mise à jour
buffered = np.zeros((CHUNK, channels), dtype=np.float32)
offset   = 0

def update_spectrum():
    global prev_spectrum, flux_history, buffered, offset, is_armed

    # 1. Lecture et mix
    data = stream.read(HOP, exception_on_overflow=False)
    chunk = (np.frombuffer(data, np.int16).astype(np.float32)/ np.iinfo(np.int16).max)
    chunk = chunk.reshape(-1, channels)
    buffered[offset:offset+HOP] = chunk
    offset = (offset + HOP) % CHUNK
    mono  = buffered.mean(axis=1)

    # 2. Gate RMS
    rms = np.sqrt(np.mean(mono**2))
    if rms < RMS_THRESHOLD:
        # Si trop silencieux, on arrête là
        # On peut aussi réarmer l’hystérésis pour reprendre proprement
        is_armed = True
        # Mise à jour visuelle du spectre sans détection
        spectrum_vis = np.abs(np.fft.rfft(mono))
        curve.setData(freqs, spectrum_vis)
        return

    # 3. Filtrage passe-bande + spectre
    mono_f   = lfilter(b_bp, a_bp, mono)
    spectrum = np.abs(np.fft.rfft(mono_f))

    # 4. Calcul du Spectral Flux
    flux = np.sum(np.maximum(spectrum - prev_spectrum, 0))
    prev_spectrum = spectrum

    # 5. Historique & seuils adaptatifs
    flux_history.append(flux)
    if len(flux_history) > HISTORY_FRAMES:
        flux_history.pop(0)
    mu, sigma = np.mean(flux_history), np.std(flux_history)
    high = mu + K_HIGH * sigma
    low  = mu + K_LOW  * sigma

    now = time.time()
    # 6. Détection avec double condition
    if (flux > high
            and flux > ABS_FLUX_THRESHOLD
            and is_armed
            and (now - last_beat_time) > MIN_INTERVAL):

        ok_kick = detect_beat(now, flux, high, ABS_FLUX_THRESHOLD)

        if ok_kick:
            beat.setBrush(QBrush(QColor("green")))  # KICK confirmé
            ser.write(b"1\n")
        else:
            beat.setBrush(QBrush(QColor("red")))  # KICK non validé
            ser.write(b"0\n")

        is_armed = False

    elif (flux < low and (now - last_beat_time) > MIN_INTERVAL):
        is_armed = True
        beat.setBrush(QBrush(QColor("red")))  # trop faible, reset
        ser.write(b"0\n")


    # 7. Mise à jour spectre visuel
    spectrum_vis = np.abs(np.fft.rfft(mono))
    curve.setData(freqs, spectrum_vis)


# 7. Lancement du timer Qt
timer = QTimer()
timer.timeout.connect(update_spectrum)
timer.start(16)   # ≃60 FPS → 16 ms

# 8. Boucle Qt
if __name__ == '__main__':
    sys.exit(app.exec())

# 9. Nettoyage
stream.stop_stream()
stream.close()
p.terminate()
