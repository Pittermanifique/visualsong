import sys
import time
import serial
import argparse
import numpy as np
import pyaudiowpatch as pa
from scipy.signal import butter, lfilter

def parse_args():
    p = argparse.ArgumentParser(
        description="Détection de kicks via spectral overflow et envoi série"
    )

    # Port série
    p.add_argument('--port',     type=str,   default='COM7',
                   help="Port COM pour l'ESP32")
    p.add_argument('--baudrate', type=int,   default=115200,
                   help="Baudrate du port série")
    p.add_argument('--timeout',  type=float, default=1.0,
                   help="Timeout pour le port série (s)")

    # Audio
    p.add_argument('--rate',  type=int, default=44100,
                   help="Fréquence d'échantillonnage")
    p.add_argument('--chunk', type=int, default=512,
                   help="Taille de la fenêtre d’analyse")
    p.add_argument('--hop',   type=int, default=None,
                   help="Pas de lecture (par défaut chunk//2)")

    # Spectral Flux
    p.add_argument('--hist-sec',   type=float, default=1.0,
                   help="Durée de l'historique en secondes")

    p.add_argument('--k-high',     type=float, default=1.3,
                   help="""Multiplicateur seuil haut.
                   Contrôle la sensibilité aux pics :
                   • Plus K_HIGH est grand → seuls les flux très supérieurs à la moyenne déclenchent un kick.
                   • Plus K_HIGH est petit → même de petits accroissements peuvent déclencher.""")

    p.add_argument('--k-low',      type=float, default=0.8,
                   help="""Multiplicateur seuil bas (hystérésis) :
                   Détermine quand la détection se réarme.
                   • Plus K_LOW est proche de K_HIGH → hystérésis étroite (risque de rebonds).
                   • Plus K_LOW est faible → réarmement retardé, moins de fausses re-détections.""")

    p.add_argument('--min-interval', type=float, default=0.18,
                   help="Intervalle minimal entre kicks (s)")
    p.add_argument('--rms-th',       type=float, default=0.01,
                   help="Seuil RMS pour gate")
    p.add_argument('--abs-flux-th',  type=float, default=0.05,
                   help="Seuil absolu de spectral flux")

    # Filtre passe-bande
    p.add_argument('--bp-low',   type=float, default=40.0,
                   help="Fréquence basse du filtre (Hz)")
    p.add_argument('--bp-high',  type=float, default=80.0,
                   help="Fréquence haute du filtre (Hz)")
    p.add_argument('--bp-order', type=int,   default=1,
                   help="Ordre du filtre passe-bande")

    return p.parse_args()


def main():
    args = parse_args()

    # 1. Init port série
    ser = serial.Serial(
        port=args.port,
        baudrate=args.baudrate,
        timeout=args.timeout
    )

    # 2. Paramètres audio
    RATE  = args.rate
    CHUNK = args.chunk
    HOP   = args.hop if args.hop else CHUNK // 2

    # 3. Paramètres spectral flux
    HIST_FRAMES      = int(args.hist_sec / (HOP / RATE))

    # K_HIGH: sensibilité aux pics.
    #   • Plus grand → moins de déclenchements parasites, seuls les gros pics passent.
    #   • Plus petit → plus de sensibilité, même petites surélèvations déclenchent.
    K_HIGH           = args.k_high

    # K_LOW: seuil bas pour l’hystérésis.
    #   • Plus proche de K_HIGH → hystérésis étroite, risque de rebonds.
    #   • Plus faible → réarmement retardé, évite fausses re-détections successives.
    K_LOW            = args.k_low

    MIN_INTERVAL     = args.min_interval
    RMS_THRESHOLD    = args.rms_th
    ABS_FLUX_THRESHOLD = args.abs_flux_th

    # 4. Passe-bande
    b_bp, a_bp = butter(args.bp_order,[args.bp_low/(RATE/2), args.bp_high/(RATE/2)],btype='band')

    # États pour la détection
    prev_spectrum  = np.zeros(CHUNK//2 + 1, dtype=np.float32)
    flux_history   = []
    last_beat_time = 0.0
    is_armed       = True

    # 5. Initialisation loopback WASAPI
    p       = pa.PyAudio()
    wasapi  = p.get_host_api_info_by_type(pa.paWASAPI)
    out_dev = p.get_device_info_by_index(wasapi['defaultOutputDevice'])
    loop_dev = next(
        (d for d in p.get_loopback_device_info_generator()
         if out_dev['name'] in d['name']),
        None
    )
    if loop_dev is None:
        print("Appareil loopback introuvable.")
        sys.exit(1)

    stream = p.open(
        format            = pa.paInt16,
        channels          = loop_dev['maxInputChannels'],
        rate              = int(loop_dev['defaultSampleRate']),
        input             = True,
        frames_per_buffer = HOP,
        input_device_index= loop_dev['index']
    )

    # 6. Boucle de lecture / détection
    buffered = np.zeros((CHUNK, loop_dev['maxInputChannels']), dtype=np.float32)
    offset   = 0

    print("Démarrage de la détection… Ctrl+C pour stopper.")
    try:
        while True:
            data = stream.read(HOP, exception_on_overflow=False)
            chunk = (np.frombuffer(data, np.int16).astype(np.float32)
                     / np.iinfo(np.int16).max)
            chunk = chunk.reshape(-1, loop_dev['maxInputChannels'])

            buffered[offset:offset+HOP] = chunk
            offset = (offset + HOP) % CHUNK
            mono   = buffered.mean(axis=1)

            rms = np.sqrt(np.mean(mono**2))
            now = time.time()

            if rms < RMS_THRESHOLD:
                is_armed = True
                ser.write(b"0\n")
                continue

            mono_f   = lfilter(b_bp, a_bp, mono)
            spectrum = np.abs(np.fft.rfft(mono_f))
            flux     = np.sum(np.maximum(spectrum - prev_spectrum, 0))
            prev_spectrum = spectrum

            flux_history.append(flux)
            if len(flux_history) > HIST_FRAMES:
                flux_history.pop(0)

            mu, sigma   = np.mean(flux_history), np.std(flux_history)
            high_thresh = mu + K_HIGH * sigma
            low_thresh  = mu + K_LOW  * sigma
            interval_ok = (now - last_beat_time) > MIN_INTERVAL

            # 1) Kick valide : seuils OK, armé ET intervalle écoulé
            if flux > high_thresh \
                    and flux > ABS_FLUX_THRESHOLD \
                    and is_armed \
                    and interval_ok:

                ser.write(b"1\n")
                last_beat_time = now  # on met à jour le timing
                is_armed = False  # on désarme jusqu'au prochain rearm

            # 2) Flux au-dessus des seuils mais trop tôt : on n'arme pas,
            #    on renvoie simplement 0 si vous voulez notifier
            elif flux > high_thresh \
                    and flux > ABS_FLUX_THRESHOLD \
                    and is_armed \
                    and not interval_ok:

                ser.write(b"0\n")
                # is_armed reste True → on pourra retenter dès que MIN_INTERVAL sera passé

            # 3) Réarmement : flux retombé sous le seuil bas ET intervalle écoulé
            elif flux < low_thresh and interval_ok:
                is_armed = True
                ser.write(b"0\n")


    except KeyboardInterrupt:
        print("\nArrêt demandé.")
    finally:
        stream.stop_stream()
        stream.close()
        p.terminate()
        ser.close()
        print("Terminé.")


if __name__ == '__main__':
    main()
