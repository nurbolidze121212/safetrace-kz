import { useState } from 'react'
import { ArrowUpRight, History } from 'lucide-react'
import type { Case, Observation, Relation } from '../types'
import type { ObservationChange } from '../comparison'
import { compareObservations } from '../comparison'
import { date, isActive, methods } from '../lib'
import { Dialog, Empty } from './UI'

const changeNames = { added: 'Впервые в сравнении', absent: 'Не наблюдался сейчас', changed: 'Есть изменения', same: 'Без изменений' }
export default function RouteComparison({ current }: { current: Case }) {
  const snapshots = (current.history || []).filter(h => h.trace?.observations)
  const [selected, setSelected] = useState(snapshots.length - 1)
  const [showAll, setShowAll] = useState(false)
  const [detail, setDetail] = useState<ObservationChange>()
  const index = Math.max(0, Math.min(selected, snapshots.length - 1))
  const previous = snapshots[index]
  const rows = previous?.trace ? compareObservations(previous.trace, current.trace) : []
  const changed = rows.filter(row => row.kind !== 'same')
  return <details className="route-comparison">
    <summary><History size={18} /><span>Сравнение наблюдений<small>{snapshots.length ? snapshots.length + ' предыдущих анализов' : 'История появится после повторного анализа'}</small></span></summary>
    {isActive(current.status) ? <p className="comparison-note">Дождитесь завершения текущего анализа, чтобы сравнить сохраненные результаты.</p> : previous ? <>
      <div className="comparison-controls"><label>Сравнить текущий анализ с<select aria-label="Сравнить текущий анализ с" value={index} onChange={e => { setSelected(Number(e.target.value)); setDetail(undefined) }}>{snapshots.map((snapshot, i) => <option key={i} value={i}>{date(snapshot.at || '')} · UTC+5 · {snapshot.materials?.length ?? '—'} мат.</option>)}</select></label><label className="check-label"><input type="checkbox" checked={showAll} onChange={e => setShowAll(e.target.checked)} />Показать без изменений</label></div>
      <p className="comparison-note">{changed.length} адресов с различиями из {rows.length}. Сравниваются сохраненные ответы, тексты и переходы. Отсутствие адреса в новом обходе не доказывает, что страница удалена.</p>
      <div className="comparison-versions"><span>Раньше: {previous.versions?.rules || 'Версия не записана'} · индекс {previous.score?.value ?? '—'}</span><span>Сейчас: {current.versions?.rules || 'Версия не записана'} · индекс {current.score?.value ?? '—'}</span></div>
      {previous.versions?.rules !== current.versions?.rules && <p className="comparison-note warning-text">Версии правил различаются. Изменение индекса может быть связано с новой методикой анализа.</p>}
      {!(showAll ? rows : changed).length ? <p className="comparison-note">В наблюдаемых адресах, ответах, текстах и переходах изменений нет.</p> : <div className="table-wrap"><table><thead><tr><th>Адрес</th><th>Результат сравнения</th><th>Источник</th></tr></thead><tbody>{(showAll ? rows : changed).map(row => <tr key={row.url}><td><code>{row.url}</code></td><td><strong>{changeNames[row.kind]}</strong>{row.changes.length > 0 && <small>{row.changes.join(' · ')}</small>}</td><td><button className="text-button" onClick={() => setDetail(row)}>Сравнить ответы <ArrowUpRight size={14} /></button></td></tr>)}</tbody></table></div>}
    </> : <Empty title="Пока одно наблюдение"><p>После повторного анализа здесь можно проверить, изменились ли ответы, переходы и текст страниц.</p></Empty>}
    {detail && <Dialog title="Сравнение сохраненных ответов" onClose={() => setDetail(undefined)} drawer>
      <p className="dialog-intro">Просмотр архива не выполняет новый сетевой запрос.</p><div className="source-url"><code>{detail.url}</code></div>
      <ObservationPanel title="Предыдущее наблюдение" observation={detail.before} relations={(previous?.trace?.relations || []).filter(r => r.from === detail.url)} />
      <ObservationPanel title="Текущее наблюдение" observation={detail.after} relations={(current.trace.relations || []).filter(r => r.from === detail.url)} />
      <p className="footnote">Различия относятся к сохраненным наблюдениям; причина изменения требует ручной проверки.</p>
    </Dialog>}
  </details>
}

function ObservationPanel({ title, observation, relations }: { title: string; observation?: Observation; relations: Relation[] }) {
  return <article className="evidence-item"><h3>{title}</h3>{observation ? <>
    <dl><dt>Время</dt><dd>{date(observation.at)} · UTC+5</dd><dt>Метод</dt><dd>{methods[observation.method] || observation.method}</dd><dt>Ответ</dt><dd>{observation.status_code ? 'HTTP ' + observation.status_code : 'Нет ответа'}</dd></dl>
    {observation.stop && <p className="warning-text">{observation.stop}</p>}
    {observation.location && <div className="source-url"><span>Переход</span><code>{observation.location}</code></div>}
    {relations.length > 0 && <div className="comparison-links"><h4>Сохраненные переходы</h4>{relations.map((relation, i) => <div className="source-url" key={i}><span>{relation.type === 'redirects' ? 'HTTP-переход' : 'Ссылка на странице'}</span><code>{relation.to}</code>{relation.quote && <small>«{relation.quote}»</small>}</div>)}</div>}
    <blockquote>{observation.text || 'Сохраненного текста нет.'}</blockquote><details className="technical-details"><summary>Идентификатор источника</summary><code>{observation.evidence_id}</code></details>
  </> : <p>В этом анализе адрес не наблюдался.</p>}</article>
}
