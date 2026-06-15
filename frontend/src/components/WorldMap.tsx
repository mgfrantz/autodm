import { useState } from 'react'
import type { WorldMapData, RegionNode } from '../types'

interface WorldMapProps {
  map: WorldMapData
  traveling: boolean
  onTravel: (regionId: string) => void
}

/**
 * Visual region explorer. Renders the world as an SVG node graph: regions are
 * positioned by their normalized coordinates, connections are drawn as roads,
 * and the player can click any reachable region to travel there.
 */
export default function WorldMap({ map, traveling, onTravel }: WorldMapProps) {
  const [selectedId, setSelectedId] = useState<string | null>(null)

  // SVG coordinate space — leave a margin so nodes/icons don't clip.
  const PAD = 10
  const SIZE = 100
  const toX = (nx: number) => PAD + nx * (SIZE - 2 * PAD)
  const toY = (ny: number) => PAD + ny * (SIZE - 2 * PAD)

  const reachable = new Set(map.reachable_region_ids)
  const visited = new Set(map.visited_region_ids)
  const regionById = new Map(map.regions.map((r) => [r.id, r]))

  const selected = selectedId ? regionById.get(selectedId) ?? null : map.current_region

  // Build the list of connection edges (deduped).
  const edges: { a: RegionNode; b: RegionNode }[] = []
  const seen = new Set<string>()
  for (const r of map.regions) {
    for (const cid of r.connections) {
      const other = regionById.get(cid)
      if (!other) continue
      const key = [r.id, cid].sort().join('|')
      if (seen.has(key)) continue
      seen.add(key)
      edges.push({ a: r, b: other })
    }
  }

  return (
    <div className="space-y-3">
      {/* The map itself */}
      <div className="relative rounded-lg border border-parchment-700 bg-gradient-to-br from-parchment-900/80 to-blood-950/40 p-2">
        <svg viewBox={`0 0 ${SIZE} ${SIZE}`} className="w-full h-auto" style={{ aspectRatio: '1 / 1' }}>
          {/* Connection roads */}
          {edges.map(({ a, b }, i) => {
            const isTravelRoute =
              (a.id === map.current_region_id && reachable.has(b.id)) ||
              (b.id === map.current_region_id && reachable.has(a.id))
            return (
              <line
                key={`edge-${i}`}
                x1={toX(a.coordinates[0])}
                y1={toY(a.coordinates[1])}
                x2={toX(b.coordinates[0])}
                y2={toY(b.coordinates[1])}
                stroke={isTravelRoute ? '#d4a857' : '#4a4034'}
                strokeWidth={isTravelRoute ? 0.9 : 0.5}
                strokeDasharray={isTravelRoute ? '0' : '1.5 1.5'}
                opacity={0.8}
              />
            )
          })}

          {/* Region nodes */}
          {map.regions.map((r) => {
            const cx = toX(r.coordinates[0])
            const cy = toY(r.coordinates[1])
            const isCurrent = r.id === map.current_region_id
            const canTravel = reachable.has(r.id)
            const wasVisited = visited.has(r.id)
            const dim = !isCurrent && !canTravel && !wasVisited

            const fill = isCurrent
              ? '#7c2d3f'
              : canTravel
                ? '#3b4a63'
                : wasVisited
                  ? '#4a4034'
                  : '#2a241d'
            const stroke = isCurrent
              ? '#e8c46a'
              : canTravel
                ? '#9bb3d4'
                : '#6b5d4a'

            return (
              <g
                key={r.id}
                transform={`translate(${cx} ${cy})`}
                className={canTravel && !traveling ? 'cursor-pointer' : 'cursor-default'}
                onClick={() => {
                  setSelectedId(r.id)
                  if (canTravel && !traveling && !isCurrent) {
                    onTravel(r.id)
                  }
                }}
                opacity={dim ? 0.55 : 1}
              >
                {/* Pulsing ring on current location */}
                {isCurrent && (
                  <circle r={5} fill="none" stroke="#e8c46a" strokeWidth={0.4}>
                    <animate attributeName="r" values="3.5;5.5;3.5" dur="2.4s" repeatCount="indefinite" />
                    <animate attributeName="opacity" values="0.9;0.2;0.9" dur="2.4s" repeatCount="indefinite" />
                  </circle>
                )}
                <circle r={3.4} fill={fill} stroke={stroke} strokeWidth={isCurrent ? 0.8 : 0.5} />
                {/* Terrain icon */}
                <text textAnchor="middle" dominantBaseline="central" fontSize={3.4} style={{ pointerEvents: 'none' }}>
                  {r.icon}
                </text>
                {/* Reachable badge */}
                {canTravel && !isCurrent && (
                  <circle r={0.9} cx={3} cy={-3} fill="#86efac" stroke="#16a34a" strokeWidth={0.3} />
                )}
              </g>
            )
          })}

          {/* Region name labels */}
          {map.regions.map((r) => {
            const cx = toX(r.coordinates[0])
            const cy = toY(r.coordinates[1])
            const isCurrent = r.id === map.current_region_id
            return (
              <text
                key={`label-${r.id}`}
                x={cx}
                y={cy + 6.5}
                textAnchor="middle"
                fontSize={2.6}
                fill={isCurrent ? '#f3e9d2' : '#a89884'}
                fontWeight={isCurrent ? 700 : 400}
                style={{ pointerEvents: 'none' }}
              >
                {r.name.length > 16 ? r.name.slice(0, 15) + '…' : r.name}
              </text>
            )
          })}
        </svg>

        {/* Legend */}
        <div className="flex flex-wrap gap-x-3 gap-y-1 text-[10px] text-parchment-500 mt-1 px-1">
          <span className="flex items-center gap-1"><span className="inline-block w-2 h-2 rounded-full bg-[#7c2d3f] border border-amber-300" /> Current</span>
          <span className="flex items-center gap-1"><span className="inline-block w-2 h-2 rounded-full bg-[#3b4a63] border border-blue-300" /> Reachable</span>
          <span className="flex items-center gap-1"><span className="inline-block w-2 h-2 rounded-full bg-[#4a4034]" /> Visited</span>
          <span className="flex items-center gap-1"><span className="inline-block w-2 h-2 rounded-full bg-[#2a241d] opacity-60" /> Unknown</span>
        </div>
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
            <p className="text-xs text-parchment-600 italic mt-2">
              No direct route from your current location.
            </p>
          )}
        </div>
      )}
    </div>
  )
}
