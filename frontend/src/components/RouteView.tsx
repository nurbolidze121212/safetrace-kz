import { useState } from 'react'
import { ArrowDown, ArrowUpRight, FileText, GitBranch, Link2 } from 'lucide-react'
import type { Case } from '../types'
import { date, edgeNames, methods } from '../lib'
import { routePaths } from '../routes'
import { Empty } from './UI'
import RouteComparison from './RouteComparison'

export default function RouteView({ current, onEvidence, onMaterial }: { current: Case; onEvidence: (ids: string[]) => void; onMaterial: (id: string) => void }) {
  const paths = routePaths(current.trace)
  const [selected, setSelected] = useState(0)
  const selectedIndex = Math.min(selected, Math.max(0, paths.length - 1))
  const path = paths[selectedIndex]
  const sourceEdges = path ? current.graph.edges.filter(e => e.type === 'contains_link' && current.graph.nodes.find(n => n.id === e.target)?.label === path.root) : []
  const materialIds = new Set(sourceEdges.map(e => current.graph.nodes.find(n => n.id === e.source)?.material_id))
  const materials = current.materials.filter(m => materialIds.has(m.id))
  return <section className="route-workspace">
    <header className="workspace-heading"><div><h2>Путь от материала к назначению</h2><p>Каждый шаг построен по сохраненной связи. Выберите наблюдение, чтобы проверить источник.</p></div><span className="badge">{current.trace.observations.length} наблюдений</span></header>
    <RouteComparison current={current} />
    {paths.length > 1 && <div className="route-picker"><label>Маршрут<select aria-label="Выбрать маршрут" value={selectedIndex} onChange={e => setSelected(Number(e.target.value))}>{paths.map((p, i) => <option key={i} value={i}>Маршрут {i + 1} · {p.root} · {p.steps.length} шагов</option>)}</select></label></div>}
    {!path ? <Empty title="Проверенных маршрутов пока нет"><p>Добавьте ссылку или проверьте ограничения анализа.</p></Empty> : <div className="route-story">
      <div className="route-origin"><span className="route-icon"><FileText size={20} /></span><div><h3>Исходный материал</h3>{materials.length ? materials.map(m => <button className="text-button" key={m.id} onClick={() => onMaterial(m.id)}>{m.source} <ArrowUpRight size={15} /></button>) : <p>Ссылка из загруженных материалов</p>}</div></div>
      {path.steps.map((step, i) => {
        const o = step.observation
        const stopped = !!(o?.stop || step.cycle || !o)
        return <article className={'route-step ' + (stopped ? 'stopped' : '')} key={i}>
          <div className="route-connector"><ArrowDown size={16} /><span>{edgeNames[step.relation.type] || step.relation.type}{step.relation.type === 'page_link' ? ' · «' + step.relation.quote + '»' : ''}</span></div>
          <div className="route-step-body"><span className="route-step-number">{String(i + 1).padStart(2, '0')}</span><div className="route-step-content">
            <div className="route-step-heading"><span className={'badge ' + (stopped ? 'insufficient' : 'observed')}>{o?.status_code ? 'HTTP ' + o.status_code : 'Нет ответа'}{stopped ? ' · разрыв' : ''}</span><span className="field-hint">{o ? methods[o.method] : 'Наблюдение отсутствует'}</span></div>
            <code className="route-url">{step.relation.to}</code>
            {stopped && <p className="warning-text">{o?.stop || (step.cycle ? 'Цикл переходов. Продолжение не подтверждено.' : 'Нет сохраненного ответа для этого адреса.')}</p>}
            {o?.text && <div className="route-excerpt">{o.text.length > 330 ? <details><summary>{o.text.slice(0,180)}… <span>Показать текст</span></summary><p>{o.text}</p></details> : <p>{o.text}</p>}</div>}
            {o?.reused_from && <p className="field-hint">Использован уже полученный ответ этого адреса в текущем анализе.</p>}
            {!stopped && i === path.steps.length - 1 && <p className="terminal-note"><Link2 size={15} />Последний проверенный адрес в этом маршруте</p>}
            <button className="text-button" onClick={() => onEvidence([step.relation.evidence_id, ...(o ? [o.evidence_id] : [])])}>Открыть наблюдение <ArrowUpRight size={15} /></button>
          </div></div>
        </article>
      })}
    </div>}
    <details className="observation-log"><summary><GitBranch size={17} />Все наблюдения · {current.trace.observations.length}</summary><div className="table-wrap"><table><thead><tr><th>Время · UTC+5</th><th>Адрес</th><th>Ответ</th><th>Источник</th></tr></thead><tbody>{current.trace.observations.map(o => <tr key={o.id}><td>{date(o.at)}</td><td><code>{o.url}</code></td><td>{o.status_code || 'Разрыв'}</td><td><button className="text-button" onClick={() => onEvidence([o.evidence_id])}>Открыть</button></td></tr>)}</tbody></table></div></details>
  </section>
}
