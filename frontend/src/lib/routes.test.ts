import { describe, expect, it } from 'vitest'

import { colourRange, curvePath, detectRoutes, missesTarget, placeLabels, routeQuestion, routesOf, severity } from './routes'

const geo = { fuel_terminal: { Wayame: [-3.63, 128.17], Jambi: [-1.61, 103.61], Plumpang: [-6.13, 106.89] } }
const rows = [
  { fuel_terminal: 'Wayame', provinsi: 'Maluku', rate: 37.1, lo: 3107 },
  { fuel_terminal: 'Jambi', provinsi: 'Jambi', rate: 14.2, lo: 2000 },
  { fuel_terminal: 'Plumpang', provinsi: 'DKI Jakarta', rate: 12.0, lo: 9000 },
]

describe('detectRoutes', () => {
  it('finds a placed origin, a province destination, the value and a count for the width', () => {
    const found = detectRoutes(['fuel_terminal', 'provinsi', 'rate', 'lo'], rows, geo)
    expect(found).toMatchObject({ originColumn: 'fuel_terminal', destinationColumn: 'provinsi', valueColumn: 'rate', weightColumn: 'lo', destinations: null })
  })

  it('keeps a terminal named after the province it serves, and spells provinces the way the map does', () => {
    const found = detectRoutes(['fuel_terminal', 'provinsi', 'rate'], rows, geo)!
    const routes = routesOf(rows, found)
    expect(routes.map(route => route.key)).toEqual(['Wayame→Maluku', 'Jambi→Jambi', 'Plumpang→DKI Jakarta'])
    expect(routes[2].province).toBe('Jakarta Raya')
    expect(found.weightColumn).toBeNull()
  })

  it('needs coordinates for the origin and at least two routes', () => {
    expect(detectRoutes(['fuel_terminal', 'provinsi', 'rate'], rows, {})).toBeNull()
    expect(detectRoutes(['fuel_terminal', 'provinsi', 'rate'], rows.slice(0, 1), geo)).toBeNull()
    expect(detectRoutes(['fuel_terminal', 'rate'], rows, geo)).toBeNull()
  })

  it('does not take a rate with decimals as the count', () => {
    const found = detectRoutes(['fuel_terminal', 'provinsi', 'lo', 'rate'], rows, geo)!
    expect(found.valueColumn).toBe('lo')
    expect(found.weightColumn).toBeNull()
  })
})

describe('scales', () => {
  it('stops the bad end at the 90th percentile so one outlier does not wash the rest out', () => {
    const values = [10, 11, 12, 13, 14, 15, 16, 17, 30, 94]
    expect(colourRange(values, 'down')).toEqual({ low: 10, high: 30, capped: true })
    expect(colourRange(values, 'up')).toEqual({ low: 11, high: 94, capped: true })
    expect(colourRange([1, 2, 3], 'down')).toEqual({ low: 1, high: 3, capped: false })
  })

  it('puts the bad end of a declared direction at full strength', () => {
    expect(severity(30, 10, 30, 'down')).toBe(1)
    expect(severity(30, 10, 30, 'up')).toBe(0)
    expect(severity(94, 10, 30, 'down')).toBe(1)
  })

  it('says whether a value misses its target only when a target and a direction are declared', () => {
    expect(missesTarget(16, 15, 'down')).toBe(true)
    expect(missesTarget(14, 15, 'down')).toBe(false)
    expect(missesTarget(14, 15, 'up')).toBe(true)
    expect(missesTarget(14, 15, null)).toBeNull()
    expect(missesTarget(14, null, 'down')).toBeNull()
  })

  it('bows a route to one side and gives the middle of the curve', () => {
    const { d, mid } = curvePath([0, 0], [100, 0], 0.2)
    expect(d).toBe('M0.0 0.0Q50.0 20.0 100.0 0.0')
    expect(mid).toEqual([50, 10])
  })
})

describe('routeQuestion', () => {
  const route = routesOf(rows, detectRoutes(['fuel_terminal', 'provinsi', 'rate'], rows, geo)!)[0]
  it('asks in the language of the answer, without the unit', () => {
    expect(routeQuestion(route, 'Tingkat Keterlambatan (%)', 'id', true)).toBe('Kenapa tingkat keterlambatan rute Wayame ke Maluku tinggi, dan apa penyebab utamanya?')
    expect(routeQuestion(route, 'Late Rate (%)', 'en', null)).toBe('What drives Late Rate on the Wayame to Maluku route?')
  })
})

describe('placeLabels', () => {
  it('moves a label that would cover another to a free side, and keeps labels inside the visible area', () => {
    const placed = placeLabels(
      [
        { id: 'a', x: 100, y: 100, text: 'Panjang' },
        { id: 'b', x: 104, y: 100, text: 'Bangka' },
        { id: 'c', x: 995, y: 50, text: 'Jayapura' },
      ],
      1,
      [],
      { x0: 0, y0: 0, x1: 1000, y1: 600 },
    )
    const [a, b, c] = placed
    expect(a.anchor).toBe('start')
    expect([b.lx, b.ly]).not.toEqual([a.lx + 4, a.ly])
    expect(c.anchor).toBe('end') // no room on the right edge
  })

  it('leaves a label out when every side is taken, except the first one', () => {
    const crowd = Array.from({ length: 12 }, (_, i) => ({ id: String(i), x: 50, y: 50, text: 'Terminal' }))
    const placed = placeLabels(crowd, 1)
    expect(placed.length).toBeLessThan(crowd.length)
    expect(placed[0].id).toBe('0')
  })
})
