#!/usr/bin/env python3
"""Sintetiza efectos de sonido deterministas para la composición (sin bancos externos ni licencias):
  whoosh.wav : ruido rosa filtrado con barrido de frecuencia y envolvente (0.45 s)
  click.wav  : transitorio corto con resonancia a 1.8 kHz (0.09 s)
  pop.wav    : golpe grave con pitch descendente para el final de un contador (0.18 s)
  tick.wav   : clic muy corto para pasos de contador (0.03 s)
Uso: sintetizar_sfx.py carpeta_salida/
"""
import sys, os, numpy as np
from scipy import signal
from scipy.io import wavfile
SR = 48000
rng = np.random.default_rng(7)

def env(n, a, d, s=0.0, r=None):
    """ADSR simple en muestras."""
    r = n - a - d if r is None else r
    e = np.zeros(n); e[:a] = np.linspace(0, 1, a); e[a:a+d] = np.linspace(1, s, d); e[a+d:] = np.linspace(s, 0, n-a-d)
    return e

def whoosh(dur=0.45):
    n = int(SR*dur); t = np.arange(n)/SR
    ruido = rng.standard_normal(n)
    # ruido rosa aproximado
    b, a = signal.butter(1, 400/(SR/2), 'low'); rosa = signal.lfilter(b, a, ruido) + 0.3*ruido
    # pasabanda cuyo centro barre de 300 Hz a 4 kHz y vuelve (whoosh clásico)
    out = np.zeros(n); bloque = 480
    for i in range(0, n, bloque):
        f = 300 + 3700*np.sin(np.pi*min(i/n, 1.0))
        bb, aa = signal.butter(2, [max(f*0.6, 50)/(SR/2), min(f*1.6, 20000)/(SR/2)], 'band')
        out[i:i+bloque] = signal.lfilter(bb, aa, rosa[i:i+bloque])
    out *= env(n, int(0.12*n), int(0.5*n), 0.4, int(0.38*n))
    return out/np.abs(out).max()*0.8

def click(dur=0.09):
    n = int(SR*dur); t = np.arange(n)/SR
    cuerpo = np.sin(2*np.pi*1800*t)*np.exp(-t*90) + 0.5*np.sin(2*np.pi*3200*t)*np.exp(-t*160)
    golpe = rng.standard_normal(n)*np.exp(-t*600)*0.6
    out = cuerpo + golpe
    return out/np.abs(out).max()*0.9

def pop(dur=0.18):
    n = int(SR*dur); t = np.arange(n)/SR
    f = 320*np.exp(-t*18) + 80
    fase = 2*np.pi*np.cumsum(f)/SR
    out = np.sin(fase)*np.exp(-t*22) + 0.2*rng.standard_normal(n)*np.exp(-t*300)
    return out/np.abs(out).max()*0.9

def tick(dur=0.03):
    n = int(SR*dur); t = np.arange(n)/SR
    out = np.sin(2*np.pi*2400*t)*np.exp(-t*300) + rng.standard_normal(n)*np.exp(-t*900)*0.4
    return out/np.abs(out).max()*0.7

def guardar(nombre, x):
    x = np.concatenate([x, np.zeros(int(SR*0.02))])  # cola de silencio
    wavfile.write(nombre, SR, (x*32767).astype(np.int16)); print(nombre, f"{len(x)/SR:.3f} s")

if __name__ == "__main__":
    d = sys.argv[1]; os.makedirs(d, exist_ok=True)
    guardar(os.path.join(d, "whoosh.wav"), whoosh()); guardar(os.path.join(d, "click.wav"), click())
    guardar(os.path.join(d, "pop.wav"), pop()); guardar(os.path.join(d, "tick.wav"), tick())

def intro(dur=0.9):
    """Campanita de bici: un solo 'ding'. Golpe metálico breve + parciales inarmónicos de campana
    (f, 2.0f, 2.76f, 3.4f) con decaimientos distintos y un ligero batido para el brillo."""
    n = int(SR*dur); t = np.arange(n)/SR; f0 = 2250.0
    partes = [(1.0, 1.0, 5.0), (0.55, 2.0, 7.0), (0.35, 2.76, 9.0), (0.2, 3.4, 12.0), (0.5, 1.004, 5.5)]  # amplitud, múltiplo, decaimiento
    out = sum(a*np.sin(2*np.pi*f0*m*t)*np.exp(-t*d) for a, m, d in partes)
    golpe = rng.standard_normal(n)*np.exp(-t*900)*0.8
    b, a = signal.butter(2, 1500/(SR/2), 'high'); golpe = signal.lfilter(b, a, golpe)
    out = out + golpe
    out[:int(0.002*SR)] *= np.linspace(0, 1, int(0.002*SR))
    return out/np.abs(out).max()*0.9

if __name__ == "__main__" and len(sys.argv) > 1:
    guardar(os.path.join(sys.argv[1], "intro.wav"), intro())
