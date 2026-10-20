import type { Observation, Trace } from './types'

export type ObservationChange = { url: string; before?: Observation; after?: Observation; changes: string[]; kind: 'added' | 'absent' | 'changed' | 'same' }
export function compareObservations(before: Trace, after: Trace): ObservationChange[] {
  const left = new Map(before.observations.map(o => [o.url, o]))
  const right = new Map(after.observations.map(o => [o.url, o]))
  const relations = (trace: Trace, url: string) => JSON.stringify((trace.relations || []).filter(r => r.from === url).map(r => [r.type, r.to, r.quote]).sort((a, b) => JSON.stringify(a).localeCompare(JSON.stringify(b))))
  return [...new Set([...right.keys(), ...left.keys()])].map(url => {
    const previous = left.get(url), current = right.get(url)
    const changes: string[] = []
    if (previous && current) {
      if (previous.status_code !== current.status_code) changes.push('HTTP-ответ')
      if (previous.text !== current.text) changes.push('Текст страницы')
      if ((previous.stop || '') !== (current.stop || '')) changes.push('Причина остановки')
      if ((previous.location || '') !== (current.location || '') || relations(before, url) !== relations(after, url)) changes.push('Переходы')
      if (previous.method !== current.method) changes.push('Метод наблюдения')
    }
    return { url, before: previous, after: current, changes, kind: !previous ? 'added' : !current ? 'absent' : changes.length ? 'changed' : 'same' }
  })
}
