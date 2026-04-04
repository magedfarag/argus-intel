import { describe, it, expect, vi } from 'vitest'
import { render } from '@testing-library/react'

// MapLibre GL requires WebGL — stub the map instance
vi.mock('maplibre-gl', () => ({
  default: {
    Map: vi.fn(() => ({
      on: vi.fn(),
      once: vi.fn(),
      off: vi.fn(),
      addControl: vi.fn(),
      remove: vi.fn(),
      flyTo: vi.fn(),
      getCanvas: vi.fn(() => ({ style: {} })),
    })),
    NavigationControl: vi.fn(),
    ScaleControl: vi.fn(),
    Popup: vi.fn(() => ({
      setLngLat: vi.fn().mockReturnThis(),
      setHTML: vi.fn().mockReturnThis(),
      addTo: vi.fn(),
    })),
  },
}))
vi.mock('maplibre-gl/dist/maplibre-gl.css', () => ({}))
vi.mock('@deck.gl/mapbox', () => ({ MapboxOverlay: vi.fn(() => ({ setProps: vi.fn() })) }))
vi.mock('@deck.gl/geo-layers', () => ({ TripsLayer: vi.fn() }))
vi.mock('@tanstack/react-query', () => ({ useQuery: vi.fn(() => ({ data: undefined })) }))
vi.mock('../../../api/client', () => ({
  chokepointsApi: { list: vi.fn() },
  darkShipsApi: { list: vi.fn() },
}))

import { GlobeView } from '../GlobeView'

describe('GlobeView smoke', () => {
  it('exports a React component function', () => {
    expect(GlobeView).toBeTypeOf('function')
  })

  it('renders without throwing', () => {
    expect(() => render(<GlobeView aois={[]} events={[]} />)).not.toThrow()
  })
})
