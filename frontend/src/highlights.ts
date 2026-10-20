export type SourceClaim = { quote: string; start: number; end: number }

export function sourceIntervals(text: string, claims: SourceClaim[]) {
  // API offsets count Unicode code points; JavaScript slice counts UTF-16 units.
  const points = Array.from(text)
  const offsets = [0]
  for (const point of points) offsets.push(offsets.at(-1)! + point.length)
  const ranges = claims.filter(c => c.start >= 0 && c.end <= points.length && c.end > c.start && points.slice(c.start, c.end).join('') === c.quote)
    .map(c => ({ start: offsets[c.start], end: offsets[c.end] }))
    .sort((a, b) => a.start - b.start || b.end - a.end)
  const merged: { start: number; end: number }[] = []
  for (const range of ranges) {
    const previous = merged.at(-1)
    if (previous && range.start <= previous.end) previous.end = Math.max(previous.end, range.end)
    else merged.push({ ...range })
  }
  return merged
}
