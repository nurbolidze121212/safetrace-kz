import { createHash } from 'node:crypto'
import { log } from 'node:console'
import { readdir, readFile, writeFile } from 'node:fs/promises'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
async function filesIn(directory) {
  let entries
  try { entries = await readdir(path.join(root, directory), { withFileTypes: true }) }
  catch (error) { if (error.code === 'ENOENT') return []; throw error }
  const files = []
  for (const entry of entries) {
    const name = path.posix.join(directory, entry.name)
    if (entry.isDirectory()) files.push(...await filesIn(name))
    else if (entry.isFile()) files.push(name)
  }
  return files.sort()
}
async function hashes(names, prefix = '') {
  const result = {}
  for (const name of names.sort()) result[name.slice(prefix.length)] = createHash('sha256').update(await readFile(path.join(root, name))).digest('hex')
  return result
}
const sources = ['index.html', 'package.json', 'package-lock.json', 'tsconfig.json', 'vite.config.ts']
for (const directory of ['src', 'public', 'scripts']) sources.push(...await filesIn(directory))
const outputs = (await filesIn('dist')).filter(name => name !== 'dist/build-info.json')
if (!outputs.includes('dist/index.html')) throw new Error('Build did not produce dist/index.html')
const manifest = {
  schema: 'safetrace-frontend-build-1',
  generated_at: new Date().toISOString(),
  sources: await hashes(sources),
  outputs: await hashes(outputs, 'dist/'),
}
await writeFile(path.join(root, 'dist/build-info.json'), JSON.stringify(manifest, null, 2) + '\n', 'utf8')
log(`Build fingerprint saved: ${sources.length} sources, ${outputs.length} output files.`)
