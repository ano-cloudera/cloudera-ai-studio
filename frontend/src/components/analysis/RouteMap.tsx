'use client'

import { useEffect, useMemo, useRef, useState, type PointerEvent as ReactPointerEvent } from 'react'
import { Minus, Plus, RotateCcw } from 'lucide-react'

import { featureCentroid, featurePath, fitProjection, type GeoCollection } from '../../lib/geo'
import {
  colourRange,
  curvePath,
  missesTarget,
  placeLabels,
  routeQuestion,
  routesOf,
  severity,
  type LabelRequest,
  type Route,
  type RouteDetection,
} from '../../lib/routes'
import { formatBusinessValue } from '../../lib/businessPresentation'
import { workspaceColumnLabel } from '../../lib/workspaceTableLabels'
import { GRAPHIC_FONT } from '../../lib/vizType'
import { loadBoundaries } from './ResultMap'
import { answerLocale } from '../../lib/chartMetric'
import type { ChatResponse } from '../../types/api'

/** What a route map reads from an answer besides its rows: the metric, its format, which way is good, the target, the overall value. */
export function routeMapContext(response: ChatResponse) {
  const data = response.data
  return {
    metric: data.governed_metric ?? undefined,
    metricLabel: data.governed_metric_display_name ?? null,
    unitFormat: data.unit_format ?? null,
    better: data.metric_better ?? null,
    target: data.metric_target ?? null,
    overall: data.overall_value ?? null,
    locale: answerLocale(response),
    language: response.language ?? null,
  }
}

type View = { x: number; y: number; k: number }

type Props = {
  rows: Record<string, unknown>[]
  detection: RouteDetection
  /** The governed metric of the value column, for its label and format. */
  metric?: string
  metricLabel?: string | null
  unitFormat?: string | null
  /** Which way is good and the target, when the model's author declared them; without them nothing is called worse. */
  better?: 'up' | 'down' | null
  target?: number | null
  overall?: number | null
  locale?: string
  /** The language of the answer, for the question asked about one route. */
  language?: string | null
  /** Asks the question about the selected route as the next turn of the conversation. */
  onAsk?: (question: string) => void
  /** The version inside the chat: one line about the selected route above the map, the top three routes below it. */
  compact?: boolean
}

const INDIGO = '#7C7AF7'
const NAVY = '#13003D'
const PALE = [253, 200, 166]
const DEEP = [184, 42, 4]

/** The colour of a route: deep orange the worse it is; calm indigo when it meets a declared target. */
export function routeColor(sev: number, miss: boolean | null): string {
  if (miss === false) return INDIGO
  const t = Math.min(1, Math.max(0, sev))
  const mix = PALE.map((low, i) => Math.round(low + (DEEP[i] - low) * t))
  return `rgb(${mix[0]}, ${mix[1]}, ${mix[2]})`
}

/** A route counted on far fewer records than the others: its figure is shown, with a note to read it with care. */
export function fewRecords(weight: number | null, weights: number[]): boolean {
  if (weight === null || weights.length < 3) return false
  const sorted = [...weights].sort((a, b) => a - b)
  const median = sorted[Math.floor(sorted.length / 2)]
  return median > 0 && weight < median * 0.1
}

const iconButton =
  'grid h-11 w-11 place-items-center rounded-md border border-slate-200 bg-white text-slate-600 transition-colors hover:text-cloudera-navy sm:h-8 sm:w-8'

export function RouteMap({
  rows,
  detection,
  metric,
  metricLabel,
  unitFormat,
  better,
  target,
  overall,
  locale,
  language,
  onAsk,
  compact = false,
}: Props) {
  const [collection, setCollection] = useState<GeoCollection | null>(null)
  const [failed, setFailed] = useState(false)
  const [view, setView] = useState<View | null>(null)
  const [hover, setHover] = useState<{ key: string; x: number; y: number } | null>(null)
  const [shown, setShown] = useState(0)
  const drag = useRef<{ x: number; y: number; view: View; moved: boolean } | null>(null)
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

  // The drawn width of the map, so lines, dots and labels keep their size on screen whatever the panel's width.
  useEffect(() => {
    const node = frame.current
    if (!node || typeof ResizeObserver === 'undefined') return
    const observer = new ResizeObserver(entries => setShown(entries[0]?.contentRect.width ?? 0))
    observer.observe(node)
    return () => observer.disconnect()
  }, [collection])

  const routes = useMemo(() => routesOf(rows, detection), [rows, detection])
  const range = useMemo(() => colourRange(routes.map(route => route.value), better), [routes, better])
  const weights = useMemo(() => routes.map(route => route.weight ?? 0), [routes])
  const maxWeight = Math.max(0, ...weights)
  const maxValue = Math.max(0, ...routes.map(route => route.value))
  const ranked = useMemo(
    () => [...routes].sort((a, b) => (better === 'up' ? a.value - b.value : b.value - a.value)),
    [routes, better],
  )
  const [selected, setSelected] = useState<string | null>(() => ranked[0]?.key ?? null)
  // The worst route is open from the start; the others fade only once the reader picks one, so the first look is the whole picture.
  const [picked, setPicked] = useState(false)
  const choose = (key: string) => {
    setSelected(key)
    setPicked(true)
  }

  const label = metricLabel?.trim() || workspaceColumnLabel(detection.valueColumn, metric)
  const weightLabel = detection.weightColumn ? workspaceColumnLabel(detection.weightColumn) : null
  const format = (value: number) => formatBusinessValue(detection.valueColumn, value, metric, unitFormat, locale)
  const formatWeight = (value: number | null) => (detection.weightColumn && value !== null ? formatBusinessValue(detection.weightColumn, value, undefined, undefined, locale) : '')

  const geometry = useMemo(() => {
    if (!collection) return null
    const projection = fitProjection(collection, undefined, 18)
    const centres = new Map<string, [number, number]>()
    const shapes = collection.features.map(feature => {
      centres.set(feature.properties.name, featureCentroid(feature, projection))
      return { name: feature.properties.name, path: featurePath(feature, projection) }
    })
    const at = (route: Route): { from: [number, number]; to: [number, number] } | null => {
      const [lat, lon] = detection.origins[route.origin]
      const from = projection.project(lon, lat)
      const end = detection.destinations?.[route.destination]
      const to = end ? projection.project(end[1], end[0]) : route.province ? centres.get(route.province) : undefined
      return to ? { from, to } : null
    }
    const placed = routes.flatMap(route => {
      const ends = at(route)
      if (!ends) return []
      // A route that starts and ends in the same place (a terminal inside the province it serves) gets a short bow of its own.
      const near = Math.hypot(ends.to[0] - ends.from[0], ends.to[1] - ends.from[1]) < 6
      const to: [number, number] = near ? [ends.to[0] + 9, ends.to[1] + 7] : ends.to
      return [{ route, from: ends.from, to, ...curvePath(ends.from, to, near ? 0.6 : 0.2) }]
    })
    // Open on the routes, not on the whole archipelago: the box around their ends, with room for the curves and labels.
    const xs = placed.flatMap(item => [item.from[0], item.to[0], item.mid[0]])
    const ys = placed.flatMap(item => [item.from[1], item.to[1], item.mid[1]])
    const pad = 40
    const bw = Math.max(...xs) - Math.min(...xs) + 2 * pad
    const bh = Math.max(...ys) - Math.min(...ys) + 2 * pad
    const k = Math.min(5, Math.max(1, Math.min(projection.width / bw, projection.height / bh)))
    const cx = (Math.max(...xs) + Math.min(...xs)) / 2
    const cy = (Math.max(...ys) + Math.min(...ys)) / 2
    const home: View = placed.length ? { k, x: projection.width / 2 - cx * k, y: projection.height / 2 - cy * k } : { x: 0, y: 0, k: 1 }
    const destinations = new Set(placed.map(item => item.route.province).filter(Boolean) as string[])
    return { projection, shapes, placed, home, destinations }
  }, [collection, routes, detection])

  if (failed) {
    return (
      <p className="viz-text rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 !text-amber-900" role="status">
        The map boundaries could not be loaded. The Table tab has the same numbers.
      </p>
    )
  }
  if (!geometry) {
    return (
      <p className="viz-caption py-10 text-center" role="status">
        Loading map…
      </p>
    )
  }

  const { projection, shapes, placed, home, destinations } = geometry
  const current = view ?? home
  // Map units per screen pixel at the current zoom: a dot of 5 px stays 5 px, a label of 11 px stays 11 px.
  const px = (shown > 0 ? projection.width / shown : 1.6) / current.k
  const sev = (value: number) => severity(value, range.low, range.high, better)
  const miss = (value: number) => missesTarget(value, target, better)
  // Worst drawn last, so it sits on top; the selected route above all.
  const order = [...placed].sort((a, b) => sev(a.route.value) - sev(b.route.value))
  const top = order.findIndex(item => item.route.key === selected)
  if (top >= 0) order.push(...order.splice(top, 1))
  const chosen = routes.find(route => route.key === selected) ?? null
  const chosenPlaced = placed.find(item => item.route.key === selected) ?? null
  const rank = chosen ? ranked.findIndex(route => route.key === chosen.key) + 1 : 0
  const worstFirst = Boolean(better)
  const origins = [...new Set(placed.map(item => item.route.origin))]
  const originAt = (name: string): [number, number] => {
    const [lat, lon] = detection.origins[name]
    return projection.project(lon, lat)
  }

  // Place names that never sit on each other: the selected route's two ends first, then the origins of the worst routes.
  const requests: LabelRequest[] = []
  if (chosenPlaced) {
    requests.push({ id: 'to', x: chosenPlaced.to[0], y: chosenPlaced.to[1], text: chosenPlaced.route.destination })
    requests.push({ id: `from:${chosenPlaced.route.origin}`, x: chosenPlaced.from[0], y: chosenPlaced.from[1], text: chosenPlaced.route.origin })
  }
  for (const route of ranked.slice(0, compact ? 4 : 6)) {
    if (!requests.some(request => request.id === `from:${route.origin}`)) {
      const [x, y] = originAt(route.origin)
      requests.push({ id: `from:${route.origin}`, x, y, text: route.origin })
    }
  }
  const visible = {
    x0: -current.x / current.k + 4 * px,
    y0: -current.y / current.k + 4 * px,
    x1: (projection.width - current.x) / current.k - 4 * px,
    y1: (projection.height - current.y) / current.k - 4 * px,
  }
  const labels = placeLabels(requests, px, [...origins.map(originAt), ...placed.map(item => item.to)], visible)

  const zoom = (factor: number) =>
    setView(() => {
      const k = Math.min(12, Math.max(1, current.k * factor))
      const cx = projection.width / 2
      const cy = projection.height / 2
      return { k, x: cx - ((cx - current.x) / current.k) * k, y: cy - ((cy - current.y) / current.k) * k }
    })
  const onPointerDown = (event: ReactPointerEvent<SVGSVGElement>) => {
    drag.current = { x: event.clientX, y: event.clientY, view: current, moved: false }
  }
  const onPointerMove = (event: ReactPointerEvent<SVGSVGElement>) => {
    if (!drag.current || !frame.current) return
    const dx = event.clientX - drag.current.x
    const dy = event.clientY - drag.current.y
    if (Math.hypot(dx, dy) < 4 && !drag.current.moved) return
    drag.current.moved = true
    const scale = projection.width / frame.current.clientWidth
    setView({ ...drag.current.view, x: drag.current.view.x + dx * scale, y: drag.current.view.y + dy * scale })
  }
  const pick = (key: string) => {
    if (drag.current?.moved) return
    choose(key)
  }
  const track = (key: string, event: ReactPointerEvent<SVGElement>) => {
    const box = frame.current?.getBoundingClientRect()
    if (box) setHover({ key, x: event.clientX - box.left, y: event.clientY - box.top })
  }
  const hovered = hover ? routes.find(route => route.key === hover.key) : null
  const extraColumns = chosen
    ? Object.keys(chosen.row).filter(
        column =>
          column !== detection.originColumn &&
          column !== detection.destinationColumn &&
          column !== detection.valueColumn &&
          typeof chosen.row[column] === 'number',
      )
    : []
  const chosenMiss = chosen ? miss(chosen.value) : null
  const high = chosen && typeof overall === 'number' ? chosen.value > overall : chosenMiss === null ? null : better === 'down' ? chosenMiss : !chosenMiss
  const thin = chosen ? fewRecords(chosen.weight, weights) : false
  const list = ranked.slice(0, compact ? 3 : 8)
  const lineWidth = (route: Route) =>
    detection.weightColumn && maxWeight > 0 ? 1.5 + 7 * Math.sqrt((route.weight ?? 0) / maxWeight) : 1.8 + 5 * sev(route.value)
  const askButton =
    onAsk && chosen ? (
      <button
        type="button"
        onClick={() => onAsk(routeQuestion(chosen, label, language, high))}
        className="viz-text rounded-lg border border-cloudera-orange/40 bg-orange-50 px-3 py-2 text-left font-semibold !text-cloudera-navy transition-colors hover:border-cloudera-orange hover:bg-orange-100"
        data-testid="route-ask-why"
      >
        Ask why this route stands out
      </button>
    ) : null
  const targetNote = chosenMiss === true ? `target ${format(target as number)} missed` : chosenMiss === false ? `target ${format(target as number)} met` : null

  const routeList = (
    <ol className="space-y-0.5" aria-label={worstFirst ? 'Routes, worst first' : 'Routes, highest first'}>
      <li className="viz-caption px-2 pb-1 font-semibold">{worstFirst ? 'Routes, worst first' : 'Routes, highest first'}</li>
      {list.map((route, index) => (
        <li key={route.key}>
          <button
            type="button"
            aria-pressed={route.key === selected}
            onClick={() => choose(route.key)}
            className={`viz-text w-full rounded-md px-2 py-1.5 text-left transition-colors ${route.key === selected ? 'bg-violet-50' : 'hover:bg-slate-50'}`}
          >
            <span className="flex items-center justify-between gap-2">
              <span className="flex min-w-0 items-center gap-2">
                <span className="w-4 shrink-0 text-right text-slate-500">{index + 1}</span>
                <span className="truncate text-slate-800">
                  {route.origin} → {route.destination}
                </span>
              </span>
              <span className="shrink-0 font-semibold tabular-nums text-cloudera-navy">{format(route.value)}</span>
            </span>
            {/* How far along the scale the route is, so the ranking reads at a glance. */}
            <span className="ml-6 mt-1 block h-1 rounded-full bg-slate-100" aria-hidden>
              <span
                className="block h-1 rounded-full"
                style={{ width: `${maxValue > 0 ? Math.max(2, (route.value / maxValue) * 100) : 0}%`, background: routeColor(sev(route.value), miss(route.value)) }}
              />
            </span>
          </button>
        </li>
      ))}
      {routes.length > list.length && <li className="viz-caption px-2 pt-1">{routes.length - list.length} more routes in the Table tab</li>}
    </ol>
  )

  return (
    <div className="space-y-3" data-testid="route-map">
      <div className="flex items-center justify-between gap-2">
        <div className="min-w-0">
          <p className="viz-title">
            {label} by route: {workspaceColumnLabel(detection.originColumn)} to {workspaceColumnLabel(detection.destinationColumn)}
          </p>
          {compact && chosen && (
            <p className="viz-text mt-0.5" data-testid="route-summary">
              {worstFirst && rank === 1 ? 'Worst' : `Route ${rank}`}: <span className="font-semibold text-cloudera-navy">{chosen.origin} → {chosen.destination}</span>, {format(chosen.value)}
              {targetNote ? `, ${targetNote}` : ''}
              {thin ? ', few records' : ''}
            </p>
          )}
        </div>
        <div className="inline-flex shrink-0 gap-1" role="group" aria-label="Zoom">
          <button type="button" aria-label="Zoom in" onClick={() => zoom(1.5)} className={iconButton}><Plus className="h-4 w-4" /></button>
          <button type="button" aria-label="Zoom out" onClick={() => zoom(1 / 1.5)} className={iconButton}><Minus className="h-4 w-4" /></button>
          <button type="button" aria-label="Reset view" onClick={() => setView(null)} className={iconButton}><RotateCcw className="h-4 w-4" /></button>
        </div>
      </div>

      <div ref={frame} className="relative overflow-hidden rounded-xl border border-slate-200 bg-[#f4f7fb]">
        <svg
          viewBox={`0 0 ${projection.width} ${projection.height}`}
          className="block h-auto w-full cursor-grab touch-none select-none active:cursor-grabbing"
          role="img"
          aria-label={`Route map of ${label}, ${routes.length} routes`}
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={() => setTimeout(() => (drag.current = null), 0)}
          onPointerLeave={() => {
            drag.current = null
            setHover(null)
          }}
          onWheel={event => {
            if (event.ctrlKey || event.metaKey) zoom(event.deltaY < 0 ? 1.2 : 1 / 1.2)
          }}
        >
          <g transform={`translate(${current.x} ${current.y}) scale(${current.k})`}>
            {shapes.map(shape => (
              <path
                key={shape.name}
                d={shape.path}
                fill={destinations.has(shape.name) ? '#e2e4f3' : '#ebeef4'}
                stroke="#ffffff"
                strokeWidth={0.9}
                vectorEffect="non-scaling-stroke"
              />
            ))}
            {order.map(({ route, d }) => {
              const active = route.key === selected
              const dim = picked && !active
              const width = lineWidth(route)
              return (
                <g key={route.key} data-route={route.key}>
                  {active && <path d={d} fill="none" stroke="#ffffff" strokeWidth={width + 4} strokeLinecap="round" vectorEffect="non-scaling-stroke" />}
                  <path
                    d={d}
                    fill="none"
                    stroke={routeColor(sev(route.value), miss(route.value))}
                    strokeWidth={width}
                    strokeLinecap="round"
                    strokeOpacity={dim ? 0.45 : 1}
                    vectorEffect="non-scaling-stroke"
                  />
                  <path
                    d={d}
                    fill="none"
                    stroke="transparent"
                    strokeWidth={16}
                    vectorEffect="non-scaling-stroke"
                    onPointerMove={event => track(route.key, event)}
                    onClick={() => pick(route.key)}
                    className="cursor-pointer"
                  >
                    <title>{`${route.origin} to ${route.destination}: ${format(route.value)}`}</title>
                  </path>
                </g>
              )
            })}
            {order.map(({ route, to }) => (
              <circle key={`end-${route.key}`} cx={to[0]} cy={to[1]} r={3 * px} fill="#ffffff" stroke={NAVY} strokeWidth={1.3} vectorEffect="non-scaling-stroke" />
            ))}
            {origins.map(name => {
              const [x, y] = originAt(name)
              return <circle key={name} cx={x} cy={y} r={4.5 * px} fill={NAVY} stroke="#ffffff" strokeWidth={1.5} vectorEffect="non-scaling-stroke" />
            })}
            {chosenPlaced && (
              // The selected route's origin, ringed so the eye finds where it starts.
              <circle cx={chosenPlaced.from[0]} cy={chosenPlaced.from[1]} r={8 * px} fill="none" stroke={NAVY} strokeWidth={1.4} vectorEffect="non-scaling-stroke" />
            )}
            {labels.map(item => (
              <text
                key={item.id}
                x={item.lx}
                y={item.ly}
                textAnchor={item.anchor}
                fontSize={GRAPHIC_FONT * px}
                fontWeight={600}
                fill={item.id === 'to' ? '#b82a04' : NAVY}
                stroke="#ffffff"
                strokeWidth={3 * px}
                strokeLinejoin="round"
                paintOrder="stroke"
              >
                {item.text}
              </text>
            ))}
          </g>
        </svg>
        {hover && hovered && (
          <div
            className="viz-caption pointer-events-none absolute z-10 -translate-x-1/2 -translate-y-full rounded-md bg-cloudera-navy px-2.5 py-1.5 !text-white shadow-lg"
            style={{ left: hover.x, top: hover.y - 8 }}
          >
            <div className="font-semibold">
              {hovered.origin} → {hovered.destination}
            </div>
            <div>
              {label}: {format(hovered.value)}
            </div>
            {weightLabel && hovered.weight !== null && (
              <div>
                {weightLabel}: {formatWeight(hovered.weight)}
              </div>
            )}
          </div>
        )}
      </div>

      <div className="viz-caption flex flex-wrap items-center gap-x-5 gap-y-1.5" data-testid="route-legend">
        <span className="flex items-center gap-2">
          <span className="tabular-nums">{format(better === 'up' ? range.high : range.low)}</span>
          <span className="h-2 w-24 rounded-full" style={{ background: `linear-gradient(to right, ${routeColor(0, null)}, ${routeColor(1, null)})` }} aria-hidden />
          <span className="tabular-nums">
            {range.capped ? (better === 'up' ? '≤ ' : '≥ ') : ''}
            {format(better === 'up' ? range.low : range.high)}
          </span>
        </span>
        {typeof target === 'number' && better ? (
          <span className="flex items-center gap-2">
            <span className="h-1 w-5 rounded-full" style={{ background: INDIGO }} aria-hidden />
            Meets the target of {format(target)}
          </span>
        ) : null}
        <span>
          {weightLabel ? `Deeper orange is ${worstFirst ? 'worse' : 'higher'}; line width is ${weightLabel}.` : `Thicker and deeper orange is ${worstFirst ? 'worse' : 'higher'}.`}
        </span>
      </div>

      {compact ? (
        <div className="grid items-start gap-3 sm:grid-cols-[1fr_auto]">
          {routeList}
          {askButton}
        </div>
      ) : (
        <div className="grid items-stretch gap-4 sm:grid-cols-2">
          {chosen ? (
            <section className="flex flex-col rounded-xl border border-slate-200 bg-white p-4" aria-label="Selected route" data-testid="route-card">
              <div className="viz-caption font-semibold">
                {worstFirst ? 'Worst' : 'Highest'} {rank} of {routes.length} routes
              </div>
              <div className="viz-title mt-1">
                {chosen.origin} <span className="text-cloudera-orange" aria-hidden>→</span>
                <span className="sr-only"> to </span> {chosen.destination}
              </div>
              <div className="mt-3 flex items-baseline gap-2">
                <span className="viz-figure">{format(chosen.value)}</span>
                <span className="viz-caption">{label}</span>
              </div>
              <dl className="viz-text mt-3 space-y-1.5">
                {typeof overall === 'number' && (
                  <div className="flex justify-between gap-2">
                    <dt className="text-slate-500">Overall</dt>
                    <dd className="font-semibold tabular-nums text-slate-800">{format(overall)}</dd>
                  </div>
                )}
                {typeof target === 'number' && (
                  <div className="flex justify-between gap-2">
                    <dt className="text-slate-500">Target</dt>
                    <dd className={`font-semibold tabular-nums ${chosenMiss ? 'text-[#b82a04]' : 'text-slate-800'}`}>
                      {format(target)}
                      {chosenMiss === true ? ', missed' : chosenMiss === false ? ', met' : ''}
                    </dd>
                  </div>
                )}
                {extraColumns.map(column => (
                  <div key={column} className="flex justify-between gap-2">
                    <dt className="text-slate-500">{workspaceColumnLabel(column)}</dt>
                    <dd className="font-semibold tabular-nums text-slate-800">{formatBusinessValue(column, chosen.row[column], undefined, undefined, locale)}</dd>
                  </div>
                ))}
              </dl>
              {thin && (
                <p className="viz-caption mt-3" role="note">
                  Counted on few records compared with the other routes. Read it with care.
                </p>
              )}
              {askButton && <div className="mt-auto pt-4 [&>button]:w-full">{askButton}</div>}
            </section>
          ) : (
            <div />
          )}
          {routeList}
        </div>
      )}
      {!compact && <p className="viz-caption">Click a route or a row for its details. Drag to pan; use the buttons or Ctrl and scroll to zoom. Boundaries: Natural Earth.</p>}
    </div>
  )
}
