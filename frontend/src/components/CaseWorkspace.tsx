import { lazy, Suspense, useEffect, useRef, useState } from 'react'
import type { KeyboardEvent } from 'react'
import { ArrowLeft, ArrowUpRight, Check, CheckCheck, Download, FileText, GitBranch, History, Info, Network, Play, Plus, RotateCcw, Square } from 'lucide-react'
import type { Case, URLCorrectionRequest } from '../types'
import AnalysisMessage from './AnalysisMessage'
import PresentationView from './PresentationView'
import { contexts, date, decisions, errorMessage, isActive, methods, modes, stageNames } from '../lib'
import { fetchExport } from '../export'
import { reviewRecency } from '../review'
import { Loading, PriorityBadge, Status } from './UI'
import MaterialsView from './MaterialsView'
import RouteView from './RouteView'
import EvidenceDrawer from './EvidenceDrawer'
import AnalysisDetails from './AnalysisDetails'
import LinkAuditView from './LinkAuditView'
import TrackExtensions from './TrackExtensions'

const GraphView = lazy(() => import('./GraphView'))
const tabs = [{ id: 'materials', name: 'Материалы', Icon: FileText }, { id: 'route', name: 'Маршрут', Icon: GitBranch }, { id: 'graph', name: 'Граф связей', Icon: Network }, { id: 'security', name: 'Вне трека · эксперимент', Icon: Info }, { id: 'review', name: 'Решение', Icon: CheckCheck }]

export default function CaseWorkspace({ current, runtimeVersions, view, busy, onView, onBack, onOpen, onAdd, onRetry, onDecision, onCorrect }: {
  current: Case; view: string; busy: boolean; onView: (view: string) => void; onBack: () => void; onOpen: (id: string) => void;
  onAdd: () => void; onRetry: () => void; onDecision: (decision: string, comment: string) => Promise<void>;
  runtimeVersions?: Record<string, string>;
  onCorrect: (value: URLCorrectionRequest) => Promise<void>;
}) {
  const [materialId, setMaterialId] = useState(current.materials[0]?.id || '')
  const [evidenceIds, setEvidenceIds] = useState<string[]>([])
  const [originalEvidence, setOriginalEvidence] = useState<string>()
  const [sectionJump, setSectionJump] = useState(0)
  const pendingSection = useRef<string | null>(null)
  const [exporting, setExporting] = useState(false), [exportError, setExportError] = useState('')
  const active = isActive(current.status)
  const recency = reviewRecency(current)
  const reviewTitle = recency === 'earlier' ? 'Проверьте новый анализ' : recency === 'updating' ? 'Анализ обновляется' : recency === 'unknown' ? 'Сохраненное решение' : current.decisions.length ? decisions[current.decisions.at(-1)!.decision] : 'Примите решение'
  const reviewHint = recency === 'earlier' ? 'Решение было до повторного запуска' : recency === 'updating' ? 'Решение после завершения' : recency === 'unknown' ? 'Проверьте время и источники' : current.decisions.length ? 'Посмотреть историю проверки' : 'После проверки источников'
  const priorityMaterial = current.materials.find(m => m.id === current.score?.material_id)
  const priorityContext = priorityMaterial?.context || current.context
  const selectedView = tabs.some(t => t.id === view) ? view : 'materials'
  useEffect(() => {
    if (pendingSection.current === view) {
      pendingSection.current = null
      document.getElementById('tab-' + view)?.focus({ preventScroll: true })
      document.getElementById('panel-' + view)?.scrollIntoView({ block: 'start' })
    }
  }, [view, sectionJump])
  function openSection(next: string) {
    pendingSection.current = next; setSectionJump(value => value + 1); onView(next)
  }
  function openMaterial(id: string, evidenceId?: string) {
    setMaterialId(id); setOriginalEvidence(evidenceId); setEvidenceIds([]); openSection('materials')
  }
  async function exportCase() {
    setExporting(true); setExportError('')
    try {
      const file = await fetchExport(current.id)
      const url = URL.createObjectURL(file)
      const link = document.createElement('a')
      link.href = url; link.download = 'safetrace-' + current.id.slice(0, 8) + '.zip'
      document.body.append(link); link.click(); link.remove()
      window.setTimeout(() => URL.revokeObjectURL(url), 60_000)
    } catch (error) { setExportError(errorMessage(error)) }
    finally { setExporting(false) }
  }
  function handleTabs(e: KeyboardEvent<HTMLDivElement>) {
    const keys = ['ArrowRight', 'ArrowLeft', 'Home', 'End']
    if (!keys.includes(e.key)) return
    e.preventDefault()
    const index = tabs.findIndex(t => t.id === selectedView)
    const next = e.key === 'Home' ? 0 : e.key === 'End' ? tabs.length - 1 : (index + (e.key === 'ArrowRight' ? 1 : -1) + tabs.length) % tabs.length
    onView(tabs[next].id)
    e.currentTarget.querySelectorAll<HTMLButtonElement>('[role="tab"]')[next].focus()
  }
  if (view === 'presentation') return <>
    <header className="presentation-heading"><div><div className="eyebrow">SAFETRACE KZ · РЕЖИМ ПОКАЗА</div><h1>{current.title}</h1></div><div className="actions"><button onClick={onBack}><ArrowLeft size={16} />Очередь</button><button onClick={() => onView('materials')}>Рабочий режим</button>{active && <button disabled={busy} onClick={onRetry}><Square size={15} />Отменить</button>}<button className="primary" disabled={exporting} aria-busy={exporting} onClick={() => void exportCase()}><Download size={17} />{exporting ? 'Подготовка…' : 'Экспорт'}</button></div></header>
    {exportError && <div className="alert error" role="alert">{exportError}</div>}
    <PresentationView current={current} onEvidence={setEvidenceIds} onMaterial={openMaterial} onGraph={() => openSection('graph')} onRetry={onRetry} busy={busy} />
    <button className="text-button" onClick={() => openSection('security')}>Другие признаки: подмена домена и запросы кодов<ArrowUpRight size={16} /></button>
    {evidenceIds.length > 0 && <EvidenceDrawer current={current} ids={evidenceIds} close={() => setEvidenceIds([])} onOriginal={openMaterial} onOpen={onOpen} />}
  </>
  return <>
    <div className="case-breadcrumb"><button className="text-button" onClick={onBack}><ArrowLeft size={16} />Очередь проверки</button><span>/</span><code>{current.id.slice(0, 8)}</code></div>
    <header className="case-heading"><div><h1>{current.title}</h1><div className="case-meta"><span className={'mode-label ' + current.mode}>{modes[current.mode]}</span><span>{date(current.created_at)} · UTC+5</span><span>{current.materials.length} мат.</span></div></div><div className="actions">
      <button onClick={() => onView('presentation')}><Play size={16} />Режим показа</button>
      <button disabled={active || busy || current.mode === 'replay'} onClick={onAdd}><Plus size={16} />Материал</button>
      <button disabled={busy || current.mode === 'replay'} onClick={onRetry}>{active ? <Square size={15} /> : <RotateCcw size={15} />}{active ? 'Отменить' : 'Повторить анализ'}</button>
      <button className="primary" disabled={exporting} aria-busy={exporting} onClick={() => void exportCase()}><Download size={17} />{exporting ? 'Подготовка…' : 'Экспорт'}</button>
    </div></header>
    {exportError && <div className="alert error" role="alert">{exportError}</div>}
    {current.analysis_assisted && <div className="mode-banner"><Info size={16} /><span>Анализ с ручным уточнением адреса. Первичный автоматический результат сохранён в истории; уточнение не включается в автоматические метрики качества.</span></div>}
    {(current.mode === 'synthetic' || current.mode === 'replay') && <div className="mode-banner"><Info size={16} /><span>{current.mode === 'replay' ? 'Сохраненный повтор. OCR, модель и сеть не вызываются заново.' : 'Синтетический стенд. Публикации, адреса и страницы созданы для демонстрации.'}</span></div>}
    <AnalysisMessage current={current} view={selectedView} busy={busy} onView={onView} onRetry={onRetry} />
    <section className="case-summary" aria-label="Результат анализа">
      <div className="priority-summary"><div className={'priority-value ' + (current.sufficient_data === false ? 'unknown' : current.score?.level || '')}>{current.sufficient_data === false ? '—' : current.score?.value ?? '…'}<small>/ 100</small></div><div><span className="field-hint">{active && current.score ? 'Предыдущий индекс · обновляется' : 'Приоритет ручной проверки'}</span><PriorityBadge item={current} /><small>Индекс, не вероятность нарушения</small></div></div>
      <div className="processing-summary"><Status value={current.status} /><div className="pipeline" aria-label="Этапы анализа">{Object.entries(current.stages).map(([stage, value]) => <span key={stage} className={value} title={(stageNames[stage] || stage) + ': ' + value}>{value === 'completed' ? <Check size={12} /> : <span className="stage-dot" />}{stageNames[stage] || stage}</span>)}</div>{active && <progress max={100} value={current.progress} aria-label="Прогресс анализа" />}</div>
      <button className="summary-review" onClick={() => onView('review')}><CheckCheck size={20} /><span>{reviewTitle}<small>{reviewHint}</small></span><ArrowUpRight size={17} /></button>
    </section>
    {active && <p className="field-hint">Отмена выполняется после текущего прохода OCR или сетевого запроса. Исходные материалы сохраняются.</p>}
    <details className="reasons-panel" open={current.sufficient_data === false}>
      <summary><Info size={17} /><span>{current.sufficient_data === false ? 'Почему данных недостаточно' : 'Почему такой приоритет'}<small>Подтвержденные основания: {current.score?.contributions.length || 0} · {methods[current.provider || 'local_rule']}</small></span></summary>
      <div className="reasons-body"><div className="reason-list">{current.score?.contributions.map(c => <button key={c.key} disabled={!c.evidence_ids.length} onClick={() => setEvidenceIds(c.evidence_ids)}><span>{c.title}</span><strong>{c.weight > 0 ? '+' : ''}{c.weight}</strong><ArrowUpRight size={16} /></button>)}{!current.score?.contributions.length && <p>Подтвержденных вкладов пока нет.</p>}</div><div><h3>{priorityMaterial ? 'Контекст материала' : 'Контекст и ограничения'}</h3>{priorityMaterial && <button className="text-button" onClick={() => openMaterial(priorityMaterial.id)}>Индекс по материалу: {priorityMaterial.source} <ArrowUpRight size={15} /></button>}<p>{contexts[priorityContext?.context || ''] || 'Контекст еще не определен'}{priorityContext?.language ? ' · ' + priorityContext.language.toUpperCase() : ''}</p>{priorityContext?.contradictions.map((c, i) => <p className="warning-text" key={i}>{c}</p>)}<ul>{current.limitations.map((l, i) => <li key={i}>{l}</li>)}</ul></div></div>
    </details>
    <AnalysisDetails current={current} runtimeVersions={runtimeVersions} />
    <TrackExtensions current={current} onMaterial={openMaterial} />
    <div className="workspace-tabs" role="tablist" aria-label="Разделы случая" onKeyDown={handleTabs}>{tabs.map(({ id, name, Icon }) => <button key={id} id={'tab-' + id} role="tab" aria-selected={selectedView === id} aria-controls={'panel-' + id} tabIndex={selectedView === id ? 0 : -1} onClick={() => onView(id)}><Icon size={18} />{name}{id === 'materials' && <span>{current.materials.length}</span>}</button>)}</div>
    {selectedView !== 'review' && <div className="workspace-panel" id={'panel-' + selectedView} role="tabpanel" aria-labelledby={'tab-' + selectedView}>
      {selectedView === 'materials' && <MaterialsView key={materialId + (originalEvidence || '')} current={current} materialId={materialId} selectedEvidence={originalEvidence} onMaterial={id => { setMaterialId(id); setOriginalEvidence(undefined) }} onEvidence={setEvidenceIds} onCorrect={onCorrect} />}
      {selectedView === 'route' && <RouteView current={current} onEvidence={setEvidenceIds} onMaterial={openMaterial} />}
      {selectedView === 'graph' && <Suspense fallback={<Loading>Загрузка графа…</Loading>}><GraphView data={current.graph} caseId={current.id} onEvidence={setEvidenceIds} onOpen={onOpen} /></Suspense>}
      {selectedView === 'security' && <LinkAuditView key={current.id + current.analysis_id + current.status} current={current} onEvidence={setEvidenceIds} />}
    </div>}
    <div className="workspace-panel" id="panel-review" role="tabpanel" aria-labelledby="tab-review" hidden={selectedView !== 'review'}><Decision current={current} onSave={onDecision} /></div>
    {evidenceIds.length > 0 && <EvidenceDrawer current={current} ids={evidenceIds} close={() => setEvidenceIds([])} onOriginal={openMaterial} onOpen={onOpen} />}
  </>
}

function Decision({ current, onSave }: { current: Case; onSave: (d: string, c: string) => Promise<void> }) {
  const [decision, setDecision] = useState(current.decisions.at(-1)?.decision || 'needs_data'), [comment, setComment] = useState('')
  const [saving, setSaving] = useState(false), [error, setError] = useState(''), [saved, setSaved] = useState(false)
  const recency = reviewRecency(current)
  const analyzing = isActive(current.status)
  return <div className="review-workspace"><section><div className="workspace-heading"><div><h2>Решение аналитика</h2><p>Сохраняется отдельно от автоматического индекса и не меняет результаты теста.</p></div></div>
    {recency === 'earlier' && <p className="alert" role="status">После последнего решения анализ выполнен заново. Проверьте обновленные источники и сохраните новое решение. Прежняя запись остается в истории.</p>}
    {recency === 'updating' && <p className="alert" role="status">Идет анализ. Сохранить решение можно после завершения; прежние решения доступны в истории.</p>}
    {recency === 'unknown' && <p className="alert" role="status">В сохраненных данных не удалось сопоставить время решения и анализа. Проверьте источники перед новым решением.</p>}
    <form onSubmit={async e => { e.preventDefault(); if (analyzing) return; setSaving(true); setError(''); setSaved(false); try { await onSave(decision, comment); setComment(''); setSaved(true) } catch (e) { setError(errorMessage(e)) } finally { setSaving(false) } }}>
      <fieldset disabled={saving || analyzing}><label>Оценка<select value={decision} onChange={e => { setDecision(e.target.value); setSaved(false) }}>{Object.entries(decisions).map(([v, label]) => <option key={v} value={v}>{label}</option>)}</select></label><label>Комментарий<textarea rows={5} maxLength={2000} value={comment} onChange={e => { setComment(e.target.value); setSaved(false) }} placeholder="Какие источники проверены? Что подтверждено и каких данных не хватает?" /></label></fieldset>
      {error && <div className="alert error" role="alert">{error}</div>}
      <button className="primary" type="submit" disabled={saving || analyzing}><Check size={17} />{saving ? 'Сохранение…' : 'Сохранить решение'}</button>{saved && recency === 'saved' && <p className="success-message" role="status">Решение сохранено в истории случая.</p>}
    </form>
    <div className="review-checklist"><h3>Перед решением</h3><p>Проверьте исходный материал, назначение ссылки и основания совпадения. Отдельно оцените предупреждение, новость или образовательный контекст.</p></div>
  </section><section className="decision-history"><div className="section-title"><History size={18} /><h2>История проверки</h2><span className="badge">{current.decisions.length}</span></div>{current.decisions.length ? [...current.decisions].reverse().map(d => <article key={d.id}><strong>{decisions[d.decision]}</strong><time>{date(d.at)} · UTC+5</time><p>{d.comment || 'Без комментария'}</p></article>) : <p className="muted">Решений пока нет. Сохраните первую проверку.</p>}</section></div>
}
