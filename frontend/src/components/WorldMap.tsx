import { useState, useRef, useMemo, useCallback, useEffect } from 'react'
import type { WorldMapData, RegionNode } from '../types'

interface WorldMapProps {
  map: WorldMapData
  traveling: boolean
  onTravel: (regionId: string) => void
}

// --- Geometry helpers ---------------------------------------------------------

/** SVG viewBox is a 100×100 square; PAD keeps nodes off the edge. */
const VIEW = 100
const PAD = 8
const toX = (nx: number) => PAD + nx * (VIEW - 2 * PAD)
const toY = (ny: number) => PAD + ny * (VIEW - 2 * PAD)
const clamp = (v: number, lo: number, hi: number) => Math.max(lo, Math.min(hi, v))
const clampZoom = (z: number) => clamp(z, 0.6, 3)

/** Terrain texture pattern tiles, keyed by the backend `visual.pattern`. */
const PATTERN_DEFS: Record<string, JSX.Element> = {
  trees: <path d="M2 6.5 L4 2 L6 6.5 Z" fill="rgba(0,0,0,0.20)" />,
  peaks: <path d="M1 7 L4 3 L7 7" stroke="rgba(0,0,0,0.22)" fill="none" strokeWidth="0.7" />,
  waves: <path d="M1 5 Q3 3 5 5 T9 5" stroke="rgba(255,255,255,0.30)" fill="none" strokeWidth="0.6" />,
  ripples: (
    <>
      <circle cx="4" cy="4" r="1.6" fill="none" stroke="rgba(0,0,0,0.20)" strokeWidth="0.5" />
      <circle cx="4" cy="4" r="3" fill="none" stroke="rgba(0,0,0,0.12)" strokeWidth="0.4" />
    </>
  ),
  dunes: <path d="M0 6 Q4 2 8 6" stroke="rgba(0,0,0,0.16)" fill="none" strokeWidth="0.6" />,
  snow: (
    <>
      <circle cx="2" cy="2" r="0.5" fill="rgba(255,255,255,0.55)" />
      <circle cx="5" cy="5" r="0.5" fill="rgba(255,255,255,0.45)" />
    </>
  ),
  cracks: (
    <path d="M1 1 L3 4 L2 7 M5 2 L6 5 L7 7" stroke="rgba(0,0,0,0.26)" fill="none" strokeWidth="0.4" />
  ),
  roofs: (
    <>
      <rect x="2" y="3" width="3" height="2.4" fill="rgba(0,0,0,0.22)" />
      <rect x="2" y="3" width="3" height="0.6" fill="rgba(255,255,255,0.18)" />
    </>
  ),
  grass: <path d="M2 5 L2 3 M4 5 L4 2.5" stroke="rgba(0,0,0,0.18)" strokeWidth="0.5" />,
}

/**
 * Visual region explorer — a *rendered* fantasy map.
 *
 * Each region is painted with a terrain-tinted radial gradient and a subtle
 * texture pattern (trees / peaks / waves / …) instead of a flat coloured dot.
 * Undiscovered regions (fog of war: not visited and not adjacent to a visited
 * region) are shrouded in cloud. The map is pannable (drag) and zoomable
 * (wheel / buttons), travel routes to reachable regions are drawn as animated
 * marching-ants roads, and a compass rose + decorative frame give it a
 * hand-drawn cartographer's feel.
 */
export default function WorldMap({ map, traveling, onTravel }: WorldMapProps) {
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [hoveredId, setHoveredId] = useState<string | null>(null)
  const [view, setView] = useState({ x: 0, y: 0, zoom: 1 })

  const svgRef = useRef<SVGSVGElement>(null)
  const dragRef = useRef<{ sx: number; sy: number; ox: number; oy: number } | null>(null)
  const dragMovedRef = useRef(false)

  // Fog of war: discovered = visited ∪ neighbours of visited. Fall back to
  // "everything visible" if the backend didn't send the set.
  const discovered = useMemo(() => {
    const ids = map.discovered_region_ids
    return new Set(ids && ids.length ? ids : map.regions.map((r) => r.id))
  }, [map.discovered_region_ids, map.regions])

  const reachable = useMemo(() => new Set(map.reachable_region_ids), [map.reachable_region_ids])
  const regionById = useMemo(() => new Map(map.regions.map((r) => [r.id, r])), [map.regions])

  // Unique terrains + patterns present on this map (for <defs>).
  const terrains = useMemo(() => {
    const seen = new Map<string, RegionNode['visual']>()
    for (const r of map.regions) seen.set(r.terrain, r.visual)
    return seen
  }, [map.regions])
  const patterns = useMemo(() => {
    const seen = new Set<string>()
    for (const r of map.regions) seen.add(r.visual.pattern)
    return seen
  }, [map.regions])

  const selected = selectedId ? regionById.get(selectedId) ?? null : map.current_region

  // Build the list of connection edges (deduped).
  const edges = useMemo(() => {
    const out: { a: RegionNode; b: RegionNode }[] = []
    const seen = new Set<string>()
    for (const r of map.regions) {
      for (const cid of r.connections) {
        const other = regionById.get(cid)
        if (!other) continue
        const key = [r.id, cid].sort().join('|')
        if (seen.has(key)) continue
        seen.add(key)
        out.push({ a: r, b: other })
      }
    }
    return out
  }, [map.regions, regionById])

  // --- pan & zoom -----------------------------------------------------------

  const clientToView = useCallback((clientX: number, clientY: number) => {
    const svg = svgRef.current
    if (!svg) return null
    const pt = svg.createSVGPoint()
    pt.x = clientX
    pt.y = clientY
    const ctm = svg.getScreenCTM()
    if (!ctm) return null
    const p = pt.matrixTransform(ctm.inverse())
    return { x: p.x, y: p.y }
  }, [])

  // Attach wheel as a non-passive listener so we can preventDefault scrolling.
  useEffect(() => {
    const svg = svgRef.current
    if (!svg) return
    const onWheel = (e: WheelEvent) => {
      e.preventDefault()
      const p = clientToView(e.clientX, e.clientY)
      if (!p) return
      const factor = e.deltaY < 0 ? 1.12 : 1 / 1.12
      setView((v) => {
        const z2 = clampZoom(v.zoom * factor)
        const k = z2 / v.zoom
        return { x: p.x - (p.x - v.x) * k, y: p.y - (p.y - v.y) * k, zoom: z2 }
      })
    }
    svg.addEventListener('wheel', onWheel, { passive: false })
    return () => svg.removeEventListener('wheel', onWheel)
  }, [clientToView])

  const onPointerDown = (e: React.PointerEvent) => {
    if (e.button !== 0) return
    dragRef.current = { sx: e.clientX, sy: e.clientY, ox: view.x, oy: view.y }
    dragMovedRef.current = false
  }

  const onPointerMove = (e: React.PointerEvent) => {
    const d = dragRef.current
    if (!d) return
    const dx = e.clientX - d.sx
    const dy = e.clientY - d.sy
    if (Math.abs(dx) + Math.abs(dy) > 3) dragMovedRef.current = true
    const svg = svgRef.current
    if (!svg) return
    const rect = svg.getBoundingClientRect()
    if (!rect.width || !rect.height) return
    setView((v) => ({ ...v, x: d.ox + dx * (VIEW / rect.width), y: d.oy + dy * (VIEW / rect.height) }))
  }

  const endDrag = () => {
    dragRef.current = null
  }

  const zoomBy = useCallback((factor: number) => {
    setView((v) => {
      const z2 = clampZoom(v.zoom * factor)
      const k = z2 / v.zoom
      const cx = VIEW / 2
      const cy = VIEW / 2
      return { x: cx - (cx - v.x) * k, y: cy - (cy - v.y) * k, zoom: z2 }
    })
  }, [])

  const resetView = () => setView({ x: 0, y: 0, zoom: 1 })

  const handleNodeClick = (r: RegionNode) => {
    if (dragMovedRef.current) return // it was a drag, not a click
    setSelectedId(r.id)
    if (reachable.has(r.id) && !traveling && r.id !== map.current_region_id) {
      onTravel(r.id)
    }
  }

  // The route to render as a marching-ants road: prefer the hovered reachable
  // region, else the selected one if it's reachable.
  const routeTargetId = hoveredId && reachable.has(hoveredId)
    ? hoveredId
    : selected && reachable.has(selected.id)
      ? selected.id
      : null
  const routePath = routeTargetId ? map.routes?.[routeTargetId] : undefined

  return (
    <div className="space-y-3">
      {/* === The map === */}
      <div className="relative rounded-lg border-2 border-amber-900/50 bg-gradient-to-br from-parchment-900/90 via-parchment-900/70 to-blood-950/50 p-1 shadow-inner overflow-hidden">
        <svg
          ref={svgRef}
          viewBox={`0 0 ${VIEW} ${VIEW}`}
          className="w-full h-auto touch-none select-none"
          style={{ aspectRatio: '1 / 1', cursor: dragRef.current ? 'grabbing' : 'grab' }}
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={endDrag}
          onPointerLeave={endDrag}
        >
          <defs>
            {/* Parchment paper texture */}
            <radialGradient id="wm-paper" cx="50%" cy="45%" r="75%">
              <stop offset="0%" stopColor="#3a3328" />
              <stop offset="100%" stopColor="#241f18" />
            </radialGradient>
            {/* Fog-of-war cloud gradient */}
            <radialGradient id="wm-fog">
              <stop offset="0%" stopColor="rgba(210,210,222,0.9)" />
              <stop offset="60%" stopColor="rgba(185,185,200,0.6)" />
              <stop offset="100%" stopColor="rgba(150,150,168,0)" />
            </radialGradient>
            {/* Per-terrain radial gradients */}
            {Array.from(terrains.entries()).map(([terrain, vis]) => (
              <radialGradient key={`grad-${terrain}`} id={`grad-${terrain}`} cx="42%" cy="38%" r="70%">
                <stop offset="0%" stopColor={vis.accent} />
                <stop offset="100%" stopColor={vis.fill} />
              </radialGradient>
            ))}
            {/* Per-terrain texture patterns */}
            {Array.from(patterns).map((pat) => (
              <pattern
                key={`pat-${pat}`}
                id={`pat-${pat}`}
                width={pat === 'snow' || pat === 'roofs' ? 7 : 8}
                height={pat === 'snow' || pat === 'roofs' ? 7 : pat === 'grass' ? 6 : 8}
                patternUnits="userSpaceOnUse"
              >
                {PATTERN_DEFS[pat] ?? null}
              </pattern>
            ))}
            {/* Soft glow for the current location */}
            <filter id="wm-glow" x="-60%" y="-60%" width="220%" height="220%">
              <feGaussianBlur stdDeviation="1.1" result="b" />
              <feMerge>
                <feMergeNode in="b" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>
            {/* Clip the map content to the inner frame */}
            <clipPath id="wm-clip">
              <rect x="1.5" y="1.5" width={VIEW - 3} height={VIEW - 3} rx="2" />
            </clipPath>
          </defs>

          {/* Paper background */}
          <rect x="0" y="0" width={VIEW} height={VIEW} fill="url(#wm-paper)" />

          {/* Transformable map content (pan + zoom) */}
          <g clipPath="url(#wm-clip)">
            <g transform={`translate(${view.x} ${view.y}) scale(${view.zoom})`}>
              {/* --- connection roads --- */}
              {edges.map(({ a, b }, i) => {
                const isTravelRoute =
                  (a.id === map.current_region_id && reachable.has(b.id)) ||
                  (b.id === map.current_region_id && reachable.has(a.id))
                const bothSeen = discovered.has(a.id) && discovered.has(b.id)
                return (
                  <line
                    key={`edge-${i}`}
                    x1={toX(a.coordinates[0])}
                    y1={toY(a.coordinates[1])}
                    x2={toX(b.coordinates[0])}
                    y2={toY(b.coordinates[1])}
                    stroke={isTravelRoute ? '#d4a857' : bothSeen ? '#5a4f3e' : '#3a3328'}
                    strokeWidth={(isTravelRoute ? 1.0 : 0.5) / view.zoom}
                    strokeDasharray={isTravelRoute ? '0' : bothSeen ? '1.4 1.6' : '0.8 2.2'}
                    opacity={bothSeen ? 0.85 : 0.4}
                  />
                )
              })}

              {/* --- animated travel route (marching ants) --- */}
              {routePath && routePath.length >= 2 && (
                <line
                  x1={toX(routePath[0][0])}
                  y1={toY(routePath[0][1])}
                  x2={toX(routePath[1][0])}
                  y2={toY(routePath[1][1])}
                  stroke="#f3d27a"
                  strokeWidth={1.1 / view.zoom}
                  strokeLinecap="round"
                  strokeDasharray={`${2 / view.zoom} ${1.4 / view.zoom}`}
                  opacity={0.95}
                >
                  <animate
                    attributeName="stroke-dashoffset"
                    from={`${3.4 / view.zoom}`}
                    to="0"
                    dur="0.55s"
                    repeatCount="indefinite"
                  />
                </line>
              )}

              {/* --- region nodes --- */}
              {map.regions.map((r) => {
                const cx = toX(r.coordinates[0])
                const cy = toY(r.coordinates[1])
                const isCurrent = r.id === map.current_region_id
                const canTravel = reachable.has(r.id)
                const isDiscovered = discovered.has(r.id)

                // Fog of war: undiscovered regions become cloud.
                if (!isDiscovered) {
                  return (
                    <g key={r.id} transform={`translate(${cx} ${cy})`} opacity={0.9}>
                      <circle r={3.2 / view.zoom} fill="url(#wm-fog)" />
                      <circle cx={-1.4} cy={-1.2} r={2.0 / view.zoom} fill="url(#wm-fog)" />
                      <circle cx={1.6} cy={0.6} r={2.2 / view.zoom} fill="url(#wm-fog)" />
                    </g>
                  )
                }

                const vis = r.visual
                const nodeR = (isCurrent ? 4.0 : 3.5) / view.zoom
                return (
                  <g
                    key={r.id}
                    transform={`translate(${cx} ${cy})`}
                    className={canTravel && !traveling ? 'cursor-pointer' : 'cursor-default'}
                    onClick={() => handleNodeClick(r)}
                    onPointerEnter={() => setHoveredId(r.id)}
                    onPointerLeave={() => setHoveredId((h) => (h === r.id ? null : h))}
                  >
                    {/* Pulsing aura on current location */}
                    {isCurrent && (
                      <circle
                        r={6 / view.zoom}
                        fill="none"
                        stroke="#e8c46a"
                        strokeWidth={0.5 / view.zoom}
                      >
                        <animate
                          attributeName="r"
                          values={`${4 / view.zoom};${7 / view.zoom};${4 / view.zoom}`}
                          dur="2.4s"
                          repeatCount="indefinite"
                        />
                        <animate attributeName="opacity" values="0.9;0.15;0.9" dur="2.4s" repeatCount="indefinite" />
                      </circle>
                    )}

                    {/* Terrain body: radial gradient + texture pattern overlay */}
                    <circle r={nodeR} fill={`url(#grad-${r.terrain})`} stroke={vis.stroke} strokeWidth={(isCurrent ? 0.9 : 0.5) / view.zoom} />
                    <circle r={nodeR} fill={`url(#pat-${vis.pattern})`} opacity={0.9} style={{ pointerEvents: 'none' }} />

                    {/* Terrain icon */}
                    <text
                      textAnchor="middle"
                      dominantBaseline="central"
                      fontSize={(isCurrent ? 3.8 : 3.3) / view.zoom}
                      style={{ pointerEvents: 'none' }}
                    >
                      {r.icon}
                    </text>

                    {/* Reachable badge */}
                    {canTravel && !isCurrent && (
                      <circle
                        r={1.0 / view.zoom}
                        cx={nodeR * 0.78}
                        cy={-nodeR * 0.78}
                        fill="#86efac"
                        stroke="#16a34a"
                        strokeWidth={0.35 / view.zoom}
                      />
                    )}
                  </g>
                )
              })}

              {/* --- region name labels (discovered only) --- */}
              {map.regions.map((r) => {
                if (!discovered.has(r.id)) return null
                const cx = toX(r.coordinates[0])
                const cy = toY(r.coordinates[1])
                const isCurrent = r.id === map.current_region_id
                return (
                  <text
                    key={`label-${r.id}`}
                    x={cx}
                    y={cy + (6.5 / view.zoom)}
                    textAnchor="middle"
                    fontSize={2.6 / view.zoom}
                    fill={isCurrent ? '#f3e9d2' : '#b9a888'}
                    fontWeight={isCurrent ? 700 : 400}
                    style={{ pointerEvents: 'none' }}
                  >
                    {r.name.length > 16 ? r.name.slice(0, 15) + '…' : r.name}
                  </text>
                )
              })}
            </g>
          </g>

          {/* === Decorative frame (fixed, not pannable) === */}
          <rect x="1.5" y="1.5" width={VIEW - 3} height={VIEW - 3} rx="2" fill="none" stroke="#8a6d3b" strokeWidth="0.6" />
          <rect x="3" y="3" width={VIEW - 6} height={VIEW - 6} rx="1.5" fill="none" stroke="#5a4528" strokeWidth="0.25" />

          {/* === Compass rose (top-right) === */}
          <g transform={`translate(${VIEW - 9} 9)`} opacity={0.85}>
            <circle r="4.4" fill="rgba(20,16,12,0.55)" stroke="#8a6d3b" strokeWidth="0.3" />
            <path d="M0 -3.6 L0.9 0 L0 3.6 L-0.9 0 Z" fill="#d4a857" />
            <path d="M-3.6 0 L0 0.9 L3.6 0 L0 -0.9 Z" fill="#8a6d3b" opacity="0.7" />
            <circle r="0.5" fill="#f3e9d2" />
            <text x="0" y="-3.6" textAnchor="middle" fontSize="1.6" fill="#e8c46a" fontWeight="700">N</text>
          </g>

          {/* === Scale bar (bottom-left) === */}
          <g transform="translate(6 94)" opacity={0.8}>
            <line x1="0" y1="0" x2="10" y2="0" stroke="#b9a888" strokeWidth="0.4" />
            <line x1="0" y1="-1" x2="0" y2="1" stroke="#b9a888" strokeWidth="0.4" />
            <line x1="5" y1="-0.6" x2="5" y2="0.6" stroke="#b9a888" strokeWidth="0.3" />
            <line x1="10" y1="-1" x2="10" y2="1" stroke="#b9a888" strokeWidth="0.4" />
            <text x="5" y="-1.4" textAnchor="middle" fontSize="1.5" fill="#a89884">~1 day's ride</text>
          </g>
        </svg>

        {/* Zoom controls */}
        <div className="absolute right-2 bottom-2 flex flex-col gap-1">
          <button
            onClick={() => zoomBy(1.2)}
            title="Zoom in"
            className="w-7 h-7 rounded bg-parchment-800/90 border border-amber-700/60 text-parchment-200 text-lg leading-none hover:bg-parchment-700 transition-colors"
          >+</button>
          <button
            onClick={() => zoomBy(1 / 1.2)}
            title="Zoom out"
            className="w-7 h-7 rounded bg-parchment-800/90 border border-amber-700/60 text-parchment-200 text-lg leading-none hover:bg-parchment-700 transition-colors"
          >−</button>
          <button
            onClick={resetView}
            title="Reset view"
            className="w-7 h-7 rounded bg-parchment-800/90 border border-amber-700/60 text-parchment-200 text-xs leading-none hover:bg-parchment-700 transition-colors"
          >⤢</button>
        </div>

        {/* Hint */}
        <div className="absolute left-2 top-2 text-[9px] text-parchment-600 italic pointer-events-none">
          drag to pan · scroll to zoom
        </div>
      </div>

      {/* Legend */}
      <div className="flex flex-wrap gap-x-3 gap-y-1 text-[10px] text-parchment-500 px-1">
        <span className="flex items-center gap-1"><span className="inline-block w-2.5 h-2.5 rounded-full bg-[#7c2d3f] border border-amber-300" /> Current</span>
        <span className="flex items-center gap-1"><span className="inline-block w-2.5 h-2.5 rounded-full bg-[#3b4a63] border border-green-300" /> Reachable</span>
        <span className="flex items-center gap-1"><span className="inline-block w-2.5 h-2.5 rounded-full bg-[#4a4034]" /> Visited</span>
        <span className="flex items-center gap-1"><span className="inline-block w-2.5 h-2.5 rounded-full bg-slate-400/70" /> Unexplored (fog)</span>
      </div>

      {/* Selected region detail */}
      {selected && (
        <div className="panel">
          <div className="flex items-start justify-between gap-2">
            <div>
              <h3 className="font-fantasy text-lg text-parchment-200 flex items-center gap-2">
                <span className="text-2xl">{selected.icon}</span>
                {selected.name}
              </h3>
              <div className="text-xs text-parchment-500 uppercase tracking-wide mt-0.5">
                {selected.terrain}
                {selected.id === map.current_region_id && <span className="ml-2 text-amber-400">● You are here</span>}
              </div>
            </div>
            {reachable.has(selected.id) && selected.id !== map.current_region_id && (
              <button
                className="btn-primary text-sm px-3 py-1"
                disabled={traveling}
                onClick={() => onTravel(selected.id)}
              >
                {traveling ? 'Traveling…' : '🧭 Travel Here'}
              </button>
            )}
          </div>
          {selected.description && (
            <p className="text-sm text-parchment-400 mt-2 leading-relaxed">{selected.description}</p>
          )}
          {selected.settlements.length > 0 && (
            <div className="mt-2">
              <span className="text-xs text-parchment-500 uppercase">Settlements: </span>
              <span className="text-sm text-parchment-300">{selected.settlements.join(', ')}</span>
            </div>
          )}
          {selected.dangers.length > 0 && (
            <div className="mt-1">
              <span className="text-xs text-parchment-500 uppercase">Known dangers: </span>
              <span className="text-sm text-blood-400">{selected.dangers.join(', ')}</span>
            </div>
          )}
          {!reachable.has(selected.id) && selected.id !== map.current_region_id && (
            <p className="text-xs text-parchment-600 italic mt-2">No direct route from your current location.</p>
          )}
        </div>
      )}
    </div>
  )
}
