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
    """'Tin' de arranque con zoom: barrido ascendente de 0.45 s (ruido + seno) que remata en una campanita."""
    n = int(SR*dur); t = np.arange(n)/SR
    n1 = int(SR*0.45); t1 = t[:n1]
    f = 220 + (1800-220)*(t1/0.45)**2                      # subida acelerada (sensación de zoom)
    fase = 2*np.pi*np.cumsum(f)/SR
    barrido = 0.5*np.sin(fase)*np.linspace(0.2, 1, n1)
    ruido = rng.standard_normal(n1)
    b, a = signal.butter(2, [800/(SR/2), 6000/(SR/2)], 'band'); ruido = signal.lfilter(b, a, ruido)*np.linspace(0, 0.5, n1)**2
    t2 = t[n1:] - 0.45
    campana = (np.sin(2*np.pi*1760*t2)*np.exp(-t2*9) + 0.6*np.sin(2*np.pi*2640*t2)*np.exp(-t2*14) + 0.3*np.sin(2*np.pi*4400*t2)*np.exp(-t2*20))
    out = np.concatenate([barrido + ruido, 0.9*campana])
    return out/np.abs(out).max()*0.9

if __name__ == "__main__" and len(sys.argv) > 1:
    guardar(os.path.join(sys.argv[1], "intro.wav"), intro())
