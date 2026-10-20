import { useCallback, useEffect, useRef, useState } from 'react'
import type { FormEvent, ReactNode } from 'react'
import cytoscape from 'cytoscape'
import { ArrowDown, ArrowLeft, ArrowUpRight, Check, ChevronRight, CircleHelp, Download, FileSearch,
  FileText, GitBranch, ImagePlus, Layers, LoaderCircle, Plus, Search, ShieldCheck, SlidersHorizontal,
  Upload, X } from 'lucide-react'

type Evidence = {id:string; quote:string; source_id:string; method:string; at:string; url?:string;
  material_id?:string; confidence?:number; polygon?:number[][]; note?:string; case_id?:string}
type GraphNode = {id:string; type:string; label:string; evidence_ids:string[]; case_id?:string; stopped?:boolean}
type Edge = {id:string; source:string; target:string; type:string; label:string; evidence_ids:string[];
  method:string; status:string; at:string}
type GraphData = {nodes:GraphNode[]; edges:Edge[]; evidence:Evidence[]; limitation?:string}
type Score = {value:number; level:string; meaning:string; contributions:{key:string;title:string;weight:number;evidence_ids:string[]}[]}
type Summary = {id:string; title:string; mode:string; status:string; created_at:string; score?:Score;
  progress:number; stage:string; sufficient_data?:boolean; material_count:number; decision?:string}
type Material = {id:string;text:string;url:string;source:string;image_id?:string;published_at?:string;
  ocr?:{text:string;width:number;height:number;model:string;lines:{text:string;confidence:number;uncertain?:boolean;warnings?:string[];evidence_id:string;polygon:number[][]}[]}}
type Case = Summary & {materials:Material[]; graph:GraphData; limitations:string[];
  context?:{language:string; context:string; contradictions:string[]}; provider?:string;
  claims?:{quote:string;source_id:string;start:number;end:number;evidence_id:string}[];
  trace:{observations:{id:string;url:string;at:string;status_code:number|null;text:string;stop?:string;
    location?:string;evidence_id:string;method:string}[]};
  decisions:{id:number;at:string;decision:string;comment:string}[]; elapsed_ms?:number;
  stages:Record<string,string>}
type Health = {provider_available:boolean;ocr_installed:boolean;offline:boolean;allowed_hosts:string[];local_mode:string}
type Demo = {id:string;title:string;subtitle:string}
type Metrics = {n:number;tp:number;fp:number;tn:number;fn:number;precision:number|null;recall:number;
  f1:number;fpr:number;coverage:number;insufficient:number;precision_ci:number[];fpr_ci:number[];p50_ms:number;p95_ms:number}
type Evaluation = {available:boolean;message?:string;dataset_version?:string;limitations?:string[];
  variants?:Record<string,Metrics>;slices?:Record<string,Metrics>;errors?:{id:string;truth:number;predicted:number;title:string}[];
  image_count?:number;test_count?:number;frozen_at?:string}

const statuses:Record<string,string> = {pending:'Ожидает',running:'Выполняется',completed:'Завершен',
  partial:'Частично завершен',error:'Ошибка',cancelled:'Отменен'}
const levels:Record<string,string> = {high:'▲ Высокий',medium:'◆ Средний',low:'○ Низкий'}
const modes:Record<string,string> = {local:'Локальный анализ',cloud:'Облачный контекст',synthetic:'Синтетический стенд',replay:'Повтор сохраненного анализа'}
const methods:Record<string,string> = {local_rule:'Локальное правило',cloud_model:'Облачная модель',network:'Сетевое наблюдение',
  synthetic_transport:'Синтетический транспорт',ocr:'OCR · распознавание',user_supplied:'Заявлено при импорте',
  source_text:'Текст источника',scoped_exact_match:'Совпадение в области домена',url_parser:'Разбор URL'}
const edgeNames:Record<string,string> = {published:'Опубликован',contains_link:'Содержит ссылку',redirects:'HTTP-переход',
  page_link:'Ссылка на странице',contains_identifier:'Содержит идентификатор',matching_identifier:'Совпадение идентификатора',
  observed:'Наблюдение',on_domain:'Домен'}
const stageNames:Record<string,string> = {originals:'Оригиналы',ocr:'Распознавание',features:'Признаки',
  links:'Переходы',graph:'Связи',priority:'Приоритет',interrupted:'Прервано перезапуском'}
const decisions:Record<string,string> = {confirmed:'Подтвердить признаки',false_positive:'Ложное срабатывание',needs_data:'Нужны данные'}
const contexts:Record<string,string> = {promotion:'Продвижение',warning:'Предупреждение',news:'Новость',education:'Образовательный разбор',free_game:'Бесплатная игра',ordinary:'Обычный контекст',ambiguous:'Неоднозначно'}
const date = (d:string) => new Intl.DateTimeFormat('ru-RU',{timeZone:'Asia/Qyzylorda',day:'2-digit',
  month:'short',hour:'2-digit',minute:'2-digit'}).format(new Date(d))
const pct = (n:number|null) => n === null ? '—' : (n*100).toFixed(1)+'%'
const initialCase = window.location.hash.match(/^#case\/([a-f0-9]{32})$/)?.[1]
async function api<T>(path:string, init?:RequestInit):Promise<T> {
  const r = await fetch('/api'+path, init)
  if(!r.ok) {const e = await r.json().catch(()=>({detail:'Сервер недоступен'})); throw new Error(typeof e.detail === 'string' ? e.detail : 'Проверьте заполненные поля.')}
  return r.json()
}
const post = <T,>(path:string,data:unknown={}) => api<T>(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)})

function Highlight({text,quotes}:{text:string;quotes:string[]}) {
  const intervals:{start:number;end:number}[] = []
  quotes.forEach(q=>{const start=text.indexOf(q);if(start>=0) intervals.push({start,end:start+q.length})})
  intervals.sort((a,b)=>a.start-b.start)
  let pos=0
  const result:ReactNode[]=[]
  intervals.forEach((r,i)=>{if(r.start<pos)return;result.push(text.slice(pos,r.start),<mark key={i}>{text.slice(r.start,r.end)}</mark>);pos=r.end})
  result.push(text.slice(pos))
  return <>{result}</>
}

export default function App(){
  const [page,setPage]=useState(initialCase?'case':'queue')
  const [cases,setCases]=useState<Summary[]>([])
  const [health,setHealth]=useState<Health>()
  const [demos,setDemos]=useState<Demo[]>([])
  const [current,setCurrent]=useState<Case>()
  const [currentId,setCurrentId]=useState<string|undefined>(initialCase)
  const [create,setCreate]=useState(false)
  const [adding,setAdding]=useState(false)
  const [query,setQuery]=useState('')
  const [filter,setFilter]=useState('all')
  const [error,setError]=useState('')
  const [busy,setBusy]=useState('')
  const [evidenceIds,setEvidenceIds]=useState<string[]>([])
  const [evalData,setEvalData]=useState<Evaluation>()
  const [tab,setTab]=useState('materials')
  const drawerRef=useRef<HTMLElement>(null)
  useEffect(()=>{
    if(!evidenceIds.length)return
    const previous=document.activeElement as HTMLElement|null
    const key=(event:KeyboardEvent)=>{
      if(event.key==='Escape'){setEvidenceIds([]);return}
      if(event.key==='Tab'){
        const elements=drawerRef.current?.querySelectorAll<HTMLElement>('button,a[href]')
        if(!elements?.length)return
        if(event.shiftKey&&document.activeElement===elements[0]){event.preventDefault();elements[elements.length-1].focus()}
        else if(!event.shiftKey&&document.activeElement===elements[elements.length-1]){event.preventDefault();elements[0].focus()}
      }
    }
    document.addEventListener('keydown',key)
    return()=>{document.removeEventListener('keydown',key);previous?.focus()}
  },[evidenceIds.length])
  const reload=useCallback(async()=>{try{setCases(await api<Summary[]>('/cases'))}catch(e){setError(String(e))}},[])
  useEffect(()=>{window.history.replaceState(null,'',page==='case'&&currentId?'#case/'+currentId:'#'+page)},[page,currentId])
  useEffect(()=>{void reload();void api<Health>('/health').then(setHealth).catch(e=>setError(String(e)));
    void api<Demo[]>('/demos').then(setDemos).catch(e=>setError(String(e)))},[reload])
  useEffect(()=>{
    if(!currentId)return
    let stopped=false
    const refresh=()=>api<Case>('/cases/'+currentId).then(d=>{if(!stopped)setCurrent(d)}).catch(e=>{if(!stopped)setError(String(e))})
    void refresh()
    const timer=setInterval(()=>{void refresh();void reload()},1600)
    return()=>{stopped=true;clearInterval(timer)}
  },[currentId,reload])
  useEffect(()=>{if(page==='evaluation')void api<Evaluation>('/evaluation').then(setEvalData).catch(e=>setError(String(e)))},[page])
  const open=(id:string)=>{setCurrent(undefined);setCurrentId(id);setPage('case');setEvidenceIds([]);setTab('materials')}
  const run=async(label:string,fn:()=>Promise<void>)=>{setBusy(label);setError('');try{await fn()}catch(e){setError(String(e))}finally{setBusy('')}}
  const demo=(id:string,replay=false)=>void run(id,async()=>{const d=await post<{id:string}>('/demos/'+id+'?replay='+replay);open(d.id);await reload()})
  const shown=cases.filter(c=>(c.title.toLowerCase().includes(query.toLowerCase())||c.id.includes(query))&&
    (filter==='all'||(c.sufficient_data!==false&&c.score?.level===filter)||(filter==='unfinished'&&c.status!=='completed')))
  const active=current?.status==='pending'||current?.status==='running'
  const selected=current?.graph.evidence.filter(e=>evidenceIds.includes(e.id))||[]
  return <div className="shell">
    <aside className="sidebar">
      <a className="brand" href="#" onClick={e=>{e.preventDefault();setPage('queue');setCurrentId(undefined)}}><span className="brandmark"><ShieldCheck size={23}/></span><span>SafeTrace <b>KZ</b><small>АНАЛИТИЧЕСКАЯ СРЕДА</small></span></a>
      <div className="workspace-label">РАБОЧЕЕ ПРОСТРАНСТВО</div>
      <nav aria-label="Основная навигация">
        <button className={page!=='evaluation'?'nav active':'nav'} onClick={()=>{setPage('queue');setCurrentId(undefined);void reload()}}><Layers size={18}/>Случаи<span>{cases.length}</span></button>
        <button className={page==='evaluation'?'nav active':'nav'} onClick={()=>{setPage('evaluation');setCurrentId(undefined)}}><SlidersHorizontal size={18}/>Оценка качества</button>
      </nav>
      <div className="side-note"><GitBranch size={24}/><h3>От сигнала к источнику</h3><p>Каждая связь открывает материал, на котором она основана.</p></div>
      <div className="side-bottom"><span className="status-dot"/>Локальная рабочая станция<small>SafeNet KZ · трек 02</small></div>
    </aside>
    <div className="main">
      <header className="topbar"><span>SafeNet KZ <ChevronRight size={14}/><b>{page==='evaluation'?'Методика и результаты':page==='case'?'Досье случая':'Очередь проверки'}</b></span><span className="top-tag"><span className="status-dot"/>{health?.offline?'Офлайн-режим':'Локальный режим'}<span className="avatar">АН</span></span></header>
      <main>
      {error&&<div className="alert error" role="alert">{error}<button aria-label="Закрыть ошибку" onClick={()=>setError('')}><X size={16}/></button></div>}
      {page==='queue'&&<>
        <div className="page-heading"><div><div className="eyebrow">ПРОВЕРКА СКРЫТОГО ПРОДВИЖЕНИЯ</div><h1>Увидеть весь маршрут.</h1><p>Соберите материал, проверьте переходы и примите обоснованное решение.</p></div><button className="primary" onClick={()=>setCreate(true)}><Plus size={18}/>Новый анализ</button></div>
        <section className="intro-strip"><span className="icon-tile"><FileSearch size={25}/></span><div><strong>Начните с материала</strong><p>Текст, ссылка или изображение. Оригиналы и источники выводов сохраняются.</p></div><button className="quiet" onClick={()=>setCreate(true)}>Загрузить материал <ArrowUpRight size={17}/></button></section>
        <div className="section-label"><h2>Попробуйте на безопасном стенде</h2><span>3 синтетических сценария</span></div>
        <div className="demo-grid">{demos.map((d,i)=><article className="demo-card" key={d.id}>
          <div className="demo-top"><span className="number">0{i+1}</span><span className="tag">DEMO</span></div>
          <div className="mini-route"><span/>{i===2?<CircleHelp size={20}/>:<><i/><span/><i/><span/></>}</div>
          <h3>{d.title}</h3><p>{d.subtitle}</p>
          <div className="demo-actions"><button disabled={!!busy} onClick={()=>demo(d.id)}>Проанализировать <ArrowUpRight size={16}/></button><button className="replay" title="Открыть сохраненный результат без нового анализа" disabled={!!busy} onClick={()=>demo(d.id,true)}>Повтор</button></div>
        </article>)}</div>
        <section className="queue-section"><div className="section-label"><h2>Случаи <span className="count">{cases.length}</span></h2><span>Asia/Qyzylorda · UTC+5</span></div>
          <div className="table-tools"><label className="search"><Search size={17}/><input aria-label="Поиск случаев" placeholder="Поиск по названию или ID" value={query} onChange={e=>setQuery(e.target.value)}/></label>
            <select aria-label="Фильтр приоритета" value={filter} onChange={e=>setFilter(e.target.value)}><option value="all">Все приоритеты</option><option value="high">Высокий</option><option value="medium">Средний</option><option value="low">Низкий</option><option value="unfinished">Незавершенные</option></select>
            <label className="quiet import-label"><Upload size={16}/>JSONL<input type="file" accept=".jsonl,.json" hidden onChange={e=>{const file=e.target.files?.[0];if(file)void run('import',async()=>{const f=new FormData();f.append('file',file);const d=await api<{id:string}>('/import',{method:'POST',body:f});open(d.id);await reload()});e.target.value=''}}/></label>
          </div>
          {shown.length?<div className="table-wrap"><table><thead><tr><th>МАТЕРИАЛ / СЛУЧАЙ</th><th>ПРИОРИТЕТ</th><th>ОБРАБОТКА</th><th>СОЗДАН</th><th/></tr></thead><tbody>{shown.map(c=><tr key={c.id} onClick={()=>open(c.id)}>
            <td><button className="case-name" onClick={()=>open(c.id)}>{c.title}</button><small>{modes[c.mode]} · {c.material_count} мат.</small></td>
            <td>{c.sufficient_data===false?<span className="risk medium">? Недостаточно данных</span>:c.score?<span className={'risk '+c.score.level}>{levels[c.score.level]} <b>{c.score.value}</b></span>:<span className="muted">Нет результата</span>}</td>
            <td><span className={'state '+c.status}>{statuses[c.status]}</span>{c.decision&&<small>{decisions[c.decision]}</small>}</td><td className="muted">{date(c.created_at)}</td><td><ChevronRight size={17}/></td>
          </tr>)}</tbody></table></div>:<div className="empty"><FileSearch size={32}/><h3>{cases.length?'Ничего не найдено':'Здесь появятся ваши случаи'}</h3><p>{cases.length?'Измените поиск или фильтр.':'Создайте анализ или откройте один из трех сценариев выше.'}</p></div>}
        </section>
        <p className="footnote"><ShieldCheck size={15}/>Система выявляет признаки для ручной проверки. Она не выносит юридических заключений.</p>
      </>}
      {page==='case'&&(!current?<div className="empty"><LoaderCircle className="spin"/>Загрузка случая…</div>:<>
        <button className="back" onClick={()=>{setPage('queue');setCurrentId(undefined);void reload()}}><ArrowLeft size={16}/>К очереди</button>
        <div className="case-heading"><div><div className="eyebrow">{modes[current.mode]} · {current.id.slice(0,8)}</div><h1>{current.title}</h1><p>{date(current.created_at)} · {current.materials.length} материалов · {statuses[current.status]}</p></div><div className="actions">
          <button disabled={!!active||current.mode==='replay'} onClick={()=>{setAdding(true)}}><Plus size={16}/>Материал</button>
          <button disabled={!!busy||current.mode==='replay'} onClick={()=>void run('retry',async()=>{await post('/cases/'+current.id+(active?'/cancel':'/retry'))})}>{active?'Отменить':'Повторить анализ'}</button>
          <a className="primary button" href={'/api/cases/'+current.id+'/export'}><Download size={16}/>Экспорт</a>
        </div></div>
        {(current.mode==='synthetic'||current.mode==='replay')&&<div className="alert"><Layers size={17}/>{current.mode==='replay'?'ПОВТОР: сохраненный анализ. Новых запросов к OCR, модели и сети нет.':'Синтетический стенд. Все публикации, адреса и страницы созданы для демонстрации.'}</div>}
        <div className="pipeline" aria-label="Этапы анализа">{Object.entries(current.stages).map(([s,v],i)=><div key={s} className={v}><span>{v==='completed'?<Check size={12}/>:i+1}</span>{stageNames[s]}<small>{statuses[v]}</small></div>)}</div>
        <div className="case-grid"><section className="case-content">
          <div className="tabs" role="tablist">{[['materials','Материалы'],['route','Маршрут'],['graph','Граф связей']].map(([id,title])=><button key={id} role="tab" aria-selected={tab===id} onClick={()=>setTab(id)} className={tab===id?'selected':''}>{title}</button>)}</div>
          {tab==='materials'&&current.materials.map((m,i)=><article className="material panel" key={m.id}>
            <div className="panel-heading"><h2><FileText size={17}/>Материал {i+1}</h2><span className="tag">{m.source}</span></div>
            <p className="small muted">Источник заявлен при импорте; авторство не проверено.{m.published_at?' Опубликован: '+date(m.published_at):''}</p>
            {m.text&&<div className="source-text"><Highlight text={m.text} quotes={(current.claims||[]).filter(c=>c.source_id===m.id).map(c=>c.quote)}/></div>}
            {m.url&&<div className="url-text">{m.url}</div>}
            {m.image_id&&<figure className="original-image"><img src={'/api/images/'+m.image_id} alt={'Оригинальное изображение материала '+(i+1)}/><figcaption>Оригинал · OCR не исправляет URL или коды автоматически</figcaption></figure>}
            {m.ocr&&<details open><summary>Распознанные строки · {m.ocr.width} × {m.ocr.height}</summary><div className="ocr-lines">{m.ocr.lines.map((l,j)=><button key={j} title={l.warnings?.join('; ')} onClick={()=>setEvidenceIds([l.evidence_id])}><span>{l.text}{l.uncertain&&<small className="warning-text">Проверьте по оригиналу{l.warnings?.length?': '+l.warnings.join('; '):''}</small>}</span><small>{Math.round(l.confidence*100)}% {l.uncertain?'⚠':''}</small></button>)}</div></details>}
          </article>)}
          {tab==='route'&&<section className="panel"><div className="panel-heading"><h2>Проверенные переходы</h2><span className="tag">{current.trace.observations.length} наблюдений</span></div>
            {!current.trace.observations.length&&<div className="empty"><GitBranch/><p>Нет проверенных переходов. Добавьте URL или дождитесь анализа.</p></div>}
            <div className="route-list">{current.trace.observations.map((o,i)=><article key={o.id} className={o.stop?'route-stop':''}><div className="route-number">{i+1}</div><div><div className="route-status"><span className="tag">{o.status_code?'HTTP '+o.status_code:'Разрыв'}</span><small>{methods[o.method]}</small></div><strong className="url-text">{o.url}</strong>{o.location&&<p><ArrowDown size={14}/> {o.location}</p>}{o.stop&&<p className="warning-text">{o.stop}</p>}{o.text&&<p>{o.text.slice(0,230)}</p>}<button className="text-button" onClick={()=>setEvidenceIds([o.evidence_id])}>Открыть наблюдение <ArrowUpRight size={14}/></button></div></article>)}</div>
            <p className="muted small">HTTP-редирект и ссылка на странице — разные наблюдения. Непроверенный участок остается разрывом.</p>
          </section>}
          {tab==='graph'&&<Graph data={current.graph} onSelect={setEvidenceIds} onOpen={open} caseId={current.id}/>}
          <details className="panel limitations"><summary>Ограничения анализа ({current.limitations.length})</summary><ul>{current.limitations.map((l,i)=><li key={i}>{l}</li>)}</ul></details>
        </section><aside className="analysis-aside">
          <section className="panel priority"><div className="eyebrow">ПРИОРИТЕТ ПРОВЕРКИ</div>{current.sufficient_data===false?<><h3>Недостаточно данных</h3><p>Число обнаруженных признаков не позволяет оценить приоритет. Проверьте разрывы и ограничения.</p></>:current.score?<><div className="score-number">{current.score.value}<span>/100</span></div><span className={'risk '+current.score.level}>{levels[current.score.level]}</span></>:<h3>Нет результата</h3>}<p>Прозрачный индекс, не вероятность нарушения.</p>
            <div className="reason-list">{current.score?.contributions.map(c=><button key={c.key} onClick={()=>setEvidenceIds(c.evidence_ids)}><span>{c.title}</span><b>{c.weight>0?'+':''}{c.weight}</b></button>)}</div>
            <div className="provider"><span className="status-dot"/>{methods[current.provider||'local_rule']}<small>{current.context?.language.toUpperCase()} · {contexts[current.context?.context||'']||current.context?.context}</small></div>
            {current.context?.contradictions.map(c=><p className="warning-text" key={c}>{c}</p>)}
          </section>
          <Decision key={current.id} current={current} onSave={async(d,c)=>{await post('/cases/'+current.id+'/decision',{decision:d,comment:c});setCurrent(await api<Case>('/cases/'+current.id));await reload()}} onError={setError}/>
        </aside></div>
      </>)}
      {page==='evaluation'&&<EvaluationView data={evalData}/>}
      </main>
    </div>
    {(create||adding)&&<CreateDialog adding={adding} health={health} busy={!!busy} close={()=>{setCreate(false);setAdding(false)}} onSubmit={(data)=>void run('create',async()=>{
      const d=adding&&current?await post<{id:string}>('/cases/'+current.id+'/materials',data.materials[0]):await post<{id:string}>('/cases',data)
      setCreate(false);setAdding(false);open(d.id);await reload()
    })} onError={setError}/>}
    {!!evidenceIds.length&&<div className="drawer-scrim" onClick={()=>setEvidenceIds([])}><aside ref={drawerRef} className="evidence-drawer" aria-label="Источник связи" role="dialog" aria-modal="true" onClick={e=>e.stopPropagation()}>
      <div className="panel-heading"><div><div className="eyebrow">ПРОВЕРЯЕМАЯ СВЯЗЬ</div><h2>Источник вывода</h2></div><button autoFocus aria-label="Закрыть источник" onClick={()=>setEvidenceIds([])}><X size={20}/></button></div>
      {selected.length?selected.map(e=><article key={e.id} className="evidence-item"><span className="tag">{methods[e.method]||e.method}</span><blockquote>{e.quote||'Нет доступного текста'}</blockquote><dl><dt>Источник</dt><dd>{e.source_id}</dd><dt>Наблюдение</dt><dd>{date(e.at)} · UTC+5</dd>{e.confidence!==undefined&&<><dt>Оценка OCR</dt><dd>{Math.round(e.confidence*100)}% — не оценка истинности</dd></>}</dl>{e.note&&<p>{e.note}</p>}{e.polygon&&<small>Координаты: {JSON.stringify(e.polygon)}</small>}{e.case_id&&<button onClick={()=>{open(e.case_id!);setEvidenceIds([])}}>Открыть связанный случай <ArrowUpRight size={15}/></button>}</article>):<p>Источник еще не сохранен. Дождитесь завершения анализа.</p>}
      <p className="footnote">Наблюдение подтверждает сохраненный фрагмент. Вывод о продвижении требует проверки аналитиком.</p>
    </aside></div>}
  </div>
}

function CreateDialog({adding,health,busy,close,onSubmit,onError}:{adding:boolean;health?:Health;busy:boolean;close:()=>void;onSubmit:(d:{title:string;mode:string;materials:{text:string;url:string;source:string;image_id:string|null}[]})=>void;onError:(s:string)=>void}){
  const [text,setText]=useState(''),[url,setUrl]=useState(''),[title,setTitle]=useState(''),[source,setSource]=useState('')
  const [mode,setMode]=useState('local'),[imageId,setImageId]=useState<string|null>(null),[filename,setFilename]=useState(''),[uploading,setUploading]=useState(false)
  const ref=useRef<HTMLDivElement>(null)
  useEffect(()=>{const handler=(e:KeyboardEvent)=>{if(e.key==='Escape')close();if(e.key==='Tab'){
    const els=ref.current?.querySelectorAll<HTMLElement>('button:not(:disabled),input,textarea,select')
    if(!els?.length)return
    if(e.shiftKey&&document.activeElement===els[0]){e.preventDefault();els[els.length-1].focus()}
    else if(!e.shiftKey&&document.activeElement===els[els.length-1]){e.preventDefault();els[0].focus()}
  }};document.addEventListener('keydown',handler);return()=>document.removeEventListener('keydown',handler)},[close])
  const submit=(e:FormEvent)=>{e.preventDefault();onSubmit({title:title||'Новый материал',mode,materials:[{text,url,source:source||'Не указан',image_id:imageId}]})}
  return <div className="modal-scrim"><div className="modal" role="dialog" aria-modal="true" aria-labelledby="create-title" ref={ref}><div className="panel-heading"><div><div className="eyebrow">НОВЫЙ ИСТОЧНИК ДЛЯ ПРОВЕРКИ</div><h2 id="create-title">{adding?'Добавить материал':'Создать анализ'}</h2></div><button aria-label="Закрыть форму" onClick={close}><X size={20}/></button></div>
    <form onSubmit={submit}>
      {!adding&&<label>Название случая<input autoFocus value={title} maxLength={180} onChange={e=>setTitle(e.target.value)} placeholder="Например, публикация с предложением бонуса"/></label>}
      <label>Текст публикации<textarea autoFocus={adding} value={text} maxLength={20000} onChange={e=>setText(e.target.value)} placeholder="Вставьте исходный текст на русском или казахском…" rows={5}/></label>
      <div className="form-grid"><label>URL<input value={url} maxLength={2048} onChange={e=>setUrl(e.target.value)} placeholder="https://…"/></label><label>Заявленный источник<input value={source} maxLength={160} onChange={e=>setSource(e.target.value)} placeholder="@аккаунт или источник"/></label></div>
      <label className="upload-box"><ImagePlus size={25}/><strong>{uploading?'Загрузка…':filename||'Добавить изображение'}</strong><small>PNG, JPEG, WebP · до 8 MiB · до 12 Мп</small><input aria-label="Загрузить изображение" type="file" accept="image/png,image/jpeg,image/webp" onChange={async e=>{
        const f=e.target.files?.[0];if(!f)return;setUploading(true)
        try{const body=new FormData();body.append('file',f);const r=await api<{image_id:string}>('/uploads',{method:'POST',body});setImageId(r.image_id);setFilename(f.name)}catch(err){onError(String(err))}finally{setUploading(false)}
      }}/></label>
      {!adding&&<label>Режим анализа<select value={mode} onChange={e=>setMode(e.target.value)}><option value="local">Локальный · OCR и правила</option><option value="synthetic">Синтетический стенд · адреса .test</option><option value="cloud">Облачный контекст · Gemini</option></select></label>}
      <p className="small muted">{mode==='cloud'?(health?.provider_available?'Материал и изображение будут переданы настроенному Gemini API.':'Ключ не настроен. Анализ продолжится локальными правилами с отметкой ограничения.'):'Настоящий OCR и локальные правила. Понимание сложного контекста ограничено.'}</p>
      <div className="modal-actions"><button type="button" onClick={close}>Отмена</button><button className="primary" type="submit" disabled={busy||uploading||!(text.trim()||url.trim()||imageId)}>{busy?<LoaderCircle className="spin" size={17}/>:<FileSearch size={17}/>}Начать анализ</button></div>
    </form>
  </div></div>
}

function Decision({current,onSave,onError}:{current:Case;onSave:(d:string,c:string)=>Promise<void>;onError:(s:string)=>void}){
  const [decision,setDecision]=useState(current.decisions.at(-1)?.decision||'needs_data'),[comment,setComment]=useState(''),[saving,setSaving]=useState(false)
  return <section className="panel decision"><h2>Решение аналитика</h2><p className="small muted">Сохраняется отдельно от автоматического результата.</p><label>Оценка<select value={decision} onChange={e=>setDecision(e.target.value)}>{Object.entries(decisions).map(([v,t])=><option key={v} value={v}>{t}</option>)}</select></label><label>Комментарий<textarea rows={3} value={comment} maxLength={2000} onChange={e=>setComment(e.target.value)} placeholder="Основания решения или недостающие данные"/></label><button className="primary full" disabled={saving} onClick={async()=>{setSaving(true);try{await onSave(decision,comment);setComment('')}catch(e){onError(String(e))}finally{setSaving(false)}}}><Check size={16}/>{saving?'Сохранение…':'Сохранить решение'}</button>
    {current.decisions.length>0&&<div className="decision-history"><h3>История проверки</h3>{[...current.decisions].reverse().map(d=><article key={d.id}><strong>{decisions[d.decision]}</strong><small>{date(d.at)}</small>{d.comment&&<p>{d.comment}</p>}</article>)}</div>}
  </section>
}

function Graph({data,onSelect,onOpen,caseId}:{data:GraphData;onSelect:(ids:string[])=>void;onOpen:(id:string)=>void;caseId:string}){
  const container=useRef<HTMLDivElement>(null),cy=useRef<cytoscape.Core|null>(null)
  const graphKey=JSON.stringify({nodes:data.nodes,edges:data.edges})
  const [filter,setFilter]=useState('all'),[focus,setFocus]=useState<string>()
  const edges=data.edges.filter(e=>filter==='all'||e.type===filter)
  const selectRef=useRef(onSelect)
  useEffect(()=>{selectRef.current=onSelect},[onSelect])
  useEffect(()=>{
    if(!container.current)return
    const stableData=JSON.parse(graphKey) as GraphData
    const shown=stableData.edges.filter(e=>filter==='all'||e.type===filter)
    const ids=new Set(shown.flatMap(e=>[e.source,e.target]))
    const nodes=stableData.nodes.filter(n=>ids.has(n.id))
    const instance=cytoscape({container:container.current,elements:[...nodes.map(n=>({data:{...n,label:n.label.length>40?n.label.slice(0,37)+'…':n.label}})),
      ...shown.map(e=>({data:{...e,label:edgeNames[e.type]}}))],
      layout:{name:'breadthfirst',directed:true,padding:40,spacingFactor:1.25},
      style:[
        {selector:'node',style:{'background-color':'#274c48','border-color':'#62c4b4','border-width':1,'label':'data(label)','color':'#ccd9d7','font-size':10,'text-wrap':'wrap','text-max-width':'130px','text-valign':'bottom','text-margin-y':8,'width':28,'height':28}},
        {selector:'node[type="material"]',style:{'shape':'round-rectangle','background-color':'#448f83','width':40,'height':32}},
        {selector:'node[type="identifier"]',style:{'shape':'diamond','background-color':'#bda26b'}},
        {selector:'node[?stopped]',style:{'border-color':'#e7a578','background-color':'#613b32'}},
        {selector:'edge',style:{'width':1.4,'line-color':'#4d6663','target-arrow-color':'#4d6663','target-arrow-shape':'triangle','curve-style':'bezier','label':'data(label)','font-size':8,'color':'#94aaa6','text-rotation':'autorotate','text-background-color':'#151f21','text-background-opacity':1,'text-background-padding':'3px'}},
        {selector:'edge[status="inferred"]',style:{'line-style':'dashed','line-color':'#baa36d'}},
        {selector:':selected',style:{'border-width':3,'border-color':'#ecfbf7','line-color':'#93f0da','target-arrow-color':'#93f0da'}},
        {selector:'.dim',style:{'opacity':.12}},
      ],minZoom:.25,maxZoom:2.5,wheelSensitivity:.15})
    instance.on('tap','node,edge',e=>{selectRef.current(e.target.data('evidence_ids')||[]);setFocus(e.target.id())})
    cy.current=instance
    return()=>{instance.destroy();cy.current=null}
  },[graphKey,filter])
  return <section className="panel graph-panel"><div className="panel-heading"><h2>Граф источников</h2><span className="tag">{data.nodes.length} узлов · {data.edges.length} связей</span></div>
    <div className="graph-tools"><select aria-label="Тип связи" value={filter} onChange={e=>setFilter(e.target.value)}><option value="all">Все связи</option>{[...new Set(data.edges.map(e=>e.type))].map(t=><option key={t} value={t}>{edgeNames[t]}</option>)}</select><button onClick={()=>{setFilter('all');cy.current?.elements().removeClass('dim');cy.current?.fit(undefined,30)}}>Весь граф</button><button disabled={!focus} onClick={()=>{const c=cy.current;if(!c||!focus)return;const n=c.getElementById(focus);const roots=n.isEdge()?n.connectedNodes():n;const route=n.union(roots).union(roots.predecessors()).union(roots.successors());c.elements().addClass('dim');route.removeClass('dim');c.fit(route,50)}}>Фокус</button></div>
    <div className="graph-canvas" ref={container} aria-label="Интерактивный граф связей"/>
    <p className="small muted">Сплошная стрелка — наблюдение. Пунктир — предполагаемая связь по совпадению. Выберите стрелку или строку ниже.</p>
    <div className="edge-list">{edges.map(e=><button key={e.id} onClick={()=>{setFocus(e.id);onSelect(e.evidence_ids)}}><GitBranch size={14}/><span>{edgeNames[e.type]}<small>{data.nodes.find(n=>n.id===e.target)?.label}</small></span><ArrowUpRight size={14}/></button>)}</div>
    {data.nodes.filter(n=>n.case_id&&n.case_id!==caseId).map(n=><button className="related-case" key={n.id} onClick={()=>onOpen(n.case_id!)}>Связанный случай: {n.label}<ArrowUpRight size={15}/></button>)}
    <p className="small muted">{data.limitation}</p>
  </section>
}

function EvaluationView({data}:{data?:Evaluation}){
  return <><div className="page-heading"><div><div className="eyebrow">ПРОВЕРЯЕМОЕ КАЧЕСТВО</div><h1>Измерения, а не обещания.</h1><p>Одинаковые входные случаи, фиксированные пороги и полный учет ошибок.</p></div></div>
    {!data?<div className="empty"><LoaderCircle className="spin"/>Загрузка результатов…</div>:!data.available?<div className="empty"><SlidersHorizontal/><h2>Результатов пока нет</h2><p>{data.message}</p></div>:<>
      <div className="alert"><CircleHelp size={18}/>Синтетический тест: {data.test_count} случаев, {data.image_count} изображений. Это не оценка точности на реальных соцсетях.</div>
      <div className="section-label"><h2>Сравнение вариантов</h2><span>{data.dataset_version} · порог 65</span></div>
      <div className="table-wrap panel"><table className="metrics"><thead><tr><th>ВАРИАНТ</th><th>PRECISION</th><th>RECALL</th><th>F1</th><th>FPR</th><th>ПОКРЫТИЕ</th></tr></thead><tbody>{Object.entries(data.variants||{}).map(([name,m])=><tr key={name}><td><strong>{{baseline:'Ключевые слова',ocr:'Текст + OCR',full:'Полный процесс'}[name]||name}</strong><small>N={m.n}; TP {m.tp} · FP {m.fp} · TN {m.tn} · FN {m.fn}</small></td><td>{pct(m.precision)}<small>95% ДИ {m.precision_ci.map(pct).join('–')}</small></td><td>{pct(m.recall)}</td><td>{pct(m.f1)}</td><td>{pct(m.fpr)}<small>95% ДИ {m.fpr_ci.map(pct).join('–')}</small></td><td>{pct(m.coverage)}<small>Без данных: {m.insufficient}</small></td></tr>)}</tbody></table></div>
      <div className="evaluation-grid"><section className="panel"><h2>Задержка</h2><p className="muted small">CPU, модель загружена. Кэш содержимого OCR выключен в обоих вариантах.</p>{Object.entries(data.variants||{}).map(([v,m])=><div className="metric-row" key={v}><span>{v}</span><strong>p50 {(m.p50_ms/1000).toFixed(2)} с</strong><span>p95 {(m.p95_ms/1000).toFixed(2)} с</span></div>)}</section><section className="panel"><h2>Как читать результаты</h2><ul>{data.limitations?.map((l,i)=><li key={i}>{l}</li>)}</ul></section></div>
      <section className="panel"><h2>Срезы полного процесса</h2><div className="table-wrap"><table><thead><tr><th>СРЕЗ</th><th>N</th><th>PRECISION</th><th>RECALL</th><th>FPR</th></tr></thead><tbody>{Object.entries(data.slices||{}).map(([s,m])=><tr key={s}><td>{s}</td><td>{m.n}</td><td>{pct(m.precision)}</td><td>{pct(m.recall)}</td><td>{pct(m.fpr)}</td></tr>)}</tbody></table></div></section>
      <section className="panel"><h2>Ошибки на зафиксированном тесте</h2>{data.errors?.length?data.errors.map(e=><article className="error-example" key={e.id}><span className="tag">{e.truth?'Пропуск':'Ложное срабатывание'}</span><p>{e.title}</p><small>{e.id}</small></article>):<p className="muted">Ошибок по выбранному порогу не обнаружено. Малый синтетический набор ограничивает этот вывод.</p>}</section>
    </>}
  </>
}
