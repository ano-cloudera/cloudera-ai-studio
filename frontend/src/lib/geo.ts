/** Geographic helpers for the Map tab: recognise province columns in a result, project boundaries, and colour values. */

export type GeoFeature = {
  type: 'Feature'
  properties: { name: string }
  geometry: { type: 'MultiPolygon'; coordinates: number[][][][] }
}
export type GeoCollection = { type: 'FeatureCollection'; features: GeoFeature[]; attribution?: string }

export type GeoDetection = {
  /** Result column whose values are province names. */
  geoColumn: string
  /** Numeric column drawn on the map. */
  valueColumn: string
  /** Rows whose name matched a province. */
  matched: number
  /** Distinct names that matched nothing (shown as a note, never guessed). */
  unmatched: string[]
}

/** The 33 provinces of the bundled boundary file (Natural Earth names). */
export const INDONESIA_PROVINCES = [
  'Aceh', 'Bali', 'Bangka-Belitung', 'Banten', 'Bengkulu', 'Gorontalo', 'Jakarta Raya', 'Jambi', 'Jawa Barat',
  'Jawa Tengah', 'Jawa Timur', 'Kalimantan Barat', 'Kalimantan Selatan', 'Kalimantan Tengah', 'Kalimantan Timur',
  'Kepulauan Riau', 'Lampung', 'Maluku', 'Maluku Utara', 'Nusa Tenggara Barat', 'Nusa Tenggara Timur', 'Papua',
  'Papua Barat', 'Riau', 'Sulawesi Barat', 'Sulawesi Selatan', 'Sulawesi Tengah', 'Sulawesi Tenggara',
  'Sulawesi Utara', 'Sumatera Barat', 'Sumatera Selatan', 'Sumatera Utara', 'Yogyakarta',
] as const

/** Other common spellings, keyed by their normalised form. */
const ALIASES: Record<string, string> = {
  'dki jakarta': 'Jakarta Raya',
  jakarta: 'Jakarta Raya',
  'di yogyakarta': 'Yogyakarta',
  'daerah istimewa yogyakarta': 'Yogyakarta',
  diy: 'Yogyakarta',
  'bangka belitung': 'Bangka-Belitung',
  'kepulauan bangka belitung': 'Bangka-Belitung',
  'kep riau': 'Kepulauan Riau',
  'nanggroe aceh darussalam': 'Aceh',
  ntb: 'Nusa Tenggara Barat',
  ntt: 'Nusa Tenggara Timur',
  'jabar': 'Jawa Barat',
  'jateng': 'Jawa Tengah',
  'jatim': 'Jawa Timur',
}

function normalise(name: string): string {
  return name
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .toLowerCase()
    .replace(/^provinsi\s+/, '')
    .replace(/[-_.]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
}

const BY_NORMALISED = new Map<string, string>([
  ...INDONESIA_PROVINCES.map(name => [normalise(name), name] as [string, string]),
  ...Object.entries(ALIASES),
])

/** The boundary-file name for a province written in any common way, or null. */
export function provinceName(value: unknown): string | null {
  if (typeof value !== 'string') return null
  return BY_NORMALISED.get(normalise(value)) ?? null
}

function numericValue(value: unknown): number | null {
  if (typeof value === 'number') return Number.isFinite(value) ? value : null
  if (typeof value === 'string' && value.trim() !== '') {
    const parsed = Number(value)
    return Number.isFinite(parsed) ? parsed : null
  }
  return null
}

/** A province column plus a numeric column, when the result has them. */
export function detectGeo(columns: string[], rows: Record<string, unknown>[]): GeoDetection | null {
  if (rows.length === 0) return null
  let best: { column: string; matched: number; unmatched: string[] } | null = null
  for (const column of columns) {
    const distinct = new Set<string>()
    let matched = 0
    for (const row of rows) {
      const value = row[column]
      if (typeof value !== 'string' || !value.trim()) continue
      distinct.add(value)
      if (provinceName(value)) matched += 1
    }
    if (distinct.size === 0) continue
    const matchedNames = [...distinct].filter(name => provinceName(name))
    if (matchedNames.length < 2 || matchedNames.length / distinct.size < 0.6) continue
    const unmatched = [...distinct].filter(name => !provinceName(name))
    if (!best || matched > best.matched) best = { column, matched, unmatched }
  }
  if (!best) return null
  const numeric = columns.filter(column => column !== best!.column && rows.some(row => numericValue(row[column]) !== null))
  const valueColumn = numeric.includes('metric_value') ? 'metric_value' : numeric[0]
  if (!valueColumn) return null
  return { geoColumn: best.column, valueColumn, matched: best.matched, unmatched: best.unmatched }
}

/** value per province name (rows of the same province are summed only if the model returned duplicates). */
export function valuesByProvince(rows: Record<string, unknown>[], detection: GeoDetection): Map<string, number> {
  const out = new Map<string, number>()
  for (const row of rows) {
    const name = provinceName(row[detection.geoColumn])
    const value = numericValue(row[detection.valueColumn])
    if (name && value !== null) out.set(name, (out.get(name) ?? 0) + value)
  }
  return out
}

export const MAP_WIDTH = 1000

export type Projection = { project: (lon: number, lat: number) => [number, number]; width: number; height: number }

/** Equirectangular projection fitted to the boundary file (Indonesia sits on the equator, so the distortion is small). */
export function fitProjection(collection: GeoCollection, width = MAP_WIDTH, padding = 12): Projection {
  let minLon = Infinity
  let maxLon = -Infinity
  let minLat = Infinity
  let maxLat = -Infinity
  for (const feature of collection.features) {
    for (const polygon of feature.geometry.coordinates) {
      for (const [lon, lat] of polygon[0]) {
        minLon = Math.min(minLon, lon)
        maxLon = Math.max(maxLon, lon)
        minLat = Math.min(minLat, lat)
        maxLat = Math.max(maxLat, lat)
      }
    }
  }
  const scale = (width - 2 * padding) / (maxLon - minLon)
  const height = Math.ceil((maxLat - minLat) * scale + 2 * padding)
  return {
    width,
    height,
    project: (lon, lat) => [padding + (lon - minLon) * scale, padding + (maxLat - lat) * scale],
  }
}

export function featurePath(feature: GeoFeature, projection: Projection): string {
  return feature.geometry.coordinates
    .map(polygon =>
      polygon
        .map(ring => 'M' + ring.map(([lon, lat]) => projection.project(lon, lat).map(n => n.toFixed(1)).join(' ')).join('L') + 'Z')
        .join(''),
    )
    .join('')
}

/** Centre of the largest ring of a feature (area weighted), in projected coordinates. */
export function featureCentroid(feature: GeoFeature, projection: Projection): [number, number] {
  let best: { area: number; x: number; y: number } | null = null
  for (const polygon of feature.geometry.coordinates) {
    const ring = polygon[0].map(([lon, lat]) => projection.project(lon, lat))
    let area = 0
    let cx = 0
    let cy = 0
    for (let i = 0; i < ring.length - 1; i += 1) {
      const [x0, y0] = ring[i]
      const [x1, y1] = ring[i + 1]
      const cross = x0 * y1 - x1 * y0
      area += cross
      cx += (x0 + x1) * cross
      cy += (y0 + y1) * cross
    }
    area /= 2
    if (area === 0) continue
    const candidate = { area: Math.abs(area), x: cx / (6 * area), y: cy / (6 * area) }
    if (!best || candidate.area > best.area) best = candidate
  }
  return best ? [best.x, best.y] : [0, 0]
}

const LOW = [255, 237, 224] // pale orange
const HIGH = [194, 52, 8] // deep orange

/** Colour for a value between min and max (a pale-to-deep orange ramp, matching the product accent). */
export function rampColor(value: number, min: number, max: number): string {
  const t = max > min ? Math.min(1, Math.max(0, (value - min) / (max - min))) : 1
  const mix = LOW.map((low, i) => Math.round(low + (HIGH[i] - low) * t))
  return `rgb(${mix[0]}, ${mix[1]}, ${mix[2]})`
}

/** Bubble radius that scales with the area of the value, between 5 and 26 units. */
export function bubbleRadius(value: number, max: number): number {
  if (max <= 0 || value <= 0) return 5
  return 5 + 21 * Math.sqrt(value / max)
}
