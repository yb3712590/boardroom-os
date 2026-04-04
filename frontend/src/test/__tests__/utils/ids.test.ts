import { describe, expect, it } from 'vitest'

import { newPrefixedId } from '../../../utils/ids'

describe('utils/ids', () => {
  it('creates a prefixed identifier with a hexadecimal suffix', () => {
    expect(newPrefixedId('board-approve')).toMatch(/^board-approve_[0-9a-f]{12}$/)
  })

  it('returns a different identifier on subsequent calls', () => {
    const first = newPrefixedId('emp')
    const second = newPrefixedId('emp')

    expect(first).not.toBe(second)
  })
})
