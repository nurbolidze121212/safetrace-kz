import { useEffect, useRef, useState } from 'react'
import cytoscape from 'cytoscape'
import { ArrowRight, ArrowUpRight, Focus, Maximize2, Minus, Plus } from 'lucide-react'
import type { GraphData } from '../types'
import { edgeNames } from '../lib'
import { graphScopeEdges } from '../graphScope'
import type { GraphScope } from '../graphScope'
import { Empty } from './UI'

const shortEdges: Record<string, string> = { contains_link: 'URL', redirects: 'HTTP', page_link: 'HTML', contains_identifier: 'Код', matching_identifier: 'Совпадение', observed: 'Ответ', on_domain: 'Домен', published: 'Источник' }
function nodeLabel(label: string) {
  let readable = label
  try {
    const url = new URL(label)
    if (url.protocol === 'http:' || url.protocol === 'https:') readable = url.hostname + '\n' + url.pathname + url.search
  } catch { /* Non-URL source labels remain unchanged. */ }
  const truncated = readable.length > 85 ? readable.slice(0, 82) + '…' : readable
  return truncated.split('\n').flatMap(line => {
    const lines: string[] = []
    let current = ''
    for (const word of line.split(/\s+/).filter(Boolean)) {
      if ([...current, ...word].length + 1 > 22 && current) { lines.push(current); current = '' }
      const letters = [...word]
      while (letters.length > 22) { lines.push(letters.splice(0, 22).join('')) }
      current += (current ? ' ' : '') + letters.join('')
    }
    if (current) lines.push(current)
    return lines
  }).join('\n')
}
export default function GraphView({ data, caseId, onEvidence, onOpen }: { data: GraphData; caseId: string; onEvidence: (ids: string[]) => void; onOpen: (id: string) => void }) {
  const container = useRef<HTMLDivElement>(null), cy = useRef<cytoscape.Core | null>(null), selection = useRef(onEvidence)
  const [scope, setScope] = useState<GraphScope>('route'), [filter, setFilter] = useState('all'), [focus, setFocus] = useState('')
  const graphKey = JSON.stringify({ nodes: data.nodes, edges: data.edges })
  const scopedEdges = graphScopeEdges(data, caseId, scope)
  const edges = scopedEdges.filter(e => filter === 'all' || e.type === filter)
  const related = [...new Map(data.nodes.filter(n => n.case_id && n.case_id !== caseId).map(n => [n.case_id!, n])).values()]
  useEffect(() => { selection.current = onEvidence }, [onEvidence])
  useEffect(() => {
    if (!container.current) return
    const stable = JSON.parse(graphKey) as GraphData
    const shown = graphScopeEdges(stable, caseId, scope).filter(e => filter === 'all' || e.type === filter)
    const ids = new Set(shown.flatMap(e => [e.source, e.target]))
    const nodes = stable.nodes.filter(n => ids.has(n.id))
    const ranks = new Map<string, number>()
    const incoming = new Map(nodes.map(n => [n.id, shown.filter(e => e.target === n.id).length]))
    const queue = nodes.filter(n => !incoming.get(n.id)).map(n => n.id)
    queue.forEach(id => ranks.set(id, 0))
    for (let i = 0; i < queue.length; i++) {
      const id = queue[i]
      for (const edge of shown.filter(e => e.source === id)) {
        ranks.set(edge.target, Math.max(ranks.get(edge.target) || 0, (ranks.get(id) || 0) + 1))
        incoming.set(edge.target, (incoming.get(edge.target) || 1) - 1)
        if (!incoming.get(edge.target)) queue.push(edge.target)
      }
    }
    const columns = new Map<number, string[]>()
    nodes.forEach(n => { const rank = ranks.get(n.id) || 0; columns.set(rank, [...(columns.get(rank) || []), n.id]) })
    const positions: Record<string, { x: number; y: number }> = {}
    const columnSpacing = scope === 'route' ? 235 : 285
    columns.forEach((column, rank) => column.forEach((id, index) => { positions[id] = { x: rank * columnSpacing + 110, y: (index - (column.length - 1) / 2) * 145 + 230 } }))
    const instance = cytoscape({
      container: container.current,
      elements: [...nodes.map(n => ({ data: { ...n, label: nodeLabel(n.label) } })), ...shown.map(e => ({ data: { ...e, label: shortEdges[e.type] || edgeNames[e.type] || e.type } }))],
      layout: { name: 'preset', positions, padding: 35 },
      style: [
        { selector: 'node', style: { 'shape': 'round-rectangle', 'width': 184, 'height': 90, 'background-color': '#ffffff', 'border-color': '#a6b5c8', 'border-width': 1.5, 'label': 'data(label)', 'color': '#182b46', 'font-family': 'Segoe UI', 'font-size': 16, 'text-wrap': 'wrap', 'text-max-width': '170px', 'text-valign': 'center', 'text-halign': 'center' } },
        { selector: 'node[type="material"]', style: { 'background-color': '#e8efff', 'border-color': '#3a66c7', 'font-weight': 'bold' } },
        { selector: 'node[type="identifier"]', style: { 'background-color': '#fff3d9', 'border-color': '#b8872b', 'width': 145, 'height': 48 } },
        { selector: 'node[?stopped]', style: { 'border-color': '#a64b33', 'border-style': 'dashed', 'background-color': '#fff0e8' } },
        { selector: 'edge', style: { 'width': 1.8, 'line-color': '#889bb6', 'target-arrow-color': '#889bb6', 'target-arrow-shape': 'triangle', 'curve-style': 'bezier', 'label': 'data(label)', 'font-size': 12, 'color': '#445a76', 'text-background-color': '#f5f7fb', 'text-background-opacity': 1, 'text-background-padding': '4px', 'text-margin-y': -9 } },
        { selector: 'edge[status="inferred"]', style: { 'line-style': 'dashed', 'line-color': '#a27625', 'target-arrow-color': '#a27625' } },
        { selector: ':selected', style: { 'border-width': 3, 'border-color': '#2459c4', 'line-color': '#2459c4', 'target-arrow-color': '#2459c4' } },
        { selector: '.dim', style: { 'opacity': .15 } },
      ],
      minZoom: .2, maxZoom: 2.5,
    })
    instance.on('tap', 'node,edge', event => { setFocus(event.target.id()); selection.current(event.target.data('evidence_ids') || []) })
    if (instance.zoom() > 1) { instance.zoom(1); instance.center() }
    cy.current = instance
    const observer = new ResizeObserver(() => instance.resize())
    observer.observe(container.current)
    return () => { observer.disconnect(); instance.destroy(); cy.current = null }
  }, [graphKey, caseId, scope, filter])
  function focusPath(id: string) {
    const instance = cy.current
    if (!instance) return
    const selected = instance.getElementById(id)
    if (!selected.length) return
    const roots = selected.isEdge() ? selected.connectedNodes() : selected
    const route = selected.union(roots).union(roots.predecessors()).union(roots.successors())
    instance.elements().addClass('dim'); route.removeClass('dim'); instance.fit(route, 50)
  }
  function zoom(factor: number) {
    const instance = cy.current
    if (instance) instance.zoom({ level: instance.zoom() * factor, renderedPosition: { x: instance.width() / 2, y: instance.height() / 2 } })
  }
  return <section className="graph-workspace">
    <header className="workspace-heading"><div><h2>Связи и их основания</h2><p>Выберите узел или стрелку. Все связи доступны также в списке под графом.</p></div><span className="badge">{data.nodes.length} узлов · {data.edges.length} связей</span></header>
    <div className="graph-tools"><div className="segmented" aria-label="Область графа">{([{ id: 'route', label: 'Основной маршрут' }, { id: 'case', label: 'Этот случай' }, { id: 'all', label: 'Все связи' }] as const).map(item => <button key={item.id} aria-pressed={scope === item.id} onClick={() => { setScope(item.id); setFilter('all'); setFocus('') }}>{item.label}</button>)}</div><select aria-label="Тип связи" value={filter} onChange={e => { setFilter(e.target.value); setFocus('') }}><option value="all">Все типы связей</option>{[...new Set(scopedEdges.map(e => e.type))].map(t => <option key={t} value={t}>{edgeNames[t]}</option>)}</select><button disabled={!focus} onClick={() => focusPath(focus)}><Focus size={16} />Фокус</button></div>
    {scope === 'case' && <p className="field-hint">Показаны материалы этого случая и их основания. Совпадения с другими случаями доступны в режиме «Все связи».</p>}
    {edges.length ? <div className="graph-stage"><div className="graph-canvas" ref={container} aria-label="Интерактивный граф связей" /><div className="graph-zoom"><button aria-label="Увеличить граф" onClick={() => zoom(1.25)}><Plus size={18} /></button><button aria-label="Уменьшить граф" onClick={() => zoom(.8)}><Minus size={18} /></button><button aria-label="Вписать весь граф" onClick={() => { cy.current?.elements().removeClass('dim'); cy.current?.fit(undefined, 35) }}><Maximize2 size={18} /></button></div><div className="graph-legend"><span><i />Наблюдение</span><span><i className="dashed" />Предполагаемая связь</span></div></div> : <Empty title="Связей этого типа пока нет" />}
    <p className="field-hint">HTTP — редирект. HTML — ссылка на странице. Полные адреса и основания доступны в списке связей.</p>
    <div className="edge-list-heading"><h3>Проверить связь</h3><span>{edges.length} показано</span></div>
    <div className="edge-list">{edges.map(e => <button key={e.id} onClick={() => { setFocus(e.id); onEvidence(e.evidence_ids) }}><span className="edge-type">{edgeNames[e.type]}<small>{e.status === 'inferred' ? 'Предполагаемая' : 'Наблюдаемая'}</small></span><span className="edge-endpoints"><span>{data.nodes.find(n => n.id === e.source)?.label}</span><ArrowRight size={15} /><span>{data.nodes.find(n => n.id === e.target)?.label}</span></span><ArrowUpRight size={17} /></button>)}</div>
    {related.length > 0 && <section className="related-section"><h3>Связанные случаи <span className="badge">{related.length}</span></h3><p className="field-hint">Совпадение идентификатора — основание проверить связь, не доказательство общего владельца.</p><div>{related.map(n => <button key={n.case_id} onClick={() => onOpen(n.case_id!)}>{n.label}<ArrowUpRight size={16} /></button>)}</div></section>}
    <p className="footnote">{data.limitation}</p>
  </section>
}
