/**
 * Routes in a result: rows that go from a place with coordinates (a terminal, a depot, a warehouse, which the semantic model places
 * through `geo_points`) to another place (a province, or a second place with coordinates), with a value per row. Nothing here is
 * specific to one domain: any result broken down by an origin and a destination the map knows becomes a route map.
 */
import { provinceName } from './geo'

export type RouteDetection = {
  originColumn: string
  destinationColumn: string
  valueColumn: string
  /** A second number that counts something (orders, shipments), drawn as the width of a route: a deep colour on a thin line is a
   * bad figure on few records. Null when the result has one number only. */
  weightColumn: string | null
  /** Where each origin is: value -> [latitude, longitude]. */
  origins: Record<string, [number, number]>
  /** Where each destination is when the destination is also a placed column; else destinations are provinces. */
  destinations: Record<string, [number, number]> | null
}

export type Route = {
  key: string
  origin: string
  destination: string
  /** The boundary-file province name, when the destination is a province. */
  province: string | null
  value: number
  weight: number | null
  row: Record<string, unknown>
}

function numeric(value: unknown): number | null {
  if (typeof value === 'number') return Number.isFinite(value) ? value : null
  if (typeof value === 'string' && value.trim() !== '') {
    const parsed = Number(value)
    return Number.isFinite(parsed) ? parsed : null
  }
  return null
}

function placed(column: string, rows: Record<string, unknown>[], geoPoints: Record<string, Record<string, number[]>>) {
  const places = geoPoints[column]
  if (!places) return null
  const out: Record<string, [number, number]> = {}
  for (const row of rows) {
    const name = row[column]
    const at = typeof name === 'string' ? places[name] : undefined
    if (Array.isArray(at) && at.length === 2) out[name as string] = [Number(at[0]), Number(at[1])]
  }
  return Object.keys(out).length ? out : null
}

/** A route map needs two place columns, one numeric column and at least two routes that both ends of can be placed. */
export function detectRoutes(
  columns: string[],
  rows: Record<string, unknown>[],
  geoPoints?: Record<string, Record<string, number[]>> | null,
): RouteDetection | null {
  if (!geoPoints || rows.length < 2) return null
  for (const originColumn of columns) {
    const origins = placed(originColumn, rows, geoPoints)
    if (!origins) continue
    for (const destinationColumn of columns) {
      if (destinationColumn === originColumn) continue
      const destinations = placed(destinationColumn, rows, geoPoints)
      const text = rows.map(row => row[destinationColumn]).filter((v): v is string => typeof v === 'string' && v.trim() !== '')
      if (!text.length) continue
      const provinces = text.filter(value => provinceName(value)).length
      if (!destinations && provinces / text.length < 0.6) continue
      const numericColumns = columns.filter(
        column => column !== originColumn && column !== destinationColumn && rows.some(row => numeric(row[column]) !== null),
      )
      const valueColumn = numericColumns.includes('metric_value') ? 'metric_value' : numericColumns[0]
      if (!valueColumn) continue
      const counts = numericColumns.filter(
        column => column !== valueColumn && rows.every(row => row[column] === null || row[column] === undefined || (Number.isInteger(numeric(row[column])) && (numeric(row[column]) as number) >= 0)),
      )
      const detection: RouteDetection = { originColumn, destinationColumn, valueColumn, weightColumn: counts[0] ?? null, origins, destinations }
      if (routesOf(rows, detection).length >= 2) return detection
    }
  }
  return null
}

/** One route per row whose two ends can be placed and whose value is a number; the first row wins when a pair repeats. */
export function routesOf(rows: Record<string, unknown>[], detection: RouteDetection): Route[] {
  const seen = new Set<string>()
  const out: Route[] = []
  for (const row of rows) {
    const origin = String(row[detection.originColumn] ?? '')
    const destination = String(row[detection.destinationColumn] ?? '')
    const value = numeric(row[detection.valueColumn])
    if (!detection.origins[origin] || value === null) continue
    const province = detection.destinations ? null : provinceName(destination)
    if (detection.destinations ? !detection.destinations[destination] : !province) continue
    const key = `${origin}→${destination}`
    // Two placed columns naming the same place is not a route; a terminal named after the province it serves (Jambi) is.
    if (seen.has(key) || (detection.destinations && origin === destination)) continue
    seen.add(key)
    const weight = detection.weightColumn ? numeric(row[detection.weightColumn]) : null
    out.push({ key, origin, destination, province, value, weight, row })
  }
  return out
}

/**
 * Which end of the scale is the bad one, so the worst route is drawn strongest. A metric whose author declared "lower is better"
 * (a late rate) is worst at the top; "higher is better" (on-time rate) at the bottom; undeclared, the largest value is the strongest.
 */
export function severity(value: number, min: number, max: number, better?: 'up' | 'down' | null): number {
  if (!(max > min)) return 1
  const t = Math.min(1, Math.max(0, (value - min) / (max - min)))
  return better === 'up' ? 1 - t : t
}

/**
 * The values the colour scale runs between. One or two extreme routes would otherwise wash every other route out to the palest
 * colour, so the bad end stops at the 90th percentile (the 10th when higher is better) and anything beyond it gets the full colour.
 */
export function colourRange(values: number[], better?: 'up' | 'down' | null): { low: number; high: number; capped: boolean } {
  const sorted = values.filter(Number.isFinite).sort((a, b) => a - b)
  if (!sorted.length) return { low: 0, high: 0, capped: false }
  const min = sorted[0]
  const max = sorted[sorted.length - 1]
  if (sorted.length < 6) return { low: min, high: max, capped: false }
  const at = (q: number) => sorted[Math.min(sorted.length - 1, Math.max(0, Math.round(q * (sorted.length - 1))))]
  if (better === 'up') {
    const low = at(0.1)
    return { low, high: max, capped: low > min }
  }
  const high = at(0.9)
  return { low: min, high, capped: high < max }
}

/** Whether a value is on the wrong side of the declared target; null when no target or no direction is declared. */
export function missesTarget(value: number, target?: number | null, better?: 'up' | 'down' | null): boolean | null {
  if (typeof target !== 'number' || !better) return null
  return better === 'down' ? value > target : value < target
}

/** A quadratic curve from a to b that bows to one side by a share of its length, so routes from one origin fan out. */
export function curvePath(a: [number, number], b: [number, number], bow = 0.18): { d: string; mid: [number, number] } {
  const [x0, y0] = a
  const [x1, y1] = b
  const dx = x1 - x0
  const dy = y1 - y0
  const length = Math.hypot(dx, dy) || 1
  const cx = (x0 + x1) / 2 - (dy / length) * length * bow
  const cy = (y0 + y1) / 2 + (dx / length) * length * bow
  // The point on the curve at t = 0.5, where the route's label or hit target sits.
  const mid: [number, number] = [0.25 * x0 + 0.5 * cx + 0.25 * x1, 0.25 * y0 + 0.5 * cy + 0.25 * y1]
  return { d: `M${x0.toFixed(1)} ${y0.toFixed(1)}Q${cx.toFixed(1)} ${cy.toFixed(1)} ${x1.toFixed(1)} ${y1.toFixed(1)}`, mid }
}

/** The question that asks the agent why one route stands where it does, in the language of the answer. */
export function routeQuestion(route: Route, metricLabel: string, language: string | null | undefined, high: boolean | null): string {
  const label = metricLabel.replace(/\s*\([^)]*\)\s*$/, '').trim()
  if (language === 'id') {
    // Mid-sentence, a title-case label reads in lower case; an acronym (LO, SPBU, TBBM) keeps its capitals.
    const lower = label
      .split(' ')
      .map(word => (/^[A-Z][a-z]/.test(word) ? word.toLowerCase() : word))
      .join(' ')
    if (high === true) return `Kenapa ${lower} rute ${route.origin} ke ${route.destination} tinggi, dan apa penyebab utamanya?`
    if (high === false) return `Kenapa ${lower} rute ${route.origin} ke ${route.destination} rendah, dan apa penyebab utamanya?`
    return `Apa yang memengaruhi ${lower} pada rute ${route.origin} ke ${route.destination}?`
  }
  if (high === true) return `Why is ${label} high on the ${route.origin} to ${route.destination} route, and what are the main causes?`
  if (high === false) return `Why is ${label} low on the ${route.origin} to ${route.destination} route, and what are the main causes?`
  return `What drives ${label} on the ${route.origin} to ${route.destination} route?`
}

export type LabelRequest = { id: string; x: number; y: number; text: string }
export type PlacedLabel = LabelRequest & { lx: number; ly: number; anchor: 'start' | 'middle' | 'end' }

/**
 * Labels that do not sit on each other: each is tried right, left, above and below its point, in the order given (the most important
 * first), and left out when every spot is taken; the first one is always placed. `unit` is one screen pixel in map units, so the
 * spacing holds at any zoom. `avoid` are points (dots) a label must not cover; `bounds` is the visible area, which a label must not
 * leave (a place at the edge gets its label on the inner side).
 */
export function placeLabels(
  requests: LabelRequest[],
  unit: number,
  avoid: [number, number][] = [],
  bounds?: { x0: number; y0: number; x1: number; y1: number },
): PlacedLabel[] {
  const charWidth = 6.3 * unit
  const height = 12 * unit
  const boxes: { x0: number; y0: number; x1: number; y1: number }[] = avoid.map(([x, y]) => ({ x0: x - 4 * unit, y0: y - 4 * unit, x1: x + 4 * unit, y1: y + 4 * unit }))
  const out: PlacedLabel[] = []
  requests.forEach((request, index) => {
    const width = request.text.length * charWidth
    const spots: [number, number, PlacedLabel['anchor']][] = [
      [8, -6, 'start'],
      [8, 14, 'start'],
      [-8, -6, 'end'],
      [-8, 14, 'end'],
      [0, -12, 'middle'],
      [0, 22, 'middle'],
    ]
    for (const [dx, dy, anchor] of spots) {
      const lx = request.x + dx * unit
      const ly = request.y + dy * unit
      const x0 = anchor === 'start' ? lx : anchor === 'end' ? lx - width : lx - width / 2
      const box = { x0: x0 - 2 * unit, y0: ly - height, x1: x0 + width + 2 * unit, y1: ly + 3 * unit }
      const outside = bounds ? box.x0 < bounds.x0 || box.x1 > bounds.x1 || box.y0 < bounds.y0 || box.y1 > bounds.y1 : false
      const clash = outside || boxes.some(other => box.x0 < other.x1 && box.x1 > other.x0 && box.y0 < other.y1 && box.y1 > other.y0)
      if (!clash) {
        boxes.push(box)
        out.push({ ...request, lx, ly, anchor })
        return
      }
    }
    if (index === 0) {
      // The most important label (the selected route's end) is shown even when crowded, on the side with room.
      const room = bounds ? request.x + 8 * unit + width < bounds.x1 : true
      out.push({ ...request, lx: request.x + (room ? 8 : -8) * unit, ly: request.y - 6 * unit, anchor: room ? 'start' : 'end' })
    }
  })
  return out
}
