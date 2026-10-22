import { useRef, useState } from 'react'
import { ArrowRight, CheckCheck, ChevronRight, FileInput, FlaskConical, Plus, Search, X } from 'lucide-react'
import type { Demo, Summary } from '../types'
import { date, decisions, isActive, modes } from '../lib'
import { Empty, PriorityBadge, Status } from './UI'

export default function QueueView({ cases, demos, busy, onCreate, onOpen, onDemo, onImport }: {
  cases: Summary[]; demos: Demo[]; busy: boolean; onCreate: () => void; onOpen: (id: string) => void;
  onDemo: (id: string, replay?: boolean) => void; onImport: (file: File) => void;
}) {
  const [query, setQuery] = useState(''), [filter, setFilter] = useState('all'), [priority, setPriority] = useState('all'), [sort, setSort] = useState('newest')
  const fileRef = useRef<HTMLInputElement>(null)
  const unreviewed = cases.filter(c => !c.decision).length
  const processing = cases.filter(c => isActive(c.status)).length
  const missing = cases.filter(c => c.sufficient_data === false).length
  const shown = cases.filter(c => (c.title + ' ' + c.id).toLowerCase().includes(query.toLowerCase().trim())
    && (priority === 'all' || (c.sufficient_data !== false && c.score?.level === priority))
    && (filter === 'all' || filter === 'unreviewed' && !c.decision || filter === 'active' && isActive(c.status) || filter === 'missing' && c.sufficient_data === false))
    .sort((a, b) => sort === 'priority' ? (b.sufficient_data === false ? -1 : b.score?.value ?? -1) - (a.sufficient_data === false ? -1 : a.score?.value ?? -1) || b.created_at.localeCompare(a.created_at) : b.created_at.localeCompare(a.created_at))
  const reset = () => { setQuery(''); setFilter('all'); setPriority('all') }
  return <>
    <header className="page-heading"><div><div className="eyebrow">SAFETRACE KZ · ТРЕК «СКРЫТАЯ ИГРА»</div><h1>Очередь проверки <span className="heading-count">{cases.length}</span></h1><p>Находим признаки скрытого продвижения азартных игр.</p></div><button className="primary" onClick={onCreate}><Plus size={19} />Проверить сообщение</button></header>
    <section className="message-intro" aria-label="Как проверить сообщение"><strong>Пришло сообщение в WhatsApp или другом мессенджере?</strong><p>Вставьте его текст, ссылку или загрузите скриншот. Получите признаки, доступный маршрут и основания для ручной проверки.</p><small>Текст → признаки · скриншот → OCR · ссылка → проверка доступных переходов. Проверка всех видов мошенничества не входит в этот трек.</small></section>
    <details className="demo-section" open={!cases.length}>
      <summary><FlaskConical size={19} /><span>Безопасный демонстрационный стенд<small>Три сценария: маршрут, совпадение и предупреждение</small></span><span className="badge">3 сценария</span></summary>
      <div className="demo-list">{demos.map((d, i) => <article key={d.id}><span className="demo-number">0{i + 1}</span><div><h3>{d.title}</h3><p>{d.subtitle}</p></div><button disabled={busy} onClick={() => onDemo(d.id)}>Проанализировать <ArrowRight size={17} /></button><button disabled={busy} className="quiet" onClick={() => onDemo(d.id, true)}>Сохраненный повтор</button></article>)}</div>
      <p className="field-hint">Публикации и страницы созданы для демонстрации. Повтор открывает сохраненный результат без нового анализа.</p>
    </details>
    <section className="queue-workspace" aria-label="Случаи для проверки">
      <div className="queue-filters" aria-label="Состояние проверки">
        {[['all', 'Все случаи', cases.length], ['unreviewed', 'Без решения', unreviewed], ['active', 'В обработке', processing], ['missing', 'Недостаточно данных', missing]].map(([value, label, count]) =>
          <button key={value} aria-pressed={filter === value} className={filter === value ? 'selected' : ''} onClick={() => setFilter(String(value))}>{label}<span>{count}</span></button>)}
      </div>
      <div className="table-tools">
        <div className="search"><Search size={18} /><input aria-label="Поиск случаев" placeholder="Поиск по названию или ID" value={query} onChange={e => setQuery(e.target.value)} />{query && <button className="icon-button" aria-label="Очистить поиск" onClick={() => setQuery('')}><X size={16} /></button>}</div>
        <select aria-label="Фильтр приоритета" value={priority} onChange={e => setPriority(e.target.value)}><option value="all">Все приоритеты</option><option value="high">Высокий</option><option value="medium">Средний</option><option value="low">Низкий</option></select>
        <select aria-label="Сортировка случаев" value={sort} onChange={e => setSort(e.target.value)}><option value="newest">Сначала новые</option><option value="priority">По приоритету</option></select>
        <button disabled={busy} onClick={() => fileRef.current?.click()}><FileInput size={17} />Импорт JSONL</button>
        <input ref={fileRef} hidden type="file" accept=".jsonl,.json" aria-label="Файл JSONL" onChange={e => { const f = e.target.files?.[0]; if (f) onImport(f); e.target.value = '' }} />
      </div>
      {shown.length ? <div className="table-wrap queue-table"><table><thead><tr><th>Случай / источник анализа</th><th>Приоритет</th><th>Обработка / решение</th><th>Создан · UTC+5</th><th><span className="sr-only">Открыть</span></th></tr></thead><tbody>{shown.map(c =>
        <tr key={c.id}><td><button className="case-name" onClick={() => onOpen(c.id)}>{c.title}</button><div className="row-meta"><span className={'mode-dot ' + c.mode} />{modes[c.mode]}<span>·</span>{c.material_count} мат.</div></td>
          <td><PriorityBadge item={c} /></td><td><Status value={c.status} /><small>{c.decision ? decisions[c.decision] : 'Решение не принято'}</small></td><td className="date-cell">{date(c.created_at)}</td><td><button className="icon-button row-open" aria-label={'Открыть случай: ' + c.title} onClick={() => onOpen(c.id)}><ChevronRight size={19} /></button></td></tr>)}</tbody></table></div>
        : <Empty title={cases.length ? 'По этим условиям случаев нет' : 'Начните с первого материала'}><p>{cases.length ? 'Попробуйте другой запрос или сбросьте фильтры.' : 'Загрузите публикацию или попробуйте демонстрационный сценарий.'}</p><button onClick={cases.length ? reset : onCreate}>{cases.length ? 'Сбросить фильтры' : 'Создать анализ'}</button></Empty>}
      <footer className="table-footer"><span>Показано {shown.length} из {cases.length}</span><span><CheckCheck size={15} />Ручные решения сохраняются отдельно от анализа</span></footer>
    </section>
    <p className="footnote">SafeTrace выявляет признаки для ручной проверки. Индекс приоритета не является вероятностью нарушения.</p>
  </>
}
