'use client'

import { useEffect, useMemo, useRef, useState, type PointerEvent as ReactPointerEvent } from 'react'
import { Minus, Plus, RotateCcw } from 'lucide-react'
import {
  bubbleRadius,
  featureCentroid,
  featurePath,
  fitProjection,
  rampColor,
  valuesByProvince,
  type GeoCollection,
  type GeoDetection,
} from '../../lib/geo'
import { formatBusinessValue } from '../../lib/businessPresentation'
import { workspaceColumnLabel } from '../../lib/workspaceTableLabels'

const GEO_URL = '/geo/indonesia-provinces.json'
let boundariesPromise: Promise<GeoCollection> | null = null

/** Loaded once per page; a failed load is retried on the next open. */
function loadBoundaries(): Promise<GeoCollection> {
  if (!boundariesPromise) {
    boundariesPromise = fetch(GEO_URL)
      .then(response => {
        if (!response.ok) throw new Error(`HTTP ${response.status}`)
        return response.json() as Promise<GeoCollection>
      })
      .catch(error => {
        boundariesPromise = null
        throw error
      })
  }
  return boundariesPromise
}

type Mode = 'areas' | 'bubbles'
type View = { x: number; y: number; k: number }
const HOME: View = { x: 0, y: 0, k: 1 }

type Props = {
  columns: string[]
  rows: Record<string, unknown>[]
  detection: GeoDetection
  metric?: string
  unitFormat?: string | null
}

export function ResultMap({ rows, detection, metric, unitFormat }: Props) {
  const [collection, setCollection] = useState<GeoCollection | null>(null)
  const [failed, setFailed] = useState(false)
  const [mode, setMode] = useState<Mode>('areas')
  const [view, setView] = useState<View>(HOME)
  const [hover, setHover] = useState<{ name: string; x: number; y: number } | null>(null)
  const drag = useRef<{ x: number; y: number; view: View } | null>(null)
  const frame = useRef<HTMLDivElement>(null)

  useEffect(() => {
    let alive = true
    loadBoundaries().then(
      data => alive && setCollection(data),
      () => alive && setFailed(true),
    )
    return () => {
      alive = false
    }
  }, [])

  const values = useMemo(() => valuesByProvince(rows, detection), [rows, detection])
  const stats = useMemo(() => {
    const list = [...values.values()]
    return { min: Math.min(...list), max: Math.max(...list) }
  }, [values])
  const geometry = useMemo(() => {
    if (!collection) return null
    const projection = fitProjection(collection)
    return {
      projection,
      items: collection.features.map(feature => ({
        name: feature.properties.name,
        path: featurePath(feature, projection),
        centre: featureCentroid(feature, projection),
      })),
    }
  }, [collection])

  const label = workspaceColumnLabel(detection.valueColumn, metric)
  const format = (value: number) => formatBusinessValue(detection.valueColumn, value, metric, unitFormat)
  const ranking = useMemo(() => [...values.entries()].sort((a, b) => b[1] - a[1]), [values])

  if (failed) {
    return (
      <p className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900" role="status">
        The map boundaries could not be loaded. The Table tab has the same numbers.
      </p>
    )
  }
  if (!geometry) {
    return (
      <p className="py-10 text-center text-sm text-slate-500" role="status">
        Loading map…
      </p>
    )
  }

  const { projection, items } = geometry
  const zoom = (factor: number) =>
    setView(current => {
      const k = Math.min(8, Math.max(1, current.k * factor))
      const cx = projection.width / 2
      const cy = projection.height / 2
      return { k, x: cx - ((cx - current.x) / current.k) * k, y: cy - ((cy - current.y) / current.k) * k }
    })
  const onPointerDown = (event: ReactPointerEvent<SVGSVGElement>) => {
    drag.current = { x: event.clientX, y: event.clientY, view }
  }
  const onPointerMove = (event: ReactPointerEvent<SVGSVGElement>) => {
    if (!drag.current || !frame.current) return
    const scale = projection.width / frame.current.clientWidth
    setView({
      ...drag.current.view,
      x: drag.current.view.x + (event.clientX - drag.current.x) * scale,
      y: drag.current.view.y + (event.clientY - drag.current.y) * scale,
    })
  }
  const track = (name: string, event: ReactPointerEvent<SVGElement>) => {
    const box = frame.current?.getBoundingClientRect()
    if (box) setHover({ name, x: event.clientX - box.left, y: event.clientY - box.top })
  }

  return (
    <div className="space-y-4" data-testid="result-map">
      <div>
        <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
          <div className="inline-flex rounded-lg border border-slate-200 bg-white p-0.5 text-xs font-semibold" role="group" aria-label="Map style">
            {(['areas', 'bubbles'] as const).map(option => (
              <button
                key={option}
                type="button"
                aria-pressed={mode === option}
                onClick={() => setMode(option)}
                className={`rounded-md px-3 py-1.5 transition-colors ${
                  mode === option ? 'bg-cloudera-navy text-white' : 'text-slate-600 hover:text-cloudera-navy'
                }`}
              >
                {option === 'areas' ? 'Areas' : 'Bubbles'}
              </button>
            ))}
          </div>
          <div className="inline-flex gap-1" role="group" aria-label="Zoom">
            <button type="button" aria-label="Zoom in" onClick={() => zoom(1.5)} className="rounded-md border border-slate-200 bg-white p-1.5 text-slate-600 hover:text-cloudera-navy"><Plus className="h-4 w-4" /></button>
            <button type="button" aria-label="Zoom out" onClick={() => zoom(1 / 1.5)} className="rounded-md border border-slate-200 bg-white p-1.5 text-slate-600 hover:text-cloudera-navy"><Minus className="h-4 w-4" /></button>
            <button type="button" aria-label="Reset view" onClick={() => setView(HOME)} className="rounded-md border border-slate-200 bg-white p-1.5 text-slate-600 hover:text-cloudera-navy"><RotateCcw className="h-4 w-4" /></button>
          </div>
        </div>

        <div ref={frame} className="relative overflow-hidden rounded-xl border border-slate-200 bg-gradient-to-b from-sky-50 to-white">
          <svg
            viewBox={`0 0 ${projection.width} ${projection.height}`}
            className="block h-auto w-full cursor-grab touch-none select-none active:cursor-grabbing"
            role="img"
            aria-label={`Map of ${label} by province`}
            onPointerDown={onPointerDown}
            onPointerMove={onPointerMove}
            onPointerUp={() => (drag.current = null)}
            onPointerLeave={() => {
              drag.current = null
              setHover(null)
            }}
            onWheel={event => {
              if (event.ctrlKey || event.metaKey) zoom(event.deltaY < 0 ? 1.2 : 1 / 1.2)
            }}
          >
            <g transform={`translate(${view.x} ${view.y}) scale(${view.k})`}>
              {items.map(item => {
                const value = values.get(item.name)
                const filled = mode === 'areas' && value !== undefined
                return (
                  <path
                    key={item.name}
                    d={item.path}
                    data-province={item.name}
                    fill={filled ? rampColor(value, stats.min, stats.max) : '#e8ebf3'}
                    stroke="#ffffff"
                    strokeWidth={0.7 / view.k}
                    onPointerMove={event => track(item.name, event)}
                  >
                    <title>{value === undefined ? `${item.name}: no data` : `${item.name}: ${format(value)}`}</title>
                  </path>
                )
              })}
              {mode === 'bubbles' &&
                items.map(item => {
                  const value = values.get(item.name)
                  if (value === undefined) return null
                  return (
                    <circle
                      key={item.name}
                      cx={item.centre[0]}
                      cy={item.centre[1]}
                      r={bubbleRadius(value, stats.max) / Math.sqrt(view.k)}
                      fill={rampColor(value, stats.min, stats.max)}
                      fillOpacity={0.9}
                      stroke="#ffffff"
                      strokeWidth={1.2 / view.k}
                      data-bubble={item.name}
                      onPointerMove={event => track(item.name, event)}
                    />
                  )
                })}
            </g>
          </svg>
          {hover && (
            <div
              className="pointer-events-none absolute z-10 -translate-x-1/2 -translate-y-full rounded-md bg-cloudera-navy px-2.5 py-1.5 text-xs text-white shadow-lg"
              style={{ left: hover.x, top: hover.y - 8 }}
            >
              <div className="font-semibold">{hover.name}</div>
              <div>{values.has(hover.name) ? `${label}: ${format(values.get(hover.name)!)}` : 'No data'}</div>
            </div>
          )}
        </div>
        <div className="mt-2 flex items-center gap-3 text-[11px] text-slate-600" data-testid="map-legend">
          <span className="shrink-0 font-semibold text-slate-700">{label}</span>
          <span className="shrink-0">{format(stats.min)}</span>
          <div className="h-2 min-w-0 flex-1 rounded-full" style={{ background: `linear-gradient(to right, ${rampColor(0, 0, 1)}, ${rampColor(1, 0, 1)})` }} />
          <span className="shrink-0">{format(stats.max)}</span>
        </div>
        <p className="mt-1 text-[11px] text-slate-400">Drag to pan, use the buttons (or Ctrl and scroll) to zoom. Boundaries: Natural Earth, public domain.</p>
        {detection.unmatched.length > 0 && (
          <p className="mt-2 text-xs text-amber-800" role="note">
            Not placed on the map (name not recognised): {detection.unmatched.join(', ')}.
          </p>
        )}
      </div>

      <ol className="grid gap-x-6 gap-y-1 text-sm sm:grid-cols-2" aria-label={`${label} by province, highest first`}>
        {ranking.slice(0, 10).map(([name, value], index) => (
          <li
            key={name}
            onMouseEnter={() => setHover(null)}
            className="flex items-center justify-between gap-2 rounded-md px-2 py-1.5 hover:bg-slate-50"
          >
            <span className="flex items-center gap-2">
              <span className="w-4 text-right text-xs text-slate-400">{index + 1}</span>
              <span className="h-2.5 w-2.5 rounded-sm" style={{ background: rampColor(value, stats.min, stats.max) }} aria-hidden />
              <span className="text-slate-800">{name}</span>
            </span>
            <span className="font-semibold tabular-nums text-cloudera-navy">{format(value)}</span>
          </li>
        ))}
      </ol>
    </div>
  )
}
