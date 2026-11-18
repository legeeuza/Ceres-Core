# Ceres-Core: tablero para el coach (NFL)

Herramienta para el **cuerpo técnico** de un equipo de la NFL. Con datos reales de tracking (posición de cada
jugador 10 veces por segundo) y del scouting de PFF, responde tres preguntas de partido:

1. **¿Qué pasó en esta jugada?** Ves la cancha, a los 22 jugadores, el balón y las rutas de los receptores.
2. **¿Quién está cansado ahora mismo?** Cada jugador recibe un estado físico calculado solo con lo que ha jugado hasta ese momento.
3. **¿A quién cambio y por quién?** La app recomienda sacar, monitorear o mantener a cada jugador y propone un relevo de su misma posición.

Proyecto del Hackathon NFL Big Data Bowl, UNAM. Equipo: Emilio (campo y estado físico) y Kareem (táctica + IA).

---

## Cómo usarlo (coach)

Abre la app y entra a la pestaña **"Tablero y Fatiga"**.

### 1. Revisar una jugada
1. En **Partido…** elige el juego. Solo aparecen los partidos que tienen datos de tracking.
2. En **Jugada…** elige la jugada. Cada opción indica cuarto, reloj, down y yardas por avanzar, y el equipo con el balón.
3. Con el selector de equipo eliges a quién quieres ver, **ofensiva** o **defensiva**. El otro equipo se ve atenuado.
4. Sobre la cancha verás:
   - **Fichas azules (ofensiva) y rojas (defensiva)** con la posición (QB, WR, CB…) y el número del jugador. Pasa el cursor para ver su nombre, su función en la jugada y dónde se alineó.
   - **Rutas**: líneas claras con el recorrido real de los receptores, desde el snap hasta que llega el balón.
   - **Línea amarilla**: línea de golpeo.
   - **Línea punteada azul**: yarda 35 rival, desde donde tu pateador ya tiene rango de gol de campo.
   - **Línea punteada naranja**: yarda 35 propia. Pasada esa línea, el pateador rival ya tiene rango.
5. Mueve la **barra de tiempo** para ver la jugada cuadro por cuadro. El botón **ball_snap** regresa al momento del snap.

### 2. Ver la ficha de un jugador
Haz **clic en cualquier ficha** de la cancha y se abre su ficha debajo:

- **Calificación del partido (0 a 100)**: cómo rindió comparado con jugadores de su misma posición. Las barras indican en qué percentil queda en cada métrica.
- **Stats físicas**: velocidad máxima y promedio, aceleración máxima, segundos del snap a su máxima aceleración, yardas recorridas, sprints y desglose por cuarto.
- **PFF en el partido**: snaps, funciones que cumplió, presiones generadas o permitidas, veces que lo superó su rival y rutas corridas.
- **Fatiga y recomendación**: los motivos de la alerta y el relevo sugerido.
- **Evolución partido a partido**: su calificación en cada partido con datos. Indica si **mejora, se mantiene o empeora** frente al partido anterior (±5 puntos).

### 3. Revisar a todo el plantel
En el bloque **"Stats físicas, cansancio y relevo"**:
1. Elige el partido y el equipo (local o visitante).
2. Activa **Solo alertas** para ver únicamente a los jugadores marcados.
3. Haz clic en una fila para ver sus yardas y sprints por cuarto.
4. En la última columna aparece la **Sugerencia de Cambio / Relevo Recomendado**.

---

## Cómo leer las recomendaciones

| Recomendación | Significa | Qué hacer |
|---|---|---|
| 🔴 **Cambiar** | Rinde por debajo de 40 puntos **y** tiene fatiga probable | Sácalo y mete al relevo sugerido |
| 🟡 **Vigilar** | Rinde bajo **o** muestra fatiga, pero no ambas | Dale descanso en la próxima serie si se puede |
| 🟢 **Mantener** | Rinde bien y está en forma | Sigue en el campo |

### ¿Cómo se decide si un jugador está cansado?
La fatiga se mide **solo con lo jugado hasta ese momento**, así que nadie aparece fatigado al inicio del partido.
El jugador necesita al menos **12 jugadas**, y luego se revisan tres señales:

| Señal | Se activa si… |
|---|---|
| **Sin descanso** | Lleva 8 o más jugadas seguidas en la serie actual sin salir del campo |
| **Pierde explosividad** | Su velocidad tope en sus últimas 5 jugadas cayó 10% o más frente a sus primeras 5 |
| **Carga alta** | Sus yardas recorridas están en el 20% más alto de su posición en el partido |

- 0 señales: **En forma**
- 1 señal: **Carga moderada**
- 2 o 3 señales: **Fatiga probable**. La app busca un relevo de su mismo equipo y posición, sin fatiga y con menos yardas encima.

### ¿Cómo se calcula la calificación?
- Cada métrica se compara **solo contra jugadores de su misma posición**, en todos los partidos con datos.
- **Físico (50%)**: velocidad tope, aceleración, yardas por jugada, sprints por jugada y pérdida de velocidad.
- **Ejecución (50%)**, según su función:
  - **Presiona al QB**: hits, hurries y sacks por jugada.
  - **Protege al QB**: presiones permitidas y veces superado por jugada (menos es mejor).
  - **Receptores y cobertura**: PFF no trae una métrica de calidad para estas funciones, así que su calificación es 100% física. La ficha lo indica.
- Con menos de 5 jugadas no se califica, porque la muestra es insuficiente.

### Límites que conviene conocer
- Los datos de tracking del Big Data Bowl **solo incluyen jugadas de pase**. Las rachas y la carga no cuentan las jugadas de carrera.
- Hoy hay 10 partidos con tracking, todos de la **semana 8**, así que cada jugador tiene un solo partido. La evolución partido a partido aparece al agregar archivos de otras semanas.
- Todos los números salen de los datos reales. La app no inventa ni rellena valores.

---

## Instalación y ejecución (Windows)

### 1. Datos
Los datos **no vienen en el repositorio**. Coloca los archivos del NFL Big Data Bowl en `data/`:

```
data/
  games.csv
  plays.csv
  players.csv
  pffScoutingData.csv
  tracking/
    tracking_2021102500.csv
    tracking_...csv        <- se detectan solos; puedes agregar más
```

### 2. Entorno (una sola vez)
Desde la raíz del proyecto:
```powershell
.\.hackathon\setup.cmd
```
Instala Python 3.12, Node 22 y todas las dependencias dentro del proyecto.

### 3. Arrancar la app
Abre dos terminales en la raíz del proyecto.

**Terminal 1 (servidor de datos):**
```powershell
.\.venv\Scripts\uvicorn.exe backend.main:app --reload --port 8000
```
Para comprobarlo, `http://127.0.0.1:8000/health` debe responder `{"status":"ok"}`.

**Terminal 2 (pantalla del coach):**
```powershell
cd dashboard
$env:Path = "$PWD\..\.hackathon\.tools\node;$env:Path"
npm.cmd run dev
```
Abre la dirección que aparece, normalmente `http://localhost:5173`.

### Problemas comunes
| Problema | Solución |
|---|---|
| `uvicorn` no se reconoce | Usa la ruta completa `.\.venv\Scripts\uvicorn.exe` |
| `npm.ps1 ... la ejecución de scripts está deshabilitada` | Usa `npm.cmd` en lugar de `npm` |
| `.venv` no arranca después de mover la carpeta | Borra `.hackathon\.tools\python\cpython-3.12-windows-x86_64-none` y `.venv`, y corre `.\.hackathon\setup.cmd` |
| "No hay archivos tracking" | Revisa que estén en `data/tracking/` con el nombre `tracking_{gameId}.csv` |

---

## Para desarrolladores

**Stack:** FastAPI + pandas (backend) · React 18 + TypeScript + Tailwind + Recharts (frontend). Todo se calcula
en memoria, sin escribir a disco.

```
backend/
  app.py              cargadores de datos compartidos + /api/partidos, /api/jugadas/{game_id}
  main.py             registra los routers + /health
  modulo_a_kareem.py  /api/kareem  (táctica + IA)
  modulo_b_emilio.py  /api/emilio  (campo, estado físico, calificación)
dashboard/src/
  App.tsx             pestañas
  TacticaKareem.tsx   vista de Kareem
  TableroEmilio.tsx   vista de Emilio
```

**Endpoints de `/api/emilio`:**
| Endpoint | Devuelve |
|---|---|
| `GET tablero/{game_id}/{play_id}` | Cancha, fichas, rutas, zonas de pateador y todos los cuadros de la jugada |
| `GET estado/{game_id}/{play_id}` | Estado físico de cada jugador hasta esa jugada |
| `GET fatiga/{game_id}` | Stats físicas y estado al final del partido (también `/equipo/{abbr}` y `/jugador/{nfl_id}`) |
| `GET evaluacion/{game_id}` | Calificación 0-100 y recomendación por jugador |
| `GET jugador/{nfl_id}/historial` | Calificación partido a partido |

**Datos:** [NFL Big Data Bowl 2023](https://www.kaggle.com/competitions/nfl-big-data-bowl-2023) (tracking, plays, players, PFF scouting).
