import '@testing-library/jest-dom/vitest'
import { vi } from 'vitest'
import { cleanup } from '@testing-library/react'
import { afterEach } from 'vitest'

afterEach(cleanup)

Object.defineProperty(window.HTMLElement.prototype, 'scrollIntoView', { configurable: true, value: vi.fn() })
let sequence = 0
Object.defineProperty(globalThis, 'crypto', { configurable: true, value: { randomUUID: () => `00000000-0000-4000-8000-${String(++sequence).padStart(12, '0')}` } })
