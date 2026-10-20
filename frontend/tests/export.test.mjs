import assert from 'node:assert/strict'
import test from 'node:test'
import { fetchExport } from '../src/export.ts'

const { Response } = globalThis

test('export preserves a ZIP response', async () => {
  const bytes = new Uint8Array([80, 75, 3, 4, 1, 2, 3])
  let requested
  const blob = await fetchExport('case-id', async url => {
    requested = url
    return new Response(bytes, { headers: { 'Content-Type': 'application/zip' } })
  })
  assert.equal(requested, '/api/cases/case-id/export')
  assert.deepEqual(new Uint8Array(await blob.arrayBuffer()), bytes)
})

test('integrity rejection surfaces the backend explanation instead of a fake ZIP', async () => {
  await assert.rejects(fetchExport('case-id', async () => new Response(JSON.stringify({
    detail: 'Оригинал изображения изменен: SHA-256 не совпадает.'
  }), { status: 409, headers: { 'Content-Type': 'application/json' } })), /SHA-256/)
})

test('unexpected successful HTML cannot be downloaded as a dossier', async () => {
  await assert.rejects(fetchExport('case-id', async () => new Response('<html>Error</html>', {
    headers: { 'Content-Type': 'text/html' }
  })), /вместо ZIP/)
})

test('network and malformed error responses produce useful messages', async () => {
  await assert.rejects(fetchExport('case-id', async () => { throw new TypeError('Failed to fetch') }), /локальным сервером/)
  await assert.rejects(fetchExport('case-id', async () => new Response('Bad gateway', { status: 502 })), /подготовить досье/)
})
