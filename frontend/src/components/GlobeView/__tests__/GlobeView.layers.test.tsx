import { describe, it, expect, vi } from 'vitest'
import { render, renderHook } from '@testing-library/react'

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
vi.mock('@deck.gl/geo-layers', () => ({ TripsLayer: vi.fn(), Tile3DLayer: vi.fn() }))
vi.mock('@deck.gl/layers', () => ({ PathLayer: vi.fn(), ScatterplotLayer: vi.fn() }))
vi.mock('@tanstack/react-query', () => ({ useQuery: vi.fn(() => ({ data: undefined })) }))
vi.mock('../../../api/client', () => ({
  chokepointsApi: { list: vi.fn() },
  darkShipsApi: { list: vi.fn() },
}))

import { GlobeView } from '../GlobeView'
import { useScenePerformance } from '../../../hooks/useScenePerformance'

describe('GlobeView layer props', () => {
  it('renders without crashing with all new Phase 2 props', () => {
    expect(() =>
      render(
        <GlobeView
          aois={[]}
          events={[]}
          showOrbitsLayer={false}
          orbitPasses={[]}
          showAirspaceLayer={false}
          airspaceRestrictions={[]}
          showJammingLayer={false}
          jammingEvents={[]}
          showStrikesLayer={false}
          strikeEvents={[]}
          showTerrainLayer={false}
          show3dBuildingsLayer={false}
          showPerfOverlay={false}
        />
      )
    ).not.toThrow()
  })

  it('renders with showPerfOverlay enabled', () => {
    expect(() =>
      render(<GlobeView aois={[]} events={[]} showPerfOverlay={true} />)
    ).not.toThrow()
  })

  it('GlobeView exports are stable', () => {
    expect(typeof GlobeView).toBe('function')
  })
})

describe('useScenePerformance', () => {
  it('returns a valid report with low entity count', () => {
    const { result } = renderHook(() => useScenePerformance(0))
    expect(result.current.fps).toBeGreaterThan(0)
    expect(result.current.isDenseView).toBe(false)
    expect(result.current.shouldReduceDetail).toBe(false)
  })

  it('returns isDenseView true when entity count exceeds threshold', () => {
    const { result } = renderHook(() => useScenePerformance(600))
    expect(result.current.isDenseView).toBe(true)
    expect(result.current.shouldReduceDetail).toBe(true)
  })
})
