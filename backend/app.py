"""Cargador compartido (en memoria, con lru_cache) y endpoints compartidos.

Contrato: expone plays(), scouting(), players(), games(), tracking_jugada() y
solo dos endpoints: GET /api/partidos y GET /api/jugadas/{game_id}.
data/ es de solo lectura: nada se escribe a disco.
"""
import json
import re
from functools import lru_cache
from pathlib import Path

import pandas as pd
from fastapi import APIRouter, HTTPException

RAIZ = Path(__file__).resolve().parent.parent
DATA_DIR = RAIZ / "data"
TRACKING_DIR = DATA_DIR / "tracking"

# Columnas de tracking que se usan (las que no existan en el archivo se ignoran).
COLUMNAS_TRACKING = {
    "gameId", "playId", "nflId", "frameId", "jerseyNumber", "team",
    "playDirection", "x", "y", "s", "a", "dis", "event",
}

router = APIRouter(prefix="/api", tags=["compartido"])


def a_json(df: pd.DataFrame) -> list:
    """DataFrame -> lista de dicts JSON-seguros (NaN -> null, tipos numpy -> nativos)."""
    return json.loads(df.to_json(orient="records"))


@lru_cache(maxsize=1)
def plays() -> pd.DataFrame:
    return pd.read_csv(DATA_DIR / "plays.csv")


@lru_cache(maxsize=1)
def scouting() -> pd.DataFrame:
    return pd.read_csv(DATA_DIR / "pffScoutingData.csv")


@lru_cache(maxsize=1)
def players() -> pd.DataFrame:
    return pd.read_csv(DATA_DIR / "players.csv").drop_duplicates("nflId")


@lru_cache(maxsize=1)
def games() -> pd.DataFrame:
    return pd.read_csv(DATA_DIR / "games.csv")


def archivos_tracking() -> dict:
    """Escanea dinámicamente data/tracking/ -> {game_id: Path}."""
    salida = {}
    if TRACKING_DIR.is_dir():
        for p in TRACKING_DIR.glob("tracking_*.csv"):
            m = re.fullmatch(r"tracking_(\d+)\.csv", p.name)
            if m:
                salida[int(m.group(1))] = p
    return salida


@lru_cache(maxsize=3)
def tracking_juego(game_id: int) -> pd.DataFrame:
    """Tracking completo de un partido (cacheado en RAM). Lanza FileNotFoundError si no existe."""
    ruta = archivos_tracking().get(int(game_id))
    if ruta is None:
        raise FileNotFoundError(f"No hay tracking para el partido {game_id}")
    df = pd.read_csv(ruta, usecols=lambda c: c in COLUMNAS_TRACKING)
    return df.sort_values(["playId", "frameId"], kind="stable").reset_index(drop=True)


def tracking_jugada(game_id: int, play_id: int) -> pd.DataFrame:
    """Frames de una jugada (todas las filas: jugadores y balón), ordenados por frameId."""
    df = tracking_juego(game_id)
    return df[df["playId"] == int(play_id)]


@router.get("/partidos")
def get_partidos() -> list:
    con_tracking = archivos_tracking()
    g = games().copy()
    g["tiene_tracking"] = g["gameId"].isin(list(con_tracking.keys()))
    g = g.sort_values(["week", "gameId"])
    return a_json(g)


@router.get("/jugadas/{game_id}")
def get_jugadas(game_id: int) -> list:
    p = plays()
    p = p[p["gameId"] == game_id]
    if p.empty:
        raise HTTPException(status_code=404, detail=f"Partido {game_id} sin jugadas en plays.csv")
    cols = [
        "gameId", "playId", "quarter", "down", "yardsToGo", "possessionTeam",
        "defensiveTeam", "gameClock", "absoluteYardlineNumber", "playDescription",
    ]
    return a_json(p[cols].sort_values(["quarter", "playId"]))
