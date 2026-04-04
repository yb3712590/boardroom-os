import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  formatNumber,
  formatRelativeTime,
  formatTimestamp,
  normalizeConstraints,
} from '../../../utils/format'

describe('utils/format', () => {
  afterEach(() => {
    vi.useRealTimers()
  })

  it('formats numbers with en-US grouping', () => {
    expect(formatNumber(481800)).toBe('481,800')
  })

  it('formats timestamps and respects the provided empty label', () => {
    expect(formatTimestamp(null, 'Not recorded')).toBe('Not recorded')
    expect(formatTimestamp('2026-04-01T23:12:00+08:00')).toBe('Apr 1, 11:12 PM')
  })

  it('formats relative time across short and fallback ranges', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-04-02T00:12:30+08:00'))

    expect(formatRelativeTime('2026-04-02T00:12:00+08:00')).toBe('30s ago')
    expect(formatRelativeTime('2026-04-01T22:12:30+08:00')).toBe('2h ago')
    expect(formatRelativeTime('2026-03-31T23:12:00+08:00')).toBe('Mar 31, 11:12 PM')
  })

  it('normalizes multiline constraint input', () => {
    expect(normalizeConstraints('Keep auditability.\n\n  Avoid browser truth drift. \n')).toEqual([
      'Keep auditability.',
      'Avoid browser truth drift.',
    ])
  })
})
