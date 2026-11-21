# Pendientes — llave de verde — IMG_7889_t12_3s_chromakey_alfa.webm
Veredicto: RECHAZADO
Bloqueantes: 0 · Mayores: 1 · Menores: 0

## P-01 · MAYOR · 00:12.000–00:15.000
Criterio: la máscara de la llave no parpadea (tasa de conmutación ≤ 2 % por píxel)
Evidencia: zona x 0–240, y 1120–1280 (1080x1920): conmutación máx. 10.1 % por frame; verde en la zona a distancia p95 0.095 del clave, umbral actual 0.08, necesario 0.11, techo 0.141
Acción: llave por zona: mascara_sombras.py y chromakey 0.13 dentro de la máscara (techo 0.141 por el negro de la ropa); no subir el global
Estado: abierto
