# Handoff — sesión del 20 nov 2026

## Qué es este proyecto
Recrear el sistema de edición automática de shorts de Charlie Sebastian que construyó un editor
profesional con Claude Code: Notion dispara → editor (agente) corta y compone → auditor revisa con
`pendientes.md` → render 7 CTAs → dashboard, Telegram, Drive, Blotato.
Leer en este orden: `docs/00-analisis-y-fases.md`, `docs/01-decisiones-tecnicas.md`.

## Decisiones ya tomadas (no reabrir)
- Motor de composición: **Hyperframes** (no Remotion). Cortes y concat: FFmpeg.
- **Dónde cortar lo decide la señal, no el transcript.** Validado con datos: Whisper asignó pausas
  de 2 s a palabras vecinas (92–93 % de la "palabra" era silencio).
- Capa B del auditor: **Essentia** (DiscontinuityDetector principal) + métrica propia "voz a ambos
  lados del corte". Validada con voz real: cero falsos positivos, acierto exacto en cortes sucios.
- Transcripción: backends intercambiables en `pipeline/transcribir.py` (`whisper` local y
  `assemblyai` API). La intención es usar **AssemblyAI** en producción.

## Qué hay en el repo
| Ruta | Qué es | Estado |
|---|---|---|
| `prototipos/essentia-cortes/` | Prototipo del auditor de señal + README con resultados | Validado |
| `prototipos/editor-pausas/` | Editor mínimo por energía: encuentra pausas, acorta, EDL JSON | Validado |
| `pipeline/transcribir.py` | Transcriptor con backends whisper / assemblyai | whisper OK, assemblyai sin probar |

## Estado del entorno de nube `edicion-mate`
- Hosts permitidos: huggingface.co y sus CDN, api.assemblyai.com.
- Variable de entorno `ASSEMBLYAI_API_KEY` guardada por el usuario (la sesión anterior no la veía
  porque se creó después de arrancar). **Esta sesión nueva debería verla.**
- El contenedor es fresco: no hay `.venv`, ni modelos, ni audios de prueba.

## Primera tarea de esta sesión
1. Preparar entorno:
   ```bash
   apt-get update -q && apt-get install -y -q espeak-ng
   python3 -m venv .venv && . .venv/bin/activate
   pip install -r prototipos/essentia-cortes/requirements.txt faster-whisper requests
   ```
2. Verificar que `ASSEMBLYAI_API_KEY` existe (sin imprimir su valor).
3. Pedir al usuario que suba de nuevo las dos notas de voz (.ogg de WhatsApp): nota 1 ("El día de
   hoy, 20 de noviembre...") y nota 2 ("Segunda prueba de audio... espaciados..."), que tiene tres
   pausas largas a propósito (2.5 s, 2.0 s, 1.9 s).
4. Transcribir con `python pipeline/transcribir.py nota2.ogg --backend assemblyai`.
   - El backend usa el encabezado `authorization: <llave>` sin "Bearer"; si da 401, probar con
     prefijo Bearer en `pipeline/transcribir.py` y anotar cuál acepta AssemblyAI v2.
5. Comparar tiempos por palabra AssemblyAI vs Whisper en las pausas largas de la nota 2
   (Whisper: 'esta' 4.12–6.26 s y 'para' 8.82–11.56 s, casi todo silencio). Pregunta a responder:
   ¿AssemblyAI respeta los bordes reales de palabra o también estira sobre las pausas?
6. Probar `disfluencies=True` (muletillas) y ver si aparecen "eh", "mm", etc.
7. Documentar resultados en `prototipos/editor-pausas/README.md` y commitear.

## Pendientes del lado del usuario (ya pedidos, aún sin respuesta)
- Audio o video de Charlie, idealmente con una frase donde baje la voz al final.
- Un raw con su versión final editada, para extraer el criterio editorial.
- Sistema operativo y GPU de la máquina de producción.

## Reglas de trabajo que el usuario espera
- Explicar despacio y paso a paso cuando se trata de configuraciones de UI.
- Entregar archivos de audio editados cuando se edita algo, no solo describirlo.
- Commitear y pushear a la rama `claude/charming-planck-lmkxqj` conforme se avanza.
