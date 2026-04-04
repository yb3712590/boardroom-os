function fallbackHex(length: number): string {
  const seed = `${Date.now().toString(16)}${Math.random().toString(16).slice(2)}`
  return seed.slice(0, length).padEnd(length, '0')
}

export function newPrefixedId(prefix: string): string {
  const byteLength = 6
  const hexLength = byteLength * 2
  const bytes = new Uint8Array(byteLength)

  if (typeof globalThis.crypto?.getRandomValues === 'function') {
    globalThis.crypto.getRandomValues(bytes)
    const suffix = Array.from(bytes, (value) => value.toString(16).padStart(2, '0')).join('')
    return `${prefix}_${suffix}`
  }

  return `${prefix}_${fallbackHex(hexLength)}`
}
