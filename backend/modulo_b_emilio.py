"""Módulo B (Emilio): tablero de cancha con fichas/rutas y análisis de fatiga.

Todo se calcula en memoria a partir de data/*.csv y data/tracking/tracking_{gameId}.csv
y se cachea con lru_cache. No se escribe nada a disco.
"""
import math
from functools import lru_cache

import numpy as np
import pandas as pd
from fastapi import APIRouter, HTTPException

from backend.app import (
    archivos_tracking, games, players, plays, scouting, tracking_jugada, tracking_juego,
)

router = APIRouter(prefix="/api/emilio", tags=["emilio"])

# ---- Parámetros de la heurística (visibles en la respuesta de /fatiga) ----
FPS = 10.0                 # el tracking NFL se muestrea a 10 cuadros por segundo
UMBRAL_SPRINT = 8.0        # yd/s (~16.4 mph); un sprint = racha continua de frames con s >= umbral
CUARTOS = (1, 2, 3, 4)

# ---- Criterio de fatiga por señales, evaluado HASTA cada jugada ----
MIN_SNAPS_FATIGA = 12      # con menos jugadas jugadas nadie puede estar "fatigado"
RACHA_SIN_DESCANSO = 8     # jugadas seguidas de su unidad sin salir del campo
VENTANA_EXPLOSIVIDAD = 5   # primeras N vs últimas N jugadas del jugador
CAIDA_EXPLOSIVIDAD = 0.10  # caída >= 10% en la velocidad tope promedio
PERCENTIL_CARGA = 0.80     # yardas acumuladas >= p80 de su posición en ese momento
MIN_GRUPO_CARGA = 4        # jugadores mínimos de la posición para comparar carga

PARAMETROS_FATIGA = {
    "min_snaps": MIN_SNAPS_FATIGA, "racha_sin_descanso": RACHA_SIN_DESCANSO,
    "ventana_explosividad": VENTANA_EXPLOSIVIDAD, "caida_explosividad": CAIDA_EXPLOSIVIDAD,
    "percentil_carga": PERCENTIL_CARGA, "min_grupo_carga": MIN_GRUPO_CARGA,
    "umbral_sprint_yd_s": UMBRAL_SPRINT,
    "nota": "El tracking del Big Data Bowl solo incluye jugadas de pase: las rachas cuentan solo pases.",
}


def _num(v, nd=3):
    """Escalar -> float redondeado o None si es NaN/None."""
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) or math.isinf(f) else round(f, nd)


def _txt(v):
    return None if v is None or (isinstance(v, float) and math.isnan(v)) else str(v)


def _requerir_tracking(game_id: int) -> None:
    if game_id not in archivos_tracking():
        raise HTTPException(status_code=404, detail=f"No hay data/tracking/tracking_{game_id}.csv")


def _info_partido(game_id: int):
    g = games()
    g = g[g["gameId"] == game_id]
    if g.empty:
        raise HTTPException(status_code=404, detail=f"Partido {game_id} no existe en games.csv")
    return g.iloc[0]


# =====================================================================
# BLOQUE 1: tablero
# =====================================================================
@lru_cache(maxsize=64)
def _tablero(game_id: int, play_id: int) -> dict:
    g = _info_partido(game_id)
    p = plays()
    p = p[(p["gameId"] == game_id) & (p["playId"] == play_id)]
    if p.empty:
        raise HTTPException(status_code=404, detail=f"Jugada {play_id} no existe en plays.csv")
    jug = p.iloc[0]

    trk = tracking_jugada(game_id, play_id)
    if trk.empty:
        raise HTTPException(status_code=404, detail=f"La jugada {play_id} no está en el tracking del partido {game_id}")
    trk = trk.dropna(subset=["x", "y"])

    equipo_de = {"home": g["homeTeamAbbr"], "away": g["visitorTeamAbbr"]}
    ataque, defensa = jug["possessionTeam"], jug["defensiveTeam"]

    # ---- metadatos por jugador (tracking + players.csv + pffScoutingData.csv) ----
    ids = [int(i) for i in trk["nflId"].dropna().unique()]
    pl = players().set_index("nflId")
    sc = scouting()
    sc = sc[(sc["gameId"] == game_id) & (sc["playId"] == play_id)].drop_duplicates("nflId").set_index("nflId")
    primera = trk[trk["nflId"].notna()].drop_duplicates("nflId").set_index("nflId")

    jugadores = []
    for i in ids:
        fila = primera.loc[i]
        abbr = equipo_de.get(fila["team"], _txt(fila["team"]))
        jersey = fila["jerseyNumber"] if "jerseyNumber" in primera.columns else None
        jugadores.append({
            "nflId": i,
            "displayName": _txt(pl.at[i, "displayName"]) if i in pl.index else None,
            "officialPosition": _txt(pl.at[i, "officialPosition"]) if i in pl.index else None,
            "jerseyNumber": int(jersey) if jersey is not None and not pd.isna(jersey) else None,
            "team": abbr,
            "lado": "ataque" if abbr == ataque else "defensa",
            "pff_role": _txt(sc.at[i, "pff_role"]) if i in sc.index else None,
            "pff_positionLinedUp": _txt(sc.at[i, "pff_positionLinedUp"]) if i in sc.index else None,
        })

    # ---- frames (todos, para poder mover el frameId en el front) ----
    frames, snap_frame, arrival_frame = [], None, None
    tiene_evento = "event" in trk.columns
    for fid, f in trk.groupby("frameId", sort=True):
        ev = None
        if tiene_evento:
            ev = next((e for e in f["event"].dropna() if e != "None"), None)
        if ev == "ball_snap" and snap_frame is None:
            snap_frame = int(fid)
        if ev == "pass_arrived" and arrival_frame is None:
            arrival_frame = int(fid)
        ids_f = f["nflId"].fillna(0).astype(int).tolist()
        frames.append({
            "frameId": int(fid),
            "event": ev,
            "pos": [[i, round(float(x), 2), round(float(y), 2)]
                    for i, x, y in zip(ids_f, f["x"], f["y"])],
        })
    if snap_frame is None:
        snap_frame = frames[0]["frameId"]
    ultimo = frames[-1]["frameId"]

    # ---- dirección de juego ----
    direccion = None
    if "playDirection" in trk.columns and trk["playDirection"].notna().any():
        direccion = str(trk["playDirection"].dropna().iloc[0])
    if direccion not in ("left", "right"):
        # Respaldo: si el ataque se alinea a la izquierda del balón, juega hacia la derecha.
        f0 = trk[trk["frameId"] == snap_frame]
        ids_ataque = [j["nflId"] for j in jugadores if j["lado"] == "ataque"]
        x_att = f0[f0["nflId"].isin(ids_ataque)]["x"].mean()
        x_bal = f0[f0["nflId"].isna()]["x"].mean()
        direccion = "right" if x_att < x_bal else "left"

    # ---- rutas: jugadores con pff_role == 'Pass Route' ----
    fin = arrival_frame if arrival_frame is not None else ultimo
    rutas = []
    for j in jugadores:
        if (j["pff_role"] or "").strip().lower() != "pass route":
            continue
        tr = trk[(trk["nflId"] == j["nflId"]) & (trk["frameId"] >= snap_frame) & (trk["frameId"] <= fin)]
        rutas.append({
            "nflId": j["nflId"],
            "team": j["team"],
            "trayectoria": [[round(float(x), 2), round(float(y), 2)] for x, y in zip(tr["x"], tr["y"])],
        })

    # ---- zonas de pateador (gol de campo): 35 yd en escala 0-120 con zonas de anotación de 10 ----
    der = direccion == "right"
    zonas = {
        # equipo que ataca hacia la derecha (si direccion == right) o izquierda
        "ataque": {"x_rival_35": 110 - 35 if der else 10 + 35, "x_propio_35": 10 + 35 if der else 110 - 35},
        "defensa": {"x_rival_35": 10 + 35 if der else 110 - 35, "x_propio_35": 110 - 35 if der else 10 + 35},
    }

    return {
        "gameId": game_id,
        "playId": play_id,
        "campo": {"largo": 120, "ancho": 53.3},
        "playDirection": direccion,
        "possessionTeam": ataque,
        "defensiveTeam": defensa,
        "absoluteYardlineNumber": _num(jug["absoluteYardlineNumber"], 1),
        "yardlineSide": _txt(jug["yardlineSide"]),
        "yardlineNumber": _num(jug["yardlineNumber"], 0),
        "gameClock": _txt(jug["gameClock"]),
        "quarter": int(jug["quarter"]),
        "down": _num(jug["down"], 0),
        "yardsToGo": _num(jug["yardsToGo"], 0),
        "playDescription": _txt(jug["playDescription"]),
        "snap_frame": snap_frame,
        "arrival_frame": arrival_frame,
        "ultimo_frame": ultimo,
        "jugadores": jugadores,
        "frames": frames,
        "rutas": rutas,
        "zonas_pateador": zonas,
    }


@router.get("/tablero/{game_id}/{play_id}")
def get_tablero(game_id: int, play_id: int) -> dict:
    _requerir_tracking(game_id)
    return _tablero(game_id, play_id)


# =====================================================================
# ESTADO FÍSICO JUGADA A JUGADA (criterio de señales)
# =====================================================================
@lru_cache(maxsize=16)
def _por_jugada(game_id: int) -> pd.DataFrame:
    """Una fila por (jugador, jugada) desde el snap: velocidad tope, yardas, equipo, lado y posición."""
    g = _info_partido(game_id)
    t = tracking_juego(game_id)
    t = t[t["nflId"].notna()]
    inicio = t.groupby("playId")["frameId"].transform("min")
    if "event" in t.columns:
        snaps = t.loc[t["event"] == "ball_snap"].groupby("playId")["frameId"].min()
        snap = t["playId"].map(snaps).fillna(inicio)
    else:
        snap = inicio
    t = t[t["frameId"] >= snap]
    equipo_de = {"home": g["homeTeamAbbr"], "away": g["visitorTeamAbbr"]}
    t = t.assign(abbr=t["team"].map(equipo_de).fillna(t["team"]), nflId=t["nflId"].astype(int))
    pj = t.groupby(["nflId", "playId"]).agg(
        team=("abbr", "first"), vmax=("s", "max"), dist=("dis", "sum")).reset_index()
    p = plays()
    p = p.loc[p["gameId"] == game_id, ["playId", "possessionTeam"]]
    pj = pj.merge(p, on="playId", how="left")
    pj["lado"] = np.where(pj["team"] == pj["possessionTeam"], "Ofensiva", "Defensiva")
    pj["pos"] = pj["nflId"].map(players().set_index("nflId")["officialPosition"]).fillna("N/D")
    return pj.sort_values(["playId", "nflId"]).reset_index(drop=True)


@lru_cache(maxsize=16)
def _jugadas_partido(game_id: int) -> pd.DataFrame:
    ids = _por_jugada(game_id)["playId"].unique()
    p = plays()
    p = p[(p["gameId"] == game_id) & (p["playId"].isin(ids))]
    return p[["playId", "possessionTeam", "defensiveTeam"]].sort_values("playId").reset_index(drop=True)


@lru_cache(maxsize=512)
def _estado(game_id: int, play_id: int) -> dict:
    """Estado físico de cada jugador usando SOLO las jugadas hasta play_id (incluida)."""
    pj = _por_jugada(game_id)
    h = pj[pj["playId"] <= play_id]
    jp = _jugadas_partido(game_id)
    jp = jp[jp["playId"] <= play_id]
    nombres = players().set_index("nflId")["displayName"]

    plantel = pj.groupby("nflId").agg(team=("team", "first"), pos=("pos", "first"),
                                      unidad=("lado", lambda s: s.value_counts().idxmax()))
    acum = h.groupby("nflId").agg(snaps=("playId", "nunique"), dist=("dist", "sum"))
    plantel = plantel.join(acum).fillna({"snaps": 0, "dist": 0.0})

    jugaron = plantel[plantel["snaps"] > 0]
    n_grupo = jugaron.groupby("pos")["dist"].transform("count")
    p80 = jugaron.groupby("pos")["dist"].transform(lambda s: s.quantile(PERCENTIL_CARGA))
    pct = jugaron.groupby("pos")["dist"].rank(pct=True)
    jugadas_de = h.groupby("nflId")["playId"].apply(set)
    vmax_de = h.groupby("nflId")["vmax"].apply(list)
    # serie = jugadas consecutivas con la misma posesión
    serie = (jp["possessionTeam"] != jp["possessionTeam"].shift()).cumsum()
    serie_actual = jp[serie == serie.iloc[-1]] if not jp.empty else jp

    res = {}
    for nid, r in plantel.iterrows():
        nid = int(nid)
        snaps = int(r["snaps"])
        mis = jugadas_de.get(nid, set())
        # racha dentro de la serie actual: al cambiar la posesión la unidad sale del campo y descansa
        col = "possessionTeam" if r["unidad"] == "Ofensiva" else "defensiveTeam"
        racha = 0
        if not serie_actual.empty and serie_actual[col].iloc[-1] == r["team"]:
            for pid in reversed(serie_actual["playId"].tolist()):
                if pid not in mis:
                    break
                racha += 1

        vm = vmax_de.get(nid, [])
        v_ini = v_rec = caida = None
        if len(vm) >= 2 * VENTANA_EXPLOSIVIDAD:
            v_ini = float(np.mean(vm[:VENTANA_EXPLOSIVIDAD]))
            v_rec = float(np.mean(vm[-VENTANA_EXPLOSIVIDAD:]))
            caida = 1 - v_rec / v_ini if v_ini > 0 else None

        grupo = int(n_grupo.get(nid, 0)) if snaps else 0
        lim = float(p80.get(nid, np.nan)) if snaps else np.nan
        percentil = float(pct.get(nid, np.nan)) if snaps else np.nan

        habil = snaps >= MIN_SNAPS_FATIGA
        s_racha = habil and racha >= RACHA_SIN_DESCANSO
        s_expl = habil and caida is not None and caida >= CAIDA_EXPLOSIVIDAD
        s_carga = habil and grupo >= MIN_GRUPO_CARGA and r["dist"] >= lim
        senales = [
            {"clave": "racha", "nombre": "Sin descanso", "activa": bool(s_racha),
             "detalle": f"{racha} jugadas seguidas en esta serie sin salir (alerta desde {RACHA_SIN_DESCANSO})"},
            {"clave": "explosividad", "nombre": "Pierde explosividad", "activa": bool(s_expl),
             "detalle": (f"Velocidad tope promedio: primeras {VENTANA_EXPLOSIVIDAD} jugadas {v_ini * 2.0455:.1f} mph"
                         f" → últimas {VENTANA_EXPLOSIVIDAD}: {v_rec * 2.0455:.1f} mph ({-caida * 100:+.0f}%)")
             if caida is not None else
             f"Aún no hay {2 * VENTANA_EXPLOSIVIDAD} jugadas para comparar su arranque con su momento actual"},
            {"clave": "carga", "nombre": "Carga alta", "activa": bool(s_carga),
             "detalle": (f"{r['dist']:.0f} yardas recorridas, percentil {percentil * 100:.0f} entre {grupo} "
                         f"jugadores {r['pos']} del partido")
             if grupo >= MIN_GRUPO_CARGA else
             f"{r['dist']:.0f} yardas recorridas (pocos {r['pos']} en el partido para comparar)"},
        ]
        activas = sum(s["activa"] for s in senales)
        estado = "Fatiga probable" if activas >= 2 else "Carga moderada" if activas == 1 else "En forma"
        res[nid] = {
            "nflId": nid, "displayName": _txt(nombres.get(nid)), "team": r["team"],
            "officialPosition": r["pos"], "unidad": r["unidad"], "snaps_hasta": snaps,
            "racha": racha, "caida_explosividad": _num(caida, 3),
            "dist_acumulada": _num(r["dist"], 1),
            "percentil_carga": _num(percentil * 100, 0) if not math.isnan(percentil) else None,
            "estado": estado, "senales_activas": activas, "senales": senales,
            "nota": None if habil else f"Solo {snaps} jugadas jugadas: se evalúa a partir de {MIN_SNAPS_FATIGA}.",
            "relevo_recomendado": None,
        }

    # relevo: mismo equipo y posición, sin fatiga probable, con menos yardas acumuladas hasta ahora
    for j in res.values():
        if j["estado"] != "Fatiga probable":
            continue
        cands = [c for c in res.values()
                 if c["nflId"] != j["nflId"] and c["team"] == j["team"]
                 and c["officialPosition"] == j["officialPosition"] and c["estado"] != "Fatiga probable"
                 and c["dist_acumulada"] < j["dist_acumulada"]]
        if cands:
            c = min(cands, key=lambda c: c["dist_acumulada"])
            j["relevo_recomendado"] = {
                "nflId": c["nflId"], "displayName": c["displayName"], "officialPosition": c["officialPosition"],
                "distancia_total": c["dist_acumulada"],
                "ahorro_distancia": round(j["dist_acumulada"] - c["dist_acumulada"], 1),
            }
    return {"gameId": game_id, "playId": play_id, "jugadores": res}


@router.get("/estado/{game_id}/{play_id}")
def get_estado(game_id: int, play_id: int) -> dict:
    _requerir_tracking(game_id)
    if play_id not in set(_por_jugada(game_id)["playId"]):
        raise HTTPException(status_code=404, detail=f"La jugada {play_id} no está en el tracking del partido {game_id}")
    e = _estado(game_id, play_id)
    lista = sorted(e["jugadores"].values(), key=lambda j: (-j["senales_activas"], -(j["dist_acumulada"] or 0)))
    return {"gameId": game_id, "playId": play_id, "parametros": PARAMETROS_FATIGA, "jugadores": lista}


# =====================================================================
# BLOQUE 2: fatiga
# =====================================================================
def _resumen_pff(game_id: int) -> pd.DataFrame:
    p = plays()
    ids_jugadas = p.loc[p["gameId"] == game_id, "playId"]
    sc = scouting()
    sc = sc[(sc["gameId"] == game_id) & (sc["playId"].isin(ids_jugadas))].copy()
    cols = ["pff_hit", "pff_hurry", "pff_sack", "pff_beatenByDefender",
            "pff_hitAllowed", "pff_hurryAllowed", "pff_sackAllowed"]
    sc[cols] = sc[cols].fillna(0)
    rol = sc["pff_role"].fillna("").str.strip().str.lower()
    sc["es_ruta"] = rol.eq("pass route")
    sc["es_rush"] = rol.eq("pass rush")
    sc["es_block"] = rol.eq("pass block")
    sc["presiones"] = sc["pff_hit"] + sc["pff_hurry"] + sc["pff_sack"]
    sc["presiones_permitidas"] = sc["pff_hitAllowed"] + sc["pff_hurryAllowed"] + sc["pff_sackAllowed"]
    res = sc.groupby("nflId").agg(
        snaps=("playId", "nunique"),
        beaten_by_defender=("pff_beatenByDefender", "sum"),
        presiones=("presiones", "sum"),
        presiones_permitidas=("presiones_permitidas", "sum"),
        rutas=("es_ruta", "sum"),
        snaps_rush=("es_rush", "sum"),
        snaps_block=("es_block", "sum"),
    )
    roles = sc.dropna(subset=["pff_role"]).groupby("nflId")["pff_role"].agg(
        lambda s: s.value_counts().to_dict())
    res["roles"] = roles
    return res


@lru_cache(maxsize=8)
def _fatiga(game_id: int) -> dict:
    g = _info_partido(game_id)
    t = tracking_juego(game_id)

    # frame del snap por jugada (el evento viaja en todas las filas del frame)
    if "event" in t.columns:
        snaps = t.loc[t["event"] == "ball_snap"].groupby("playId")["frameId"].min().rename("snap")
        t = t.join(snaps, on="playId")
    else:
        t = t.assign(snap=np.nan)
    t = t[t["nflId"].notna()].copy()
    t["snap"] = t["snap"].fillna(t.groupby("playId")["frameId"].transform("min"))
    t = t[t["frameId"] >= t["snap"]].copy()      # solo acción desde el snap
    t["t_snap"] = (t["frameId"] - t["snap"]) / FPS
    t["nflId"] = t["nflId"].astype(int)

    q = plays().loc[plays()["gameId"] == game_id, ["playId", "quarter"]]
    t = t.merge(q, on="playId", how="left")
    t = t.sort_values(["nflId", "playId", "frameId"], kind="stable")

    # sprints = inicios de rachas continuas con s >= umbral dentro de cada jugada
    t["_alta"] = t["s"] >= UMBRAL_SPRINT
    previo = t.groupby(["nflId", "playId"])["_alta"].shift(1, fill_value=False)
    t["_sprint"] = (t["_alta"] & ~previo).astype(int)

    equipo_de = {"home": g["homeTeamAbbr"], "away": g["visitorTeamAbbr"]}
    # el tracking puede traer 'home'/'away' o ya la abreviatura (ej. SEA); se soportan ambos
    t["abbr"] = t["team"].map(equipo_de).fillna(t["team"])

    tot = t.groupby("nflId").agg(
        team=("abbr", "first"),
        jugadas=("playId", "nunique"),
        vmax=("s", "max"), vprom=("s", "mean"),
        amax=("a", "max"),
        dist=("dis", "sum"),
        sprints=("_sprint", "sum"),
    )
    por_q = t.groupby(["nflId", "quarter"]).agg(
        jugadas=("playId", "nunique"), vmax=("s", "max"), vprom=("s", "mean"),
        dist=("dis", "sum"), sprints=("_sprint", "sum"),
    )

    # pico de aceleración por jugada -> tiempo desde el snap
    ta = t.dropna(subset=["a"])
    idx = ta.groupby(["nflId", "playId"])["a"].idxmax()
    picos = ta.loc[idx, ["nflId", "playId", "a", "t_snap"]]
    t_prom = picos.groupby("nflId")["t_snap"].mean()
    t_max = picos.loc[picos.groupby("nflId")["a"].idxmax()].set_index("nflId")["t_snap"]

    pl = players().set_index("nflId")
    pff = _resumen_pff(game_id)

    jugadores = {}
    for nfl_id, r in tot.iterrows():
        info = pl.loc[nfl_id] if nfl_id in pl.index else None
        cuartos = {}
        for qn in CUARTOS:
            if (nfl_id, qn) in por_q.index:
                rq = por_q.loc[(nfl_id, qn)]
                cuartos[str(qn)] = {
                    "jugadas": int(rq["jugadas"]), "distancia": _num(rq["dist"], 2),
                    "vmax": _num(rq["vmax"]), "vprom": _num(rq["vprom"]),
                    "sprints": int(rq["sprints"]),
                }
            else:
                cuartos[str(qn)] = {"jugadas": 0, "distancia": 0.0, "vmax": None, "vprom": None, "sprints": 0}
        rp = pff.loc[nfl_id] if nfl_id in pff.index else None
        jugadores[int(nfl_id)] = {
            "nflId": int(nfl_id),
            "displayName": _txt(info["displayName"]) if info is not None else None,
            "team": _txt(r["team"]),
            "officialPosition": _txt(info["officialPosition"]) if info is not None else None,
            "height": _txt(info["height"]) if info is not None else None,
            "weight": _num(info["weight"], 0) if info is not None else None,
            "jugadas_tracking": int(r["jugadas"]),
            "velocidad_max": _num(r["vmax"]),
            "velocidad_prom": _num(r["vprom"]),
            "aceleracion_max": _num(r["amax"]),
            "t_pico_aceleracion_max_s": _num(t_max.get(nfl_id), 2),
            "t_pico_aceleracion_prom_s": _num(t_prom.get(nfl_id), 2),
            "distancia_total": _num(r["dist"], 2),
            "sprints": int(r["sprints"]),
            "por_cuarto": cuartos,
            "pff": {
                "snaps": int(rp["snaps"]) if rp is not None else 0,
                "pff_beatenByDefender": _num(rp["beaten_by_defender"], 0) if rp is not None else 0,
                "presiones": _num(rp["presiones"], 0) if rp is not None else 0,
                "presiones_permitidas": _num(rp["presiones_permitidas"], 0) if rp is not None else 0,
                "rutas": int(rp["rutas"]) if rp is not None else 0,
                "snaps_rush": int(rp["snaps_rush"]) if rp is not None else 0,
                "snaps_block": int(rp["snaps_block"]) if rp is not None else 0,
                "roles": rp["roles"] if rp is not None and isinstance(rp["roles"], dict) else {},
            },
            "unidad": None, "estado_fisico": "En forma", "senales": [], "caida_explosividad": None,
            "alerta_fatiga": False,
            "motivos": [],
            "relevo_recomendado": None,
        }

    # ---- estado físico al FINAL del partido (mismo criterio de señales que jugada a jugada) ----
    final = _estado(game_id, int(_por_jugada(game_id)["playId"].max()))
    for nfl_id, j in jugadores.items():
        e = final["jugadores"].get(nfl_id)
        if e is None:
            continue
        j.update({
            "unidad": e["unidad"], "estado_fisico": e["estado"], "senales": e["senales"],
            "caida_explosividad": e["caida_explosividad"],
            "alerta_fatiga": e["estado"] == "Fatiga probable",
            "motivos": [s["detalle"] for s in e["senales"] if s["activa"]],
            "relevo_recomendado": e["relevo_recomendado"],
        })

    return {
        "gameId": game_id,
        "local": _txt(g["homeTeamAbbr"]),
        "visitante": _txt(g["visitorTeamAbbr"]),
        "umbral_alerta": PARAMETROS_FATIGA,
        "jugadores": jugadores,
    }


def _lista(game_id: int, equipo: str | None = None) -> list:
    js = list(_fatiga(game_id)["jugadores"].values())
    if equipo:
        js = [j for j in js if j["team"] == equipo.upper()]
    return sorted(js, key=lambda j: j["distancia_total"], reverse=True)


@router.get("/fatiga/{game_id}")
def get_fatiga(game_id: int) -> dict:
    _requerir_tracking(game_id)
    f = _fatiga(game_id)
    lista = _lista(game_id)
    return {
        "gameId": f["gameId"], "local": f["local"], "visitante": f["visitante"],
        "umbral_alerta": f["umbral_alerta"],
        "total_alertas": sum(1 for j in lista if j["alerta_fatiga"]),
        "jugadores": lista,
    }


@router.get("/fatiga/{game_id}/equipo/{equipo}")
def get_fatiga_equipo(game_id: int, equipo: str) -> dict:
    _requerir_tracking(game_id)
    lista = _lista(game_id, equipo)
    if not lista:
        raise HTTPException(status_code=404, detail=f"Equipo {equipo} sin jugadores en el partido {game_id}")
    f = _fatiga(game_id)
    return {
        "gameId": game_id, "equipo": equipo.upper(),
        "umbral_alerta": f["umbral_alerta"],
        "total_alertas": sum(1 for j in lista if j["alerta_fatiga"]),
        "jugadores": lista,
    }


@router.get("/fatiga/{game_id}/jugador/{nfl_id}")
def get_fatiga_jugador(game_id: int, nfl_id: int) -> dict:
    _requerir_tracking(game_id)
    j = _fatiga(game_id)["jugadores"].get(nfl_id)
    if j is None:
        raise HTTPException(status_code=404, detail=f"Jugador {nfl_id} no aparece en el tracking del partido {game_id}")
    return j


# =====================================================================
# EVALUACIÓN DE DESEMPEÑO (calificación 0-100 por partido) e historial
# =====================================================================
PESO_FISICO = 0.5          # 50% físico / 50% ejecución PFF (si el rol tiene métrica PFF)
UMBRAL_CAMBIO = 40         # calificación < 40 se considera bajo rendimiento
MARGEN_TENDENCIA = 5       # ±5 puntos frente al partido anterior = "Estable"
MIN_SNAPS_EVAL = 5         # con menos snaps en tracking la muestra es insuficiente

# (columna, mayor_es_mejor)
METRICAS_FISICAS = [
    ("vmax", True), ("amax", True), ("dist_snap", True), ("sprints_snap", True), ("caida", False),
]
NOMBRES = {
    "vmax": "Velocidad máxima", "amax": "Aceleración máxima", "dist_snap": "Distancia por snap",
    "sprints_snap": "Sprints por snap",
    "caida": "Caída de velocidad tope (últimas 5 vs primeras 5 jugadas)",
    "tasa_presion": "Presiones por snap de Pass Rush (hit+hurry+sack)",
    "tasa_permitida": "Presiones permitidas + beaten por snap de Pass Block",
}


def _filas_juego(game_id: int) -> list:
    g = _info_partido(game_id)
    filas = []
    for j in _fatiga(game_id)["jugadores"].values():
        pff, n = j["pff"], j["jugadas_tracking"]
        roles = pff["roles"]
        rol = max(roles, key=roles.get) if roles else None
        local = j["team"] == g["homeTeamAbbr"]
        filas.append({
            "gameId": game_id, "week": int(g["week"]), "gameDate": _txt(g["gameDate"]),
            "rival": _txt(g["visitorTeamAbbr"] if local else g["homeTeamAbbr"]),
            "nflId": j["nflId"], "displayName": j["displayName"], "team": j["team"],
            "officialPosition": j["officialPosition"] or "N/D", "rol_principal": rol, "snaps": n,
            "vmax": j["velocidad_max"], "amax": j["aceleracion_max"],
            "dist_snap": j["distancia_total"] / n if n else None,
            "sprints_snap": j["sprints"] / n if n else None,
            "caida": j.get("caida_explosividad"),
            "tasa_presion": (pff["presiones"] or 0) / pff["snaps_rush"]
            if rol == "Pass Rush" and pff["snaps_rush"] else None,
            "tasa_permitida": ((pff["presiones_permitidas"] or 0) + (pff["pff_beatenByDefender"] or 0)) / pff["snaps_block"]
            if rol == "Pass Block" and pff["snaps_block"] else None,
            "alerta_fatiga": j["alerta_fatiga"], "motivos": j["motivos"],
            "relevo_recomendado": j["relevo_recomendado"],
        })
    return filas


@lru_cache(maxsize=4)
def _evaluacion_base(ids: tuple) -> pd.DataFrame:
    """Calificación de cada jugador en cada partido con tracking.
    Percentiles contra la misma officialPosition usando TODOS los partidos con tracking."""
    df = pd.DataFrame([f for g in ids for f in _filas_juego(g)])
    elegible = df["snaps"] >= MIN_SNAPS_EVAL
    pos = df["officialPosition"]

    def pct(col, mayor_mejor):
        return df[col].where(elegible).astype(float).groupby(pos).rank(pct=True, ascending=mayor_mejor)

    for col, mm in METRICAS_FISICAS:
        df[f"p_{col}"] = pct(col, mm)
    df["p_tasa_presion"] = pct("tasa_presion", True)
    df["p_tasa_permitida"] = pct("tasa_permitida", False)
    df["n_comparados"] = df["snaps"].where(elegible).groupby(pos).transform("count")

    fis = df[[f"p_{c}" for c, _ in METRICAS_FISICAS]].mean(axis=1, skipna=True) * 100
    eje = df["p_tasa_presion"].fillna(df["p_tasa_permitida"]) * 100
    df["puntaje_fisico"] = fis.where(elegible)
    df["puntaje_ejecucion"] = eje.where(elegible)
    df["calificacion"] = np.where(eje.notna(), PESO_FISICO * fis + (1 - PESO_FISICO) * eje, fis)
    df.loc[~elegible, "calificacion"] = np.nan
    df["fecha"] = pd.to_datetime(df["gameDate"], format="%m/%d/%Y", errors="coerce")
    return df


def _base_actual() -> pd.DataFrame:
    return _evaluacion_base(tuple(sorted(archivos_tracking())))


def _recomendacion(cal, alerta: bool) -> str:
    bajo = cal is not None and cal < UMBRAL_CAMBIO
    if bajo and alerta:
        return "Cambiar"
    if bajo or alerta:
        return "Vigilar"
    return "Mantener"


def _fila_json(r: pd.Series) -> dict:
    cal = _num(r["calificacion"], 1)
    componentes = []
    for col, mm in METRICAS_FISICAS + [("tasa_presion", True), ("tasa_permitida", False)]:
        if r[col] is None or pd.isna(r[col]):
            continue
        componentes.append({
            "metrica": col, "nombre": NOMBRES[col], "valor": _num(r[col], 3),
            "percentil": _num(r[f"p_{col}"] * 100, 1) if not pd.isna(r[f"p_{col}"]) else None,
            "mayor_es_mejor": mm,
            "tipo": "ejecucion" if col.startswith("tasa_") else "fisico",
        })
    tiene_eje = not pd.isna(r["puntaje_ejecucion"])
    if r["snaps"] < MIN_SNAPS_EVAL:
        nota = f"Muestra insuficiente: {int(r['snaps'])} snaps en tracking (mínimo {MIN_SNAPS_EVAL})."
    elif tiene_eje:
        nota = f"Calificación = {int(PESO_FISICO * 100)}% físico + {int((1 - PESO_FISICO) * 100)}% ejecución PFF."
    else:
        nota = (f"PFF no trae métrica de calidad para el rol '{r['rol_principal'] or 'N/D'}': "
                "calificación 100% física.")
    return {
        "gameId": int(r["gameId"]), "week": int(r["week"]), "gameDate": r["gameDate"], "rival": r["rival"],
        "nflId": int(r["nflId"]), "displayName": r["displayName"], "team": r["team"],
        "officialPosition": r["officialPosition"], "rol_principal": r["rol_principal"],
        "snaps": int(r["snaps"]), "n_comparados": int(r["n_comparados"]) if not pd.isna(r["n_comparados"]) else 0,
        "calificacion": cal,
        "puntaje_fisico": _num(r["puntaje_fisico"], 1),
        "puntaje_ejecucion": _num(r["puntaje_ejecucion"], 1),
        "componentes": componentes, "nota": nota,
        "alerta_fatiga": bool(r["alerta_fatiga"]), "motivos": list(r["motivos"]),
        "relevo_recomendado": r["relevo_recomendado"],
        "recomendacion": _recomendacion(cal, bool(r["alerta_fatiga"])),
    }


PARAMETROS_EVAL = {
    "peso_fisico": PESO_FISICO, "umbral_cambio": UMBRAL_CAMBIO,
    "margen_tendencia": MARGEN_TENDENCIA, "min_snaps": MIN_SNAPS_EVAL,
    "comparacion": "percentil contra la misma officialPosition en todos los partidos con tracking",
}


@router.get("/evaluacion/{game_id}")
def get_evaluacion(game_id: int) -> dict:
    _requerir_tracking(game_id)
    df = _base_actual()
    filas = [_fila_json(r) for _, r in df[df["gameId"] == game_id].iterrows()]
    orden = {"Cambiar": 0, "Vigilar": 1, "Mantener": 2}
    filas.sort(key=lambda f: (orden[f["recomendacion"]],
                              f["calificacion"] if f["calificacion"] is not None else 999))
    return {
        "gameId": game_id, "parametros": PARAMETROS_EVAL,
        "partidos_comparados": int(df["gameId"].nunique()), "jugadores": filas,
    }


@router.get("/jugador/{nfl_id}/historial")
def get_historial(nfl_id: int) -> dict:
    df = _base_actual()
    d = df[df["nflId"] == nfl_id].sort_values(["fecha", "gameId"])
    if d.empty:
        raise HTTPException(status_code=404, detail=f"Jugador {nfl_id} no aparece en ningún partido con tracking")
    partidos, previo = [], None
    for _, r in d.iterrows():
        f = _fila_json(r)
        cal = f["calificacion"]
        if previo is None or cal is None:
            f["tendencia"], f["delta"] = ("Primer partido" if previo is None else "Sin dato"), None
        else:
            delta = round(cal - previo, 1)
            f["delta"] = delta
            f["tendencia"] = "Mejora" if delta > MARGEN_TENDENCIA else "Empeora" if delta < -MARGEN_TENDENCIA else "Estable"
        if cal is not None:
            previo = cal
        partidos.append(f)
    return {
        "nflId": nfl_id, "displayName": partidos[-1]["displayName"],
        "officialPosition": partidos[-1]["officialPosition"], "parametros": PARAMETROS_EVAL,
        "partidos": partidos,
    }
