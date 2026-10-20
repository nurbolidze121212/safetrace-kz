import { test } from 'node:test'
import assert from 'node:assert/strict'
import { sourceIntervals } from '../src/highlights.ts'

test('only the verified occurrence is highlighted, including text after emoji', () => {
  const text = '🔍 Не переходи. Но переходи.'
  const claim = { quote: 'переходи', start: 18, end: 26 }
  const result = sourceIntervals(text, [claim])
  assert.deepEqual(result, [{ start: text.lastIndexOf('переходи'), end: text.lastIndexOf('переходи') + 8 }])
  assert.equal(text.slice(result[0].start, result[0].end), 'переходи')
})
test('invalid source offsets are ignored and overlapping valid claims are merged', () => {
  assert.deepEqual(sourceIntervals('казино бонус', [
    { quote: 'казино', start: 0, end: 6 },
    { quote: 'казино бонус', start: 0, end: 12 },
    { quote: 'бонус', start: 0, end: 5 },
  ]), [{ start: 0, end: 12 }])
})
