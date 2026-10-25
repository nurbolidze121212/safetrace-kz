import { useEffect, useRef, useState } from 'react'
import cytoscape from 'cytoscape'
import { api, errorMessage } from '../lib'

type Entity = { id: string; label: string; type: string; case_ids: string[]; evidence_ids: string[] }
type Edge = { id: string; source: string; target: string; type: string; evidence_ids: string[]; case_ids: string[] }
type Group = { id: string; size: number; material_ids: string[]; case_ids: string[]; central_material: string }
type Network = { nodes: Entity[]; edges: Edge[]; communities: Group[]; components: Group[];
  counts: Record<string, number>; truncated: boolean; limitations: string[];
  evidence: { id: string; quote?: string; case_id: string; method: string }[] }

export default function NetworkView({ onOpen }: { onOpen: (id: string) => void }) {
  const [mode, setMode] = useState('local'), [state, setState] = useState<{mode: string; data?: Network; error?: string}>()
  const [group, setGroup] = useState(''), [selection, setSelection] = useState<string[]>([])
  const container = useRef<HTMLDivElement>(null)
  const data = state?.mode === mode ? state.data : undefined
  useEffect(() => {
    const controller = new AbortController()
    api<Network>('/network?mode=' + mode, { signal: controller.signal })
      .then(value => { if (!controller.signal.aborted) setState({ mode, data: value }) })
      .catch(error => { if (!controller.signal.aborted) setState({ mode, error: errorMessage(error) }) })
    return () => controller.abort()
  }, [mode])
  useEffect(() => {
    if (!data || !container.current) return
    const chosen = data.communities.find(c => c.id === group)
    const caseIds = chosen ? new Set(chosen.case_ids) : null
    const nodes = data.nodes.filter(n => !caseIds || n.case_ids.some(id => caseIds.has(id)))
    const nodeIds = new Set(nodes.map(n => n.id))
    const edges = data.edges.filter(e => nodeIds.has(e.source) && nodeIds.has(e.target))
    const cy = cytoscape({ container: container.current,
      elements: [...nodes.map(n => ({ data: { ...n, label: n.label.length > 45 ? n.label.slice(0, 42) + '…' : n.label } })), ...edges.map(e => ({ data: e }))],
      layout: { name: 'cose', animate: false, randomize: false, padding: 30 },
      style: [
        { selector: 'node', style: { label: 'data(label)', 'background-color': '#94a3b8', width: 28, height: 28, 'font-size': 10, color: '#26364c', 'text-margin-y': -8, 'text-wrap': 'wrap', 'text-max-width': '130px' } },
        { selector: 'node[type="material"]', style: { 'background-color': '#315fe2', width: 40, height: 40 } },
        { selector: 'node[type="source"]', style: { 'background-color': '#0c8676', shape: 'diamond' } },
        { selector: 'node[type="identifier"]', style: { 'background-color': '#bc781d', shape: 'rectangle' } },
        { selector: 'edge', style: { width: 1, 'line-color': '#bcc7d6', 'curve-style': 'bezier' } },
        { selector: 'edge[type="matching_identifier"]', style: { width: 3, 'line-color': '#bc781d', 'line-style': 'dashed' } },
        { selector: ':selected', style: { 'border-color': '#182b46', 'border-width': 3, 'line-color': '#182b46' } },
      ], minZoom: .08, maxZoom: 3 })
    cy.on('tap', 'node,edge', event => setSelection(event.target.data('evidence_ids') || []))
    const observer = new ResizeObserver(() => cy.resize())
    observer.observe(container.current)
    return () => { observer.disconnect(); cy.destroy() }
  }, [data, group])
  return <section className="network-view">
    <div className="eyebrow">СВЯЗИ МЕЖДУ СЛУЧАЯМИ</div><h1>Сеть материалов</h1>
    <p>Публикации, заявленные источники, домены и реферальные идентификаторы. Группы выделены по точным совпадениям в области домена.</p>
    <label>Источник данных <select value={mode} onChange={e => { setMode(e.target.value); setGroup(''); setSelection([]) }}><option value="local">Локальные случаи</option><option value="synthetic">Синтетические случаи</option><option value="cloud">Случаи с облачным контекстом</option><option value="replay">Сохранённые повторы</option></select></label>
    {state?.mode === mode && state.error && <p role="alert">{state.error}</p>}
    {!state?.error && !data && <p role="status">Загрузка сети…</p>}
    {data && <>
      <p><strong>{data.counts.cases}</strong> случаев · <strong>{data.counts.entities}</strong> сущностей · <strong>{data.counts.matching_pairs}</strong> совпадений · <strong>{data.counts.communities}</strong> групп Louvain · {data.counts.components} компонент</p>
      {data.truncated && <p role="status">Показаны последние 100 случаев выбранного режима. Сеть неполная.</p>}
      {data.counts.cases === 0 ? <p>В этом режиме ещё нет проанализированных материалов. Добавьте случаи или выберите синтетические примеры.</p> : <>
        <label>Группа <select value={group} onChange={e => { setGroup(e.target.value); setSelection([]) }}><option value="">Вся сеть</option>{data.communities.map((c, i) => <option key={c.id} value={c.id}>Группа {i + 1} · {c.size} материалов</option>)}</select></label>
        <div className="network-canvas" ref={container} aria-label="Интерактивный граф сущностей" />
        <details><summary>Группы и переход к случаям</summary>{data.communities.map((c, i) => <article key={c.id}><h3>Группа {i + 1} · {c.size} материалов</h3><p>Наиболее связанный материал: {data.nodes.find(n => n.id === c.central_material)?.label}</p>{c.case_ids.map(id => <button className="button" key={id} onClick={() => onOpen(id)}>Открыть случай {id.slice(0, 8)}</button>)}</article>)}</details>
        <div aria-live="polite"><h3>Источник выбранной связи</h3>{selection.length ? data.evidence.filter(e => selection.includes(e.id)).map(e => <blockquote key={e.id}><p>{e.quote || 'Источник без текстовой цитаты'}</p><button className="text-button" onClick={() => onOpen(e.case_id)}>Открыть оригинал в случае</button></blockquote>) : <p>Нажмите на узел или линию, чтобы увидеть сохранённые источники. Список групп также доступен с клавиатуры.</p>}</div>
      </>}
      <details><summary>Метод и ограничения</summary><p>Louvain: resolution=1, seed=42. Центральный материал выбран по числу связей в проекции материалов. Группировка не изменяет индекс случая.</p><ul>{data.limitations.map(x => <li key={x}>{x}</li>)}</ul></details>
    </>}
  </section>
}
