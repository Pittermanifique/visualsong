import pyaudio
import numpy as np
import pyqtgraph as pg
from pyqtgraph.Qt import QtCore, QtGui, QtWidgets

# 1. Paramètres
FORMAT   = pyaudio.paInt16
CHANNELS = 1
RATE     = 44100
CHUNK    = 1024

# 2. Initialisation PyAudio
p = pyaudio.PyAudio()
stream = p.open(format=FORMAT,
                channels=CHANNELS,
                rate=RATE,
                input=True,
                frames_per_buffer=CHUNK)

# 3. Préparation de la fenêtre PyQtGraph
app = QtWidgets.QApplication([])
win = pg.GraphicsLayoutWidget(show=True, title="Spectre audio")
plot = win.addPlot()
plot.setLogMode(x=False, y=False)
curve = plot.plot(pen='y')
plot.setXRange(20, RATE/2)
plot.setLabel('bottom', 'Fréquence', units='Hz')
plot.setLabel('left', 'Amplitude')

freqs = np.fft.rfftfreq(CHUNK, 1.0/RATE)

# 4. Fonction de mise à jour
def update():
    data = stream.read(CHUNK, exception_on_overflow=False)
    audio = np.frombuffer(data, dtype=np.int16).astype(np.float32)
    audio /= np.iinfo(np.int16).max

    spectrum = np.abs(np.fft.rfft(audio))
    spectrum /= np.max(spectrum)
    curve.setData(freqs, spectrum)

# 5. Timer pour appel périodique
timer = QtCore.QTimer()
timer.timeout.connect(update)
timer.start(50)  # rafraîchissement toutes les 50 ms

# 6. Lancement de l’app
if __name__ == '__main__':
    QtWidgets.QApplication.instance().exec()

# 7. Nettoyage après fermeture
stream.stop_stream()
stream.close()
p.terminate()
