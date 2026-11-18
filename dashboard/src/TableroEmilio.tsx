import { useEffect, useMemo, useState } from 'react'
import {
  Bar, BarChart, CartesianGrid, Legend, Line, LineChart, ReferenceLine, Tooltip, XAxis, YAxis,
} from 'recharts'

// ---------- Tipos ----------
interface Partido {
  gameId: number; week: number; gameDate: string
  homeTeamAbbr: string; visitorTeamAbbr: string; tiene_tracking: boolean
}
interface Jugada {
  playId: number; quarter: number; down: number | null; yardsToGo: number | null
  possessionTeam: string; defensiveTeam: string; gameClock: string; playDescription: string
}
interface JugadorTab {
  nflId: number; displayName: string | null; officialPosition: string | null
  jerseyNumber: number | null; team: string; lado: 'ataque' | 'defensa'
  pff_role: string | null; pff_positionLinedUp: string | null
}
interface Frame { frameId: number; event: string | null; pos: [number, number, number][] }
interface Ruta { nflId: number; team: string; trayectoria: [number, number][] }
interface ZonaLados { x_rival_35: number; x_propio_35: number }
interface Tablero {
  playDirection: string; possessionTeam: string; defensiveTeam: string
  absoluteYardlineNumber: number | null; playDescription: string | null
  snap_frame: number; arrival_frame: number | null
  jugadores: JugadorTab[]; frames: Frame[]; rutas: Ruta[]
  zonas_pateador: { ataque: ZonaLados; defensa: ZonaLados }
}
interface Cuarto { jugadas: number; distancia: number; vmax: number | null; vprom: number | null; sprints: number }
interface JugadorFatiga {
  nflId: number; displayName: string | null; team: string; officialPosition: string | null
  height: string | null; weight: number | null; jugadas_tracking: number
  velocidad_max: number | null; velocidad_prom: number | null; aceleracion_max: number | null
  t_pico_aceleracion_max_s: number | null; t_pico_aceleracion_prom_s: number | null
  distancia_total: number; sprints: number; por_cuarto: Record<string, Cuarto>
  pff: { snaps: number; pff_beatenByDefender: number | null; presiones: number | null
         presiones_permitidas: number | null; rutas: number; roles: Record<string, number> }
  alerta_fatiga: boolean; motivos: string[]
  relevo_recomendado: { nflId: number; displayName: string | null; officialPosition: string
                        distancia_total: number; ahorro_distancia: number } | null
}
interface Fatiga {
  local: string; visitante: string; total_alertas: number; jugadores: JugadorFatiga[]
  umbral_alerta: { min_snaps: number; racha_sin_descanso: number; caida_explosividad: number
                   percentil_carga: number; umbral_sprint_yd_s: number }
}

type Recomendacion = 'Cambiar' | 'Vigilar' | 'Mantener'
interface Componente {
  metrica: string; nombre: string; valor: number | null; percentil: number | null
  mayor_es_mejor: boolean; tipo: 'fisico' | 'ejecucion'
}
interface Evaluacion {
  gameId: number; week: number; gameDate: string; rival: string
  nflId: number; displayName: string | null; team: string; officialPosition: string
  rol_principal: string | null; snaps: number; n_comparados: number
  calificacion: number | null; puntaje_fisico: number | null; puntaje_ejecucion: number | null
  componentes: Componente[]; nota: string; alerta_fatiga: boolean; motivos: string[]
  relevo_recomendado: JugadorFatiga['relevo_recomendado']; recomendacion: Recomendacion
  tendencia?: string; delta?: number | null
}
interface Parametros { peso_fisico: number; umbral_cambio: number; margen_tendencia: number; min_snaps: number; comparacion: string }
interface Historial { nflId: number; displayName: string | null; parametros: Parametros; partidos: Evaluacion[] }

async function pedir<T>(url: string): Promise<T> {
  const r = await fetch(url)
  if (!r.ok) {
    let det = `Error ${r.status}`
    try { det = (await r.json()).detail ?? det } catch { /* sin cuerpo JSON */ }
    throw new Error(det)
  }
  return r.json() as Promise<T>
}

const COLOR_ATAQUE = '#1d4ed8'
const COLOR_DEFENSA = '#dc2626'

// ---------- Cancha ----------
function Cancha({ t, foco, idx, sel, onSel }: {
  t: Tablero; foco: 'ataque' | 'defensa'; idx: number; sel: number | null; onSel: (id: number) => void
}) {
  const frame = t.frames[idx]
  const pos = new Map<number, [number, number]>()
  frame.pos.forEach(([id, x, y]) => pos.set(id, [x, y]))
  const zonas = t.zonas_pateador[foco]
  const marcas = Array.from({ length: 21 }, (_, i) => 10 + i * 5)

  return (
    <svg viewBox="-1 -1 122 55.3" className="w-full border border-gray-400 rounded bg-green-700">
      <rect x={0} y={0} width={10} height={53.3} fill="#14532d" />
      <rect x={110} y={0} width={10} height={53.3} fill="#14532d" />
      {marcas.map(x => (
        <line key={x} x1={x} x2={x} y1={0} y2={53.3} stroke="#fff" strokeWidth={x % 10 === 0 ? 0.25 : 0.12} opacity={0.7} />
      ))}
      {marcas.filter(x => x % 10 === 0 && x > 10 && x < 110).map(x => (
        <text key={x} x={x} y={52} fontSize={2.4} fill="#fff" textAnchor="middle" opacity={0.8}>
          {x <= 60 ? x - 10 : 110 - x}
        </text>
      ))}

      {/* Línea de golpeo */}
      {t.absoluteYardlineNumber != null && (
        <line x1={t.absoluteYardlineNumber} x2={t.absoluteYardlineNumber} y1={0} y2={53.3}
              stroke="#facc15" strokeWidth={0.3} />
      )}

      {/* Zonas de pateador */}
      <line x1={zonas.x_rival_35} x2={zonas.x_rival_35} y1={0} y2={53.3} stroke="#22d3ee" strokeWidth={0.4} strokeDasharray="1.5 1" />
      <text x={zonas.x_rival_35} y={3} fontSize={1.9} fill="#a5f3fc" textAnchor="middle">
        Zona de 3 pts - Rango Pateador Propio
      </text>
      <line x1={zonas.x_propio_35} x2={zonas.x_propio_35} y1={0} y2={53.3} stroke="#fb923c" strokeWidth={0.4} strokeDasharray="1.5 1" />
      <text x={zonas.x_propio_35} y={6} fontSize={1.9} fill="#fed7aa" textAnchor="middle">
        Límite para frenar Pateador Rival
      </text>

      {/* Rutas */}
      {t.rutas.map(r => (
        <polyline key={r.nflId} fill="none" strokeWidth={0.35} strokeLinecap="round"
                  stroke={r.team === t.possessionTeam ? '#bfdbfe' : '#fecaca'}
                  points={r.trayectoria.map(([x, y]) => `${x},${y}`).join(' ')} />
      ))}

      {/* Fichas */}
      {t.jugadores.map(j => {
        const p = pos.get(j.nflId)
        if (!p) return null
        const enFoco = j.lado === foco
        return (
          <g key={j.nflId} opacity={enFoco || sel === j.nflId ? 1 : 0.4} className="cursor-pointer"
             onClick={() => onSel(j.nflId)}>
            <title>
              {`${j.displayName ?? 'N/D'} | rol: ${j.pff_role ?? 'N/D'} | alineación: ${j.pff_positionLinedUp ?? 'N/D'} (clic para ver desempeño)`}
            </title>
            <circle cx={p[0]} cy={p[1]} r={1.7}
                    stroke={sel === j.nflId ? '#facc15' : '#fff'} strokeWidth={sel === j.nflId ? 0.5 : 0.2}
                    fill={j.lado === 'ataque' ? COLOR_ATAQUE : COLOR_DEFENSA} />
            <text x={p[0]} y={p[1] - 0.1} fontSize={1.1} fill="#fff" textAnchor="middle" fontWeight="bold">
              {j.officialPosition ?? '?'}
            </text>
            <text x={p[0]} y={p[1] + 1.05} fontSize={0.95} fill="#fff" textAnchor="middle">
              {j.jerseyNumber ?? ''}
            </text>
          </g>
        )
      })}
      {pos.has(0) && (
        <g>
          <title>Balón</title>
          <ellipse cx={pos.get(0)![0]} cy={pos.get(0)![1]} rx={1} ry={0.65} fill="#92400e" stroke="#fff" strokeWidth={0.15} />
        </g>
      )}
    </svg>
  )
}

// ---------- Panel inferior de desempeño del jugador ----------
const ESTILO_REC: Record<Recomendacion, string> = {
  Cambiar: 'bg-red-600 text-white', Vigilar: 'bg-yellow-400 text-gray-900', Mantener: 'bg-green-600 text-white',
}
const ESTILO_TEND: Record<string, string> = {
  Mejora: 'text-green-700', Empeora: 'text-red-700', Estable: 'text-gray-700',
}

function Dato({ k, v }: { k: string; v: string | number | null | undefined }) {
  return (
    <div className="flex justify-between gap-2 border-b border-gray-100 py-0.5">
      <span className="text-gray-600">{k}</span><span className="font-medium">{v ?? '-'}</span>
    </div>
  )
}

function PanelJugador({ gameId, nflId, enJugada, onClose }: {
  gameId: number; nflId: number; enJugada: JugadorTab | null; onClose: () => void
}) {
  const [fis, setFis] = useState<JugadorFatiga | null>(null)
  const [ev, setEv] = useState<Evaluacion | null>(null)
  const [hist, setHist] = useState<Historial | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [cargando, setCargando] = useState(false)

  useEffect(() => {
    let vivo = true
    setFis(null); setEv(null); setHist(null); setError(null); setCargando(true)
    Promise.all([
      pedir<JugadorFatiga>(`api/emilio/fatiga/${gameId}/jugador/${nflId}`),
      pedir<{ jugadores: Evaluacion[] }>(`api/emilio/evaluacion/${gameId}`),
      pedir<Historial>(`api/emilio/jugador/${nflId}/historial`),
    ])
      .then(([f, e, h]) => {
        if (!vivo) return
        setFis(f); setEv(e.jugadores.find(j => j.nflId === nflId) ?? null); setHist(h)
      })
      .catch(e => vivo && setError(String(e.message)))
      .finally(() => vivo && setCargando(false))
    return () => { vivo = false }
  }, [gameId, nflId])

  const ultimo = hist?.partidos.find(p => p.gameId === gameId)
  const datosHist = (hist?.partidos ?? []).map(p => ({
    partido: `S${p.week} vs ${p.rival}`, calificacion: p.calificacion,
    fisico: p.puntaje_fisico, ejecucion: p.puntaje_ejecucion,
  }))

  return (
    <div className="mt-4 border-t-4 border-green-700 bg-white rounded shadow p-4">
      <div className="flex flex-wrap items-center gap-3 mb-3">
        <h3 className="text-lg font-semibold">
          {enJugada?.jerseyNumber != null ? `#${enJugada.jerseyNumber} ` : ''}
          {fis?.displayName ?? enJugada?.displayName ?? nflId}
        </h3>
        <span className="text-sm text-gray-600">
          {fis?.officialPosition ?? enJugada?.officialPosition ?? '-'} · {fis?.team ?? enJugada?.team} ·
          {' '}{fis?.height ?? '-'} · {fis?.weight ?? '-'} lb
          {enJugada && ` · En esta jugada: ${enJugada.pff_role ?? 'N/D'} (${enJugada.pff_positionLinedUp ?? 'N/D'})`}
        </span>
        {ev && <span className={`px-3 py-1 rounded font-bold ${ESTILO_REC[ev.recomendacion]}`}>{ev.recomendacion}</span>}
        <button className="ml-auto px-2 py-1 bg-gray-200 rounded" onClick={onClose}>Cerrar ✕</button>
      </div>

      {cargando && <p>Calculando desempeño (la primera vez compara todos los partidos con tracking)…</p>}
      {error && <p className="text-red-600">{error}</p>}

      {fis && ev && (
        <div className="grid gap-4 md:grid-cols-3 text-sm">
          {/* Calificación */}
          <div>
            <h4 className="font-semibold mb-1">Calificación del partido</h4>
            <div className="text-4xl font-bold">{ev.calificacion ?? 'N/D'}<span className="text-base text-gray-500">/100</span></div>
            <Dato k="Puntaje físico" v={ev.puntaje_fisico} />
            <Dato k="Puntaje ejecución PFF" v={ev.puntaje_ejecucion ?? 'Sin métrica PFF'} />
            <Dato k="Rol principal" v={ev.rol_principal} />
            <Dato k={`Comparado contra ${ev.officialPosition}`} v={`${ev.n_comparados} registros`} />
            <p className="text-xs text-gray-600 mt-1">{ev.nota}</p>
            <h4 className="font-semibold mt-3 mb-1">Percentil por métrica</h4>
            {ev.componentes.map(c => (
              <div key={c.metrica} className="mb-1">
                <div className="flex justify-between text-xs">
                  <span>{c.nombre}{c.mayor_es_mejor ? '' : ' (menor es mejor)'}</span>
                  <span>{c.valor} · p{c.percentil ?? '-'}</span>
                </div>
                <div className="h-2 bg-gray-200 rounded">
                  <div className={`h-2 rounded ${c.tipo === 'ejecucion' ? 'bg-blue-600' : 'bg-green-600'}`}
                       style={{ width: `${c.percentil ?? 0}%` }} />
                </div>
              </div>
            ))}
          </div>

          {/* Stats físicas y PFF */}
          <div>
            <h4 className="font-semibold mb-1">Stats físicas (tracking)</h4>
            <Dato k="Velocidad máx (yd/s)" v={fis.velocidad_max} />
            <Dato k="Velocidad prom (yd/s)" v={fis.velocidad_prom} />
            <Dato k="Aceleración máx (yd/s²)" v={fis.aceleracion_max} />
            <Dato k="t snap → pico aceleración (s)" v={fis.t_pico_aceleracion_max_s} />
            <Dato k="t pico aceleración prom (s)" v={fis.t_pico_aceleracion_prom_s} />
            <Dato k="Distancia total (yd)" v={fis.distancia_total} />
            <Dato k="Sprints" v={fis.sprints} />
            <Dato k="Jugadas en tracking" v={fis.jugadas_tracking} />
            {['1', '2', '3', '4'].map(q => (
              <Dato key={q} k={`Q${q}: dist · v máx · jugadas`}
                    v={`${fis.por_cuarto[q].distancia} · ${fis.por_cuarto[q].vmax ?? '-'} · ${fis.por_cuarto[q].jugadas}`} />
            ))}
            <h4 className="font-semibold mt-3 mb-1">PFF en el partido</h4>
            <Dato k="Snaps" v={fis.pff.snaps} />
            <Dato k="Roles" v={Object.entries(fis.pff.roles).map(([r, n]) => `${r} (${n})`).join(', ')} />
            <Dato k="Presiones generadas" v={fis.pff.presiones} />
            <Dato k="Presiones permitidas" v={fis.pff.presiones_permitidas} />
            <Dato k="Beaten by defender" v={fis.pff.pff_beatenByDefender} />
            <Dato k="Rutas corridas" v={fis.pff.rutas} />
          </div>

          {/* Fatiga, relevo y evolución */}
          <div>
            <h4 className="font-semibold mb-1">Fatiga y recomendación</h4>
            {ev.alerta_fatiga ? (
              <ul className="list-disc ml-5 text-red-700">{ev.motivos.map(m => <li key={m}>{m}</li>)}</ul>
            ) : <p className="text-green-700">Sin alerta de fatiga.</p>}
            {ev.recomendacion !== 'Mantener' && (
              ev.relevo_recomendado ? (
                <p className="mt-2 text-green-800">
                  Relevo recomendado: <b>{ev.relevo_recomendado.displayName}</b> ({ev.relevo_recomendado.officialPosition},
                  {' '}{ev.relevo_recomendado.distancia_total} yd, −{ev.relevo_recomendado.ahorro_distancia} yd de desgaste)
                </p>
              ) : <p className="mt-2 text-gray-500">Sin relevo de la misma posición con menor desgaste.</p>
            )}

            <h4 className="font-semibold mt-3 mb-1">Evolución partido a partido</h4>
            {ultimo?.tendencia && (
              <p className={`font-semibold ${ESTILO_TEND[ultimo.tendencia] ?? 'text-gray-600'}`}>
                {ultimo.tendencia}{ultimo.delta != null ? ` (${ultimo.delta > 0 ? '+' : ''}${ultimo.delta} pts)` : ''}
              </p>
            )}
            {datosHist.length < 2 && (
              <p className="text-xs text-gray-600">
                Solo hay {datosHist.length} partido con tracking para este jugador. La tendencia aparecerá al agregar
                más archivos tracking_[gameId].csv de otras semanas.
              </p>
            )}
            <LineChart width={340} height={200} data={datosHist}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="partido" fontSize={10} />
              <YAxis domain={[0, 100]} fontSize={10} />
              <Tooltip />
              <ReferenceLine y={hist?.parametros.umbral_cambio ?? 40} stroke="#dc2626" strokeDasharray="4 2" />
              <Line type="monotone" dataKey="calificacion" name="Calificación" stroke="#111827" strokeWidth={2} />
              <Line type="monotone" dataKey="fisico" name="Físico" stroke="#16a34a" />
              <Line type="monotone" dataKey="ejecucion" name="Ejecución" stroke="#2563eb" />
            </LineChart>
          </div>
        </div>
      )}
    </div>
  )
}

// ---------- Bloque 1 ----------
function BloqueTablero({ partidos }: { partidos: Partido[] }) {
  const [gameId, setGameId] = useState<number | ''>('')
  const [jugadas, setJugadas] = useState<Jugada[]>([])
  const [playId, setPlayId] = useState<number | ''>('')
  const [foco, setFoco] = useState<'ataque' | 'defensa'>('ataque')
  const [tablero, setTablero] = useState<Tablero | null>(null)
  const [idx, setIdx] = useState(0)
  const [selJug, setSelJug] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setJugadas([]); setPlayId(''); setTablero(null); setSelJug(null)
    if (gameId === '') return
    pedir<Jugada[]>(`api/jugadas/${gameId}`).then(setJugadas).catch(e => setError(String(e.message)))
  }, [gameId])

  useEffect(() => {
    setTablero(null); setError(null)
    if (gameId === '' || playId === '') return
    pedir<Tablero>(`api/emilio/tablero/${gameId}/${playId}`)
      .then(t => {
        setTablero(t)
        setIdx(Math.max(0, t.frames.findIndex(f => f.frameId === t.snap_frame)))
      })
      .catch(e => setError(String(e.message)))
  }, [gameId, playId])

  const jugadaSel = jugadas.find(j => j.playId === playId)
  const frame = tablero?.frames[idx]

  return (
    <section className="mb-8">
      <h2 className="text-xl font-semibold mb-2">Bloque 1: Tablero, fichas y rutas</h2>
      <div className="flex flex-wrap gap-3 mb-3">
        <select className="border rounded p-1" value={gameId}
                onChange={e => setGameId(e.target.value === '' ? '' : Number(e.target.value))}>
          <option value="">Partido…</option>
          {partidos.map(p => (
            <option key={p.gameId} value={p.gameId}>
              Sem {p.week}: {p.visitorTeamAbbr} @ {p.homeTeamAbbr} ({p.gameDate})
            </option>
          ))}
        </select>
        <select className="border rounded p-1 max-w-md" value={playId} disabled={!jugadas.length}
                onChange={e => setPlayId(e.target.value === '' ? '' : Number(e.target.value))}>
          <option value="">Jugada…</option>
          {jugadas.map(j => (
            <option key={j.playId} value={j.playId}>
              Q{j.quarter} {j.gameClock} | {j.possessionTeam} {j.down ?? '-'}&amp;{j.yardsToGo ?? '-'} | {j.playId}
            </option>
          ))}
        </select>
        <select className="border rounded p-1" value={foco}
                onChange={e => setFoco(e.target.value as 'ataque' | 'defensa')} disabled={!jugadaSel}>
          <option value="ataque">Ataca: {jugadaSel?.possessionTeam ?? 'possessionTeam'}</option>
          <option value="defensa">Defiende: {jugadaSel?.defensiveTeam ?? 'defensiveTeam'}</option>
        </select>
      </div>

      {error && <p className="text-red-600 mb-2">{error}</p>}
      {tablero && frame && (
        <>
          <p className="text-sm text-gray-700 mb-1">{tablero.playDescription}</p>
          <p className="text-sm mb-2">
            <span className="inline-block w-3 h-3 mr-1 align-middle" style={{ background: COLOR_ATAQUE }} />
            Ataque ({tablero.possessionTeam})
            <span className="inline-block w-3 h-3 ml-4 mr-1 align-middle" style={{ background: COLOR_DEFENSA }} />
            Defensa ({tablero.defensiveTeam}) · Dirección: {tablero.playDirection}
          </p>
          <Cancha t={tablero} foco={foco} idx={idx} sel={selJug} onSel={setSelJug} />
          <div className="flex items-center gap-3 mt-2">
            <input type="range" className="flex-1" min={0} max={tablero.frames.length - 1} value={idx}
                   onChange={e => setIdx(Number(e.target.value))} />
            <span className="text-sm w-64">
              Frame {frame.frameId}{frame.event ? ` · ${frame.event}` : ''}
            </span>
            <button className="px-2 py-1 bg-gray-200 rounded"
                    onClick={() => setIdx(Math.max(0, tablero.frames.findIndex(f => f.frameId === tablero.snap_frame)))}>
              ball_snap
            </button>
          </div>
          {selJug === null ? (
            <p className="text-sm text-gray-500 mt-2">Haz clic en una ficha para ver el desempeño del jugador.</p>
          ) : gameId !== '' && (
            <PanelJugador gameId={gameId} nflId={selJug}
                          enJugada={tablero.jugadores.find(j => j.nflId === selJug) ?? null}
                          onClose={() => setSelJug(null)} />
          )}
        </>
      )}
    </section>
  )
}

// ---------- Bloque 2 ----------
function BloqueFatiga({ partidos }: { partidos: Partido[] }) {
  const [gameId, setGameId] = useState<number | ''>('')
  const [fatiga, setFatiga] = useState<Fatiga | null>(null)
  const [equipo, setEquipo] = useState('')
  const [solo, setSolo] = useState(false)
  const [sel, setSel] = useState<number | null>(null)
  const [cargando, setCargando] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setFatiga(null); setSel(null); setError(null); setEquipo('')
    if (gameId === '') return
    setCargando(true)
    pedir<Fatiga>(`api/emilio/fatiga/${gameId}`)
      .then(f => { setFatiga(f); setEquipo(f.local) })
      .catch(e => setError(String(e.message)))
      .finally(() => setCargando(false))
  }, [gameId])

  const filas = useMemo(
    () => (fatiga?.jugadores ?? []).filter(j => j.team === equipo && (!solo || j.alerta_fatiga)),
    [fatiga, equipo, solo],
  )
  const jug = fatiga?.jugadores.find(j => j.nflId === sel) ?? null
  const datosQ = jug
    ? ['1', '2', '3', '4'].map(q => ({ cuarto: `Q${q}`, distancia: jug.por_cuarto[q].distancia, sprints: jug.por_cuarto[q].sprints }))
    : []

  return (
    <section>
      <h2 className="text-xl font-semibold mb-2">Bloque 2: Stats físicas, cansancio y relevo</h2>
      <div className="flex flex-wrap gap-3 mb-3 items-center">
        <select className="border rounded p-1" value={gameId}
                onChange={e => setGameId(e.target.value === '' ? '' : Number(e.target.value))}>
          <option value="">Partido…</option>
          {partidos.map(p => (
            <option key={p.gameId} value={p.gameId}>
              Sem {p.week}: {p.visitorTeamAbbr} @ {p.homeTeamAbbr}
            </option>
          ))}
        </select>
        {fatiga && (
          <>
            <select className="border rounded p-1" value={equipo} onChange={e => setEquipo(e.target.value)}>
              <option value={fatiga.local}>{fatiga.local} (local)</option>
              <option value={fatiga.visitante}>{fatiga.visitante} (visitante)</option>
            </select>
            <label className="text-sm">
              <input type="checkbox" className="mr-1" checked={solo} onChange={e => setSolo(e.target.checked)} />
              Solo alertas
            </label>
            <span className="text-sm text-gray-600">
              Fatiga probable al final: {fatiga.total_alertas} · 2 de 3 señales (≥{fatiga.umbral_alerta.racha_sin_descanso} jugadas
              seguidas en la serie, velocidad tope −{Math.round(fatiga.umbral_alerta.caida_explosividad * 100)}%,
              yardas ≥ p{Math.round(fatiga.umbral_alerta.percentil_carga * 100)} de su posición) · mínimo {fatiga.umbral_alerta.min_snaps} jugadas
            </span>
          </>
        )}
      </div>
      {cargando && <p>Calculando métricas…</p>}
      {error && <p className="text-red-600">{error}</p>}

      {fatiga && (
        <div className="overflow-x-auto">
          <table className="text-sm w-full border-collapse">
            <thead>
              <tr className="bg-gray-200 text-left">
                {['Jugador', 'Pos', 'V máx', 'V prom', 'A máx', 't pico A (s)', 'Dist (yd)', 'Q1', 'Q2', 'Q3', 'Q4',
                  'Sprints', 'Snaps', 'Beaten', 'Presiones', 'Rutas', 'Estado / Relevo'].map(h => (
                  <th key={h} className="p-1 whitespace-nowrap">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {filas.map(j => (
                <tr key={j.nflId} onClick={() => setSel(j.nflId)}
                    className={`cursor-pointer border-b ${j.alerta_fatiga ? 'bg-red-50' : ''} ${sel === j.nflId ? 'outline outline-2 outline-green-700' : ''}`}>
                  <td className="p-1 whitespace-nowrap">{j.displayName ?? j.nflId}</td>
                  <td className="p-1">{j.officialPosition ?? '-'}</td>
                  <td className="p-1">{j.velocidad_max ?? '-'}</td>
                  <td className="p-1">{j.velocidad_prom ?? '-'}</td>
                  <td className="p-1">{j.aceleracion_max ?? '-'}</td>
                  <td className="p-1">{j.t_pico_aceleracion_max_s ?? '-'}</td>
                  <td className="p-1">{j.distancia_total}</td>
                  {['1', '2', '3', '4'].map(q => <td key={q} className="p-1">{j.por_cuarto[q].distancia}</td>)}
                  <td className="p-1">{j.sprints}</td>
                  <td className="p-1">{j.pff.snaps}</td>
                  <td className="p-1">{j.pff.pff_beatenByDefender ?? 0}</td>
                  <td className="p-1">{j.pff.presiones ?? 0}</td>
                  <td className="p-1">{j.pff.rutas}</td>
                  <td className="p-1 min-w-64">
                    {j.alerta_fatiga ? (
                      <div>
                        <span className="text-red-700 font-semibold">⚠ Fatiga</span>
                        {j.relevo_recomendado ? (
                          <div className="text-green-800">
                            Sugerencia de Cambio / Relevo Recomendado: {j.relevo_recomendado.displayName}
                            {' '}({j.relevo_recomendado.officialPosition}, {j.relevo_recomendado.distancia_total} yd,
                            −{j.relevo_recomendado.ahorro_distancia} yd)
                          </div>
                        ) : <div className="text-gray-500">Sin relevo con menor desgaste en esa posición</div>}
                      </div>
                    ) : <span className="text-green-700">OK</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {jug && (
        <div className="mt-4">
          <h3 className="font-semibold">
            {jug.displayName} ({jug.officialPosition}) · {jug.height ?? '-'} · {jug.weight ?? '-'} lb
          </h3>
          <p className="text-sm text-gray-700">
            t pico aceleración promedio por jugada: {jug.t_pico_aceleracion_prom_s ?? '-'} s ·
            Jugadas en tracking: {jug.jugadas_tracking} ·
            Roles PFF: {Object.entries(jug.pff.roles).map(([r, n]) => `${r} (${n})`).join(', ') || '-'}
          </p>
          {jug.motivos.length > 0 && (
            <ul className="list-disc ml-5 text-sm text-red-700">
              {jug.motivos.map(m => <li key={m}>{m}</li>)}
            </ul>
          )}
          <BarChart width={520} height={260} data={datosQ}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="cuarto" />
            <YAxis yAxisId="d" />
            <YAxis yAxisId="s" orientation="right" />
            <Tooltip />
            <Legend />
            <Bar yAxisId="d" dataKey="distancia" name="Distancia (yd)" fill="#2F7D4F" />
            <Bar yAxisId="s" dataKey="sprints" name="Sprints" fill="#dc2626" />
          </BarChart>
        </div>
      )}
    </section>
  )
}

// ---------- Vista principal ----------
export default function TableroEmilio() {
  const [partidos, setPartidos] = useState<Partido[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    pedir<Partido[]>('api/partidos')
      .then(ps => setPartidos(ps.filter(p => p.tiene_tracking)))
      .catch(e => setError(String(e.message)))
  }, [])

  if (error) return <p className="text-red-600">{error}</p>
  if (!partidos) return <p>Cargando partidos…</p>
  if (!partidos.length) {
    return <p className="text-gray-700">No hay archivos tracking_[gameId].csv en data/tracking/.</p>
  }
  return (
    <div>
      <BloqueTablero partidos={partidos} />
      <BloqueFatiga partidos={partidos} />
    </div>
  )
}
