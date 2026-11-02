import { describe, expect, it } from 'vitest'
import {
  bubbleRadius,
  detectGeo,
  featureCentroid,
  featurePath,
  fitProjection,
  provinceName,
  rampColor,
  valuesByProvince,
  type GeoCollection,
} from './geo'

const square = (name: string, lon: number, lat: number): GeoCollection['features'][number] => ({
  type: 'Feature',
  properties: { name },
  geometry: {
    type: 'MultiPolygon',
    coordinates: [[[[lon, lat], [lon + 2, lat], [lon + 2, lat - 2], [lon, lat - 2], [lon, lat]]]],
  },
})

describe('provinceName', () => {
  it('matches common spellings to the boundary names', () => {
    expect(provinceName('Jawa Timur')).toBe('Jawa Timur')
    expect(provinceName('  jawa  timur ')).toBe('Jawa Timur')
    expect(provinceName('DKI Jakarta')).toBe('Jakarta Raya')
    expect(provinceName('Provinsi Bali')).toBe('Bali')
    expect(provinceName('DI Yogyakarta')).toBe('Yogyakarta')
    expect(provinceName('Bangka Belitung')).toBe('Bangka-Belitung')
    expect(provinceName('Mars')).toBeNull()
    expect(provinceName(12)).toBeNull()
  })
})

describe('detectGeo', () => {
  const rows = [
    { region_name: 'Jawa Timur', metric_value: 16.3, orders: 5 },
    { region_name: 'Kalimantan Timur', metric_value: 23.1, orders: 7 },
    { region_name: 'DKI Jakarta', metric_value: 8.6, orders: 9 },
  ]

  it('finds the province column and prefers metric_value', () => {
    expect(detectGeo(['region_name', 'orders', 'metric_value'], rows)).toMatchObject({
      geoColumn: 'region_name',
      valueColumn: 'metric_value',
      unmatched: [],
    })
  })

  it('lists the names it could not place and ignores results without provinces', () => {
    const mixed = [...rows, { region_name: 'Atlantis', metric_value: 1, orders: 1 }]
    expect(detectGeo(['region_name', 'metric_value'], mixed)?.unmatched).toEqual(['Atlantis'])
    expect(detectGeo(['carrier', 'metric_value'], [{ carrier: 'NusaCargo', metric_value: 1 }, { carrier: 'KilatKirim', metric_value: 2 }])).toBeNull()
    expect(detectGeo(['region_name'], rows.map(r => ({ region_name: r.region_name })))).toBeNull()
    expect(detectGeo(['region_name', 'metric_value'], [])).toBeNull()
  })

  it('sums duplicates per province', () => {
    const detection = detectGeo(['region_name', 'metric_value'], rows)!
    const values = valuesByProvince([...rows, { region_name: 'Jawa Timur', metric_value: 1 }], detection)
    expect(values.get('Jawa Timur')).toBeCloseTo(17.3)
    expect(values.get('Jakarta Raya')).toBe(8.6)
  })
})

describe('projection', () => {
  const collection: GeoCollection = { type: 'FeatureCollection', features: [square('A', 100, 0), square('B', 110, -4)] }

  it('fits the boundaries inside the canvas', () => {
    const projection = fitProjection(collection, 1000, 10)
    const [left, top] = projection.project(100, 0)
    const [right, bottom] = projection.project(112, -6)
    expect(left).toBeCloseTo(10)
    expect(top).toBeCloseTo(10)
    expect(right).toBeCloseTo(990)
    expect(bottom).toBeLessThanOrEqual(projection.height - 10 + 1)
  })

  it('draws a closed path and finds the centre of a square', () => {
    const projection = fitProjection(collection, 1000, 10)
    expect(featurePath(collection.features[0], projection).startsWith('M')).toBe(true)
    expect(featurePath(collection.features[0], projection).endsWith('Z')).toBe(true)
    const [cx, cy] = featureCentroid(collection.features[0], projection)
    const [x0, y0] = projection.project(101, -1)
    expect(cx).toBeCloseTo(x0, 0)
    expect(cy).toBeCloseTo(y0, 0)
  })
})

describe('colour and size scales', () => {
  it('goes from pale to deep and grows with the value', () => {
    expect(rampColor(0, 0, 10)).toBe('rgb(255, 237, 224)')
    expect(rampColor(10, 0, 10)).toBe('rgb(194, 52, 8)')
    expect(rampColor(5, 5, 5)).toBe('rgb(194, 52, 8)')
    expect(bubbleRadius(0, 10)).toBe(5)
    expect(bubbleRadius(10, 10)).toBeCloseTo(26)
    expect(bubbleRadius(2.5, 10)).toBeLessThan(bubbleRadius(10, 10))
  })
})
