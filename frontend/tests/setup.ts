import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterEach, beforeEach, expect, vi } from 'vitest'

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}

class IntersectionObserverStub {
  root = null
  rootMargin = '0px'
  thresholds = [0]
  observe() {}
  unobserve() {}
  disconnect() {}
  takeRecords() { return [] }
}

vi.stubGlobal('ResizeObserver', ResizeObserverStub)
vi.stubGlobal('IntersectionObserver', IntersectionObserverStub)
Object.defineProperty(window, 'matchMedia', { configurable: true, value: vi.fn().mockImplementation((query: string) => ({ matches: false, media: query, onchange: null, addListener: vi.fn(), removeListener: vi.fn(), addEventListener: vi.fn(), removeEventListener: vi.fn(), dispatchEvent: vi.fn() })) })
Object.defineProperty(Document.prototype, 'getAnimations', { configurable: true, value: () => [] })
Object.defineProperty(Element.prototype, 'getAnimations', { configurable: true, value: () => [] })

export const networkSpies = {
  fetch: vi.fn(),
  xhrOpen: vi.fn(),
  sendBeacon: vi.fn(),
  webSocket: vi.fn(),
}

beforeEach(() => {
  vi.stubGlobal('ResizeObserver', ResizeObserverStub)
  vi.stubGlobal('IntersectionObserver', IntersectionObserverStub)
  networkSpies.fetch.mockReset()
  networkSpies.xhrOpen.mockReset()
  networkSpies.sendBeacon.mockReset()
  networkSpies.webSocket.mockReset()
  vi.stubGlobal('fetch', networkSpies.fetch)
  vi.spyOn(XMLHttpRequest.prototype, 'open').mockImplementation(networkSpies.xhrOpen)
  Object.defineProperty(navigator, 'sendBeacon', { configurable: true, value: networkSpies.sendBeacon })
  vi.stubGlobal('WebSocket', networkSpies.webSocket)
  vi.spyOn(window, 'confirm').mockReturnValue(true)
})

afterEach(() => {
  expect(networkSpies.fetch, 'No debe invocarse fetch').not.toHaveBeenCalled()
  expect(networkSpies.xhrOpen, 'No debe abrirse XMLHttpRequest').not.toHaveBeenCalled()
  expect(networkSpies.sendBeacon, 'No debe invocarse sendBeacon').not.toHaveBeenCalled()
  expect(networkSpies.webSocket, 'No debe construirse WebSocket').not.toHaveBeenCalled()
  cleanup()
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})
