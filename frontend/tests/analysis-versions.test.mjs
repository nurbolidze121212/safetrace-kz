import test from 'node:test'
import assert from 'node:assert/strict'
import { compareAnalysisVersions } from '../src/analysisVersions.ts'

const current = { rules: 'rules-3.0', pipeline: 'pipeline-2.1', ocr: 'ocr-layout-2.0', qr: 'qr-1.0' }

test('a stored result names the components that differ from the running server', () => {
  const saved = { ...current, rules: 'rules-1.0', ocr: 'ocr-layout-1.0' }
  const before = { ...saved }
  const result = compareAnalysisVersions(saved, current)
  assert.equal(result.state, 'different')
  assert.deepEqual(result.differences.map(row => row.key), ['rules', 'ocr'])
  assert.deepEqual(saved, before)
})

test('missing legacy metadata or unavailable server metadata cannot claim matching versions', () => {
  assert.equal(compareAnalysisVersions({ rules: current.rules }, current).state, 'unknown')
  assert.equal(compareAnalysisVersions(current, undefined).state, 'unknown')
  assert.equal(compareAnalysisVersions({ ...current, qr: '' }, current).state, 'unknown')
  assert.equal(compareAnalysisVersions({ ...current, qr: 1 }, current).state, 'unknown')
  assert.equal(compareAnalysisVersions(current, { ...current }).state, 'match')
})

test('a known difference remains visible even when other historical versions are missing', () => {
  const result = compareAnalysisVersions({ rules: 'rules-2.0' }, current)
  assert.equal(result.state, 'different')
  assert.equal(result.rows.find(row => row.key === 'pipeline').saved, undefined)
})
