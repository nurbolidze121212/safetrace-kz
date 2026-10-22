import { useCallback, useEffect, useRef, useState } from 'react'
import { Activity, ArrowUpRight, ChartNoAxesCombined, ChevronRight, Inbox, Plus, ShieldCheck, X } from 'lucide-react'
import type { Case, Demo, Evaluation, Health, Summary } from './types'
import { api, errorMessage, isActive, post } from './lib'
import QueueView from './components/QueueView'
import CreateDialog from './components/CreateDialog'
import CaseWorkspace from './components/CaseWorkspace'
import EvaluationView from './components/EvaluationView'
import { Loading } from './components/UI'

type FormSession = { kind: 'create' } | { kind: 'add'; caseId: string; caseTitle: string; mode: string }

function readRoute() {
  const hash = window.location.hash.slice(1)
  const [path, query] = hash.split('?')
  const id = path.match(/^case\/([a-f0-9]{32})$/)?.[1]
  return { page: id ? 'case' : path === 'evaluation' ? 'evaluation' : 'queue', id, view: new URLSearchParams(query).get('view') || 'materials', evaluationVersion: new URLSearchParams(query).get('version') || '' }
}
export default function App() {
  const [route, setRoute] = useState(readRoute)
  const [cases, setCases] = useState<Summary[]>([]), [health, setHealth] = useState<Health>(), [demos, setDemos] = useState<Demo[]>([])
  const [current, setCurrent] = useState<Case>(), [evaluation, setEvaluation] = useState<Evaluation>()
  const [form, setForm] = useState<FormSession | null>(null), [error, setError] = useState(''), [busy, setBusy] = useState(false), [ready, setReady] = useState(false)
  const [queueError, setQueueError] = useState(''), [environmentError, setEnvironmentError] = useState('')
  const [caseError, setCaseError] = useState<{ id: string; message: string }>()
  const [evaluationError, setEvaluationError] = useState<{ version: string; message: string }>()
  const readError = queueError || environmentError || (route.page === 'case' && caseError && caseError.id === route.id ? caseError.message : '') || (route.page === 'evaluation' && evaluationError?.version === route.evaluationVersion ? evaluationError.message : '')
  const mainRef = useRef<HTMLElement>(null)
  const caseGeneration = useRef(0)
  const [caseRefresh, setCaseRefresh] = useState(0)
  const navigate = (hash: string) => { window.location.hash = hash }
  const open = (id: string) => navigate('case/' + id)
  const reload = useCallback(async () => { const list = await api<Summary[]>('/cases'); setCases(list); setReady(true); return list }, [])
  useEffect(() => { const handler = () => setRoute(readRoute()); window.addEventListener('hashchange', handler); return () => window.removeEventListener('hashchange', handler) }, [])
  useEffect(() => { mainRef.current?.focus(); window.scrollTo({ top: 0 }) }, [route.page, route.id])
  useEffect(() => {
    let stopped = false
    let environmentReady = false
    let timer: ReturnType<typeof setTimeout>
    const poll = async () => {
      let delay = 6000
      try {
        const list = await api<Summary[]>('/cases')
        if (stopped) return
        setCases(list); setReady(true); setQueueError('')
        delay = list.some(c => isActive(c.status)) ? 2000 : 12000
        try {
          // A fast server restart can occur between polls without a failed request.
          // Refresh runtime versions with each successful queue read as well.
          const [info, examples] = await Promise.all([api<Health>('/health'), environmentReady ? Promise.resolve(undefined) : api<Demo[]>('/demos')])
          if (!stopped) { setHealth(info); if (examples) setDemos(examples); setEnvironmentError(''); environmentReady = true }
        } catch (e) { if (!stopped) { setEnvironmentError(errorMessage(e)); delay = 6000 } }
      } catch (e) { if (!stopped) { setQueueError(errorMessage(e)); environmentReady = false } }
      finally { if (!stopped) timer = setTimeout(poll, delay) }
    }
    void poll()
    return () => { stopped = true; clearTimeout(timer) }
  }, [])
  useEffect(() => {
    if (!route.id) return
    let stopped = false
    let timer: ReturnType<typeof setTimeout>
    const poll = async () => {
      try {
        const generation = caseGeneration.current
        const value = await api<Case>('/cases/' + route.id)
        if (!stopped) {
          if (generation === caseGeneration.current && readRoute().id === value.id) { setCurrent(value); setCaseError(undefined) }
          timer = setTimeout(poll, isActive(value.status) ? 1600 : 12000)
        }
      } catch (e) { if (!stopped) { setCaseError({ id: route.id!, message: errorMessage(e) }); timer = setTimeout(poll, 6000) } }
    }
    void poll()
    return () => { stopped = true; clearTimeout(timer) }
  }, [route.id, caseRefresh])
  useEffect(() => {
    if (route.page !== 'evaluation') return
    let stopped = false
    let timer: ReturnType<typeof setTimeout>
    const load = async () => {
      try {
        const value = await api<Evaluation>('/evaluation' + (route.evaluationVersion ? '?version=' + encodeURIComponent(route.evaluationVersion) : ''))
        if (!stopped) { setEvaluation(value); setEvaluationError(undefined) }
      } catch (e) { if (!stopped) { setEvaluationError({ version: route.evaluationVersion, message: errorMessage(e) }); timer = setTimeout(load, 6000) } }
    }
    void load()
    return () => { stopped = true; clearTimeout(timer) }
  }, [route.page, route.evaluationVersion])
  async function run(action: () => Promise<void>) {
    setBusy(true); setError('')
    try { await action() } catch (e) { setError(errorMessage(e)) } finally { setBusy(false) }
  }
  async function refreshCase(id: string) {
    const generation = ++caseGeneration.current
    try {
      const value = await api<Case>('/cases/' + id)
      if (readRoute().id === id && generation === caseGeneration.current) setCurrent(value)
    } finally {
      if (readRoute().id === id) setCaseRefresh(value => value + 1)
    }
  }
  return <div className="shell">
    <a className="skip-link" href="#main-content" onClick={e => { e.preventDefault(); mainRef.current?.focus() }}>К содержимому</a>
    <aside className="sidebar">
      <a href="#queue" className="brand" aria-label="SafeTrace KZ — очередь проверки"><span className="brandmark"><ShieldCheck size={24} /></span><span>SafeTrace<span className="brand-country">KZ</span><small>ПРОВЕРКА РЕКЛАМНЫХ МАРШРУТОВ</small></span></a>
      <button aria-label="Новый анализ" className="sidebar-create" onClick={() => setForm({ kind: 'create' })}><Plus size={19} /><span>Новый анализ</span></button>
      <div className="nav-label">Рабочая среда</div>
      <nav aria-label="Основная навигация"><a className={route.page !== 'evaluation' ? 'nav active' : 'nav'} href="#queue" aria-label="Очередь проверки" aria-current={route.page === 'queue' ? 'page' : undefined}><Inbox size={19} /><span>Очередь проверки</span><b>{cases.length}</b></a><a className={route.page === 'evaluation' ? 'nav active' : 'nav'} href="#evaluation" aria-label="Оценка качества" aria-current={route.page === 'evaluation' ? 'page' : undefined}><ChartNoAxesCombined size={19} /><span>Оценка качества</span></a></nav>
      {cases.length > 0 && <div className="recent-cases"><div className="nav-label">Недавние случаи</div>{cases.slice(0, 3).map(c => <a href={'#case/' + c.id} key={c.id} className={route.id === c.id ? 'recent active' : 'recent'}><span className="recent-dot" /><span>{c.title}</span><ChevronRight size={14} /></a>)}</div>}
      <div className="sidebar-footer"><div className="runtime-status"><Activity size={17} /><strong>{health ? 'Локальная станция' : 'Подключение…'}</strong></div><p>{health?.offline ? 'Офлайн · данные на этом компьютере' : 'Данные на этом компьютере'}</p><div className="runtime-features"><span className={health?.ocr_installed ? 'available' : ''}>OCR {health?.ocr_installed ? 'готов' : 'не доступен'}</span><span>{health?.provider_available ? 'Gemini настроен' : 'Локальные правила'}</span></div><small>SafeNet KZ · трек 02</small></div>
    </aside>
    <div className="main">
      <header className="topbar"><div><span>SafeTrace KZ</span><ChevronRight size={14} /><strong>{route.page === 'evaluation' ? 'Оценка качества' : route.page === 'case' ? 'Исследование случая' : 'Очередь проверки'}</strong></div><span className="local-tag"><span />{health?.offline ? 'Офлайн' : 'Локально'}<span className="topbar-separator" />UTC+5</span></header>
      <main id="main-content" tabIndex={-1} ref={mainRef}>
        {readError && <div className="alert error" role="status"><span>{readError}<br /><small>Обновление повторится автоматически.</small></span></div>}
        {error && <div className="alert error" role="alert"><span>{error}</span><button className="icon-button" aria-label="Закрыть ошибку" onClick={() => setError('')}><X size={18} /></button></div>}
        {route.page === 'queue' && (ready ? <QueueView cases={cases} demos={demos} busy={busy} onCreate={() => setForm({ kind: 'create' })} onOpen={open} onDemo={(id, replay = false) => void run(async () => { const result = await post<{ id: string }>('/demos/' + id + '?replay=' + replay); open(result.id); await reload() })} onImport={file => void run(async () => { const body = new FormData(); body.append('file', file); const result = await api<{ id: string }>('/import', { method: 'POST', body }); open(result.id); await reload() })} /> : <Loading>Загрузка очереди…</Loading>)}
        {route.page === 'case' && (current && current.id === route.id ? <CaseWorkspace key={current.id} current={current} runtimeVersions={health?.versions} view={route.view} busy={busy} onView={view => navigate('case/' + current.id + '?view=' + view)} onBack={() => navigate('queue')} onOpen={open} onAdd={() => setForm({ kind: 'add', caseId: current.id, caseTitle: current.title, mode: current.mode })} onRetry={() => void run(async () => { await post('/cases/' + current.id + (isActive(current.status) ? '/cancel' : '/retry')); await refreshCase(current.id); await reload() })} onCorrect={async value => { await post('/cases/' + current.id + '/url-corrections', value); await Promise.all([refreshCase(current.id), reload()]) }} onDecision={async (decision, comment) => { await post('/cases/' + current.id + '/decision', { decision, comment }); await refreshCase(current.id); await reload() }} /> : <Loading>Загрузка случая…</Loading>)}
        {route.page === 'evaluation' && <EvaluationView data={!route.evaluationVersion || evaluation?.evaluation_id === route.evaluationVersion ? evaluation : undefined} onVersion={version => navigate('evaluation?version=' + encodeURIComponent(version))} />}
        <footer className="app-footer"><span>SafeTrace KZ · рабочая среда аналитика</span><a href="#evaluation">Методика и ограничения <ArrowUpRight size={14} /></a></footer>
      </main>
    </div>
    {form && <CreateDialog adding={form.kind === 'add'} mode={form.kind === 'add' ? form.mode : undefined} caseTitle={form.kind === 'add' ? form.caseTitle : undefined} health={health} close={() => setForm(null)} onSubmit={async data => {
      const result = form.kind === 'add' ? await post<{ id: string }>('/cases/' + form.caseId + '/materials', data.materials[0]) : await post<{ id: string }>('/cases', data)
      setForm(null); navigate('case/' + result.id + '?view=presentation'); await refreshCase(result.id); await reload()
    }} />}
  </div>
}
