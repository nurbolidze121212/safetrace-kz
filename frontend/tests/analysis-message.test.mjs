import test from 'node:test'
import assert from 'node:assert/strict'
import { analysisMessage } from '../src/analysis-message.ts'

const result = { status: 'completed', stage: 'priority', score: { level: 'low', value: 0 }, sufficient_data: true, materials: [], trace: { observations: [] } }

test('a zero score with missing data never reads as a completed negative check', () => {
  const incomplete = analysisMessage({ ...result, sufficient_data: false, status: 'partial', trace: { observations: [{ stop: 'offline' }] } })
  assert.equal(incomplete.tone, 'attention')
  assert.equal(incomplete.action, 'route')
  assert.match(incomplete.title, /дополнительные данные/)
  assert.match(incomplete.detail, /не подтверждает безопасность/)
})

test('uncertain OCR is surfaced even if an old result reports complete and sufficient', () => {
  const message = analysisMessage({ ...result, materials: [{ url_reviews: [{ needs_review: true }] }] })
  assert.equal(message.action, 'materials')
  assert.match(message.detail, /распознан неоднозначно/)
  assert.equal(message.tone, 'attention')
})

test('a partial high priority preserves both the observed signal and the missing evidence', () => {
  const message = analysisMessage({ ...result, status: 'partial', score: { level: 'high', value: 80 } })
  assert.match(message.title, /Есть признаки/)
  assert.match(message.title, /неполная/)
})

test('an explicitly corrected OCR address no longer asks for the same correction', () => {
  const message = analysisMessage({ ...result, score: { level: 'high', value: 80 }, materials: [{ url_reviews: [{ needs_review: true, selected_url: 'https://example.test/item', correction_id: 'checked' }] }] })
  assert.match(message.title, /^Обнаружены признаки/)
  assert.doesNotMatch(message.detail, /распознан неоднозначно/)
})

test('rerunning and cancelled analyses cannot present an old score as the new result', () => {
  for (const status of ['pending', 'running', 'cancelled', 'error']) {
    const message = analysisMessage({ ...result, status, stage: 'ocr', score: { level: 'high', value: 80 } })
    assert.doesNotMatch(message.title, /Обнаружены признаки/)
    if (status === 'running') assert.match(message.detail, /между этапами/)
    if (status === 'cancelled' || status === 'error') assert.equal(message.action, 'retry')
  }
})

test('a completed low priority states the gambling scope, not general link safety', () => {
  const message = analysisMessage(result)
  assert.equal(message.action, 'review')
  assert.match(message.detail, /фишинг.*не оцениваются/)
  assert.match(message.detail, /не подтверждение безопасности/)
})

test('missing score is an incomplete result, including legacy records', () => {
  assert.equal(analysisMessage({ ...result, score: null }).tone, 'attention')
})
