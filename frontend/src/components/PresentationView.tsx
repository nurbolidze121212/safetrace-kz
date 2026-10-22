import { useState } from 'react'
import { ArrowRight, ArrowUpRight, FileText, GitBranch, Image, Info, LoaderCircle, Network, Search } from 'lucide-react'
import type { Case } from '../types'
import { analysisMessage } from '../analysis-message'
import { contexts, edgeNames, isActive, levels, methods, modes } from '../lib'
import { routeMaterialIds, routePaths } from '../routes'

function addressParts(address: string) {
  try { const url = new URL(address); return { host: url.hostname, rest: url.pathname + url.search + url.hash } }
  catch { return { host: address, rest: '' } }
}

export default function PresentationView({ current, onEvidence, onMaterial, onGraph, onRetry, busy }: {
  current: Case; onEvidence: (ids: string[]) => void; onMaterial: (id: string) => void; onGraph: () => void; onRetry: () => void; busy: boolean;
}) {
  const [chosenMaterial, setChosenMaterial] = useState('')
  const [chosenPath, setChosenPath] = useState('')
  const active = isActive(current.status)
  const material = current.materials.find(m => m.id === chosenMaterial) || current.materials.find(m => m.id === current.score?.material_id) || current.materials[0]
  const score = material?.score || (current.materials.length === 1 ? current.score : undefined)
  const uncertain = material?.url_reviews?.filter(review => review.needs_review && !review.selected_url) || []
  const sufficient = uncertain.length ? false : material?.sufficient_data ?? current.sufficient_data
  const message = analysisMessage({ ...current, score, sufficient_data: sufficient, materials: material ? [material] : [] })
  const paths = routePaths(current.trace).filter(path => material && routeMaterialIds(current, path.root).has(material.id))
  const pathKey = (index: number) => paths[index].steps.map(step => step.relation.evidence_id).join('|')
  const selectedIndex = Math.max(0, paths.findIndex((_, index) => pathKey(index) === chosenPath))
  const path = paths[selectedIndex]
  const noResult = active || ['error', 'cancelled'].includes(current.status) || !score
  const contributions = noResult ? [] : score.contributions
  return <div className="presentation-view">
    <div className="presentation-context"><span className={'mode-label ' + current.mode}>{modes[current.mode]}</span><span>{current.mode === 'synthetic' ? 'Собственные демонстрационные страницы, не реальные сайты' : current.mode === 'replay' ? 'Сохранённый повтор, без нового анализа' : 'Проверка скрытого продвижения азартных игр'}</span>{current.analysis_assisted && <strong>Адрес уточнён аналитиком</strong>}</div>
    {current.materials.length > 1 && <label className="presentation-picker">Материал для показа<select aria-label="Материал для показа" value={material?.id || ''} onChange={e => { setChosenMaterial(e.target.value); setChosenPath('') }}>{current.materials.map((m, index) => <option key={m.id} value={m.id}>{index + 1}. {m.source}{m.id === current.score?.material_id ? ' · определяет индекс случая' : ''}</option>)}</select></label>}
    <div className="presentation-overview">
      <section className="presentation-input" aria-label="Исходное сообщение для показа"><div className="presentation-label"><span>01</span><h2>{material?.image_id ? 'Что на изображении' : 'Что прислали'}</h2>{material?.image_id ? <Image size={18} /> : <FileText size={18} />}</div>
        {material?.image_id && <button className="presentation-image" onClick={() => onMaterial(material.id)} aria-label="Открыть оригинал изображения"><img src={'/api/images/' + material.image_id} alt="Исходное изображение сообщения" /></button>}
        {material?.text && <blockquote>{material.text}</blockquote>}
        {!material?.text && !material?.image_id && <code className="presentation-url">{material?.url || 'Исходный материал отсутствует'}</code>}
        {material && <button className="text-button" onClick={() => onMaterial(material.id)}>{material.image_id ? 'Оригинал и распознанный текст' : 'Полный исходный материал'}<ArrowUpRight size={15} /></button>}
      </section>
      <section className={'presentation-verdict ' + message.tone} aria-label="Приоритет и причины для показа"><div className="presentation-label"><span>02</span><h2>{active ? 'Проверяем материал' : 'Почему такой приоритет'}</h2></div>
        <div className="presentation-score"><strong className={noResult || sufficient === false ? 'unknown' : score.level}>{noResult || sufficient === false ? '—' : score.value}</strong><div><b>{noResult ? 'Результат ещё не готов' : sufficient === false ? 'Недостаточно данных' : (levels[score.level] || 'Не определён') + ' приоритет'}</b><small>Индекс из 100 для ручной проверки · не вероятность</small></div></div>
        <p className="presentation-message" aria-live="polite">{active && <LoaderCircle size={17} className="spin" />}{message.title}</p>
        {contributions.length > 0 && <div className="presentation-reasons">{contributions.map(reason => <button key={reason.key} disabled={!reason.evidence_ids.length} onClick={() => onEvidence(reason.evidence_ids)}><span>{reason.title}</span><b>{reason.weight > 0 ? '+' : ''}{reason.weight}</b><ArrowUpRight size={14} /></button>)}</div>}
        {(!contributions.length || message.tone === 'neutral') && <p className="presentation-detail">{message.detail}</p>}
        {material?.context && !active && <small>Контекст: {contexts[material.context.context] || material.context.context}</small>}
        {(current.status === 'error' || current.status === 'cancelled') && <button onClick={onRetry} disabled={busy || current.mode === 'replay'}>Повторить анализ</button>}
      </section>
    </div>
    <section className="presentation-map" aria-label="Наглядная карта маршрута"><header><div className="presentation-label"><span>03</span><h2>Куда ведёт ссылка</h2></div><button className="text-button" onClick={onGraph}><Network size={17} />Подробный граф</button></header>
      {paths.length > 1 && <label className="presentation-picker">Маршрут этого материала<select aria-label="Маршрут для показа" value={selectedIndex} onChange={e => setChosenPath(pathKey(Number(e.target.value)))}>{paths.map((p, index) => <option key={pathKey(index)} value={index}>{index + 1} из {paths.length} · {p.root} · {p.steps.length} шагов</option>)}</select></label>}
      {active ? <div className="presentation-empty"><LoaderCircle size={23} className="spin" /><div><strong>Маршрут появится после проверки переходов</strong><p>{message.detail}</p><progress max={100} value={current.progress} aria-label="Прогресс анализа" /></div></div> : !path ? <div className="presentation-empty"><Search size={23} /><div><strong>{uncertain.length ? 'Сначала нужно сверить адрес на изображении' : 'Проверенного маршрута пока нет'}</strong><p>{uncertain.length ? 'OCR прочитал адрес неоднозначно. Неподтверждённые переходы не добавляются на карту.' : material?.url || material?.text ? 'Добавьте данные или откройте ограничения. Отсутствие маршрута не означает безопасность ссылки.' : 'Для карты нужна ссылка из сообщения, изображения или QR-кода.'}</p>{uncertain.map(review => <code key={review.raw_url}>{review.raw_url}</code>)}{material && <button className="text-button" onClick={() => onMaterial(material.id)}>Открыть материал и ограничения<ArrowRight size={16} /></button>}</div></div> : <>
        <ol className="presentation-path">{path.steps.map((step, index) => {
          const o = step.observation
          const stopped = Boolean(o?.stop || step.cycle || !o)
          const parts = addressParts(step.relation.to)
          return <li key={step.relation.evidence_id + '-' + index} className={stopped ? 'stopped' : ''}>
            <div className="map-connection">{index > 0 ? <ArrowRight className="map-edge-arrow" size={17} /> : <GitBranch size={14} />}<span>{edgeNames[step.relation.type] || step.relation.type}</span></div>
            <button className="map-node" onClick={() => onEvidence([step.relation.evidence_id, ...(o ? [o.evidence_id] : [])])} aria-label={'Открыть шаг ' + (index + 1) + ': ' + parts.host}>
              <div className="map-node-top"><span className="map-step">{String(index + 1).padStart(2, '0')}</span><span className={'badge ' + (stopped ? 'insufficient' : 'observed')}>{stopped ? 'Разрыв маршрута' : o?.status_code ? 'HTTP ' + o.status_code : 'Ответ не сохранён'}</span></div>
              <strong>{parts.host}</strong><code>{parts.rest}</code>
              {stopped ? <p className="warning-text">{o?.stop || (step.cycle ? 'Цикл переходов' : 'Нет сохранённого наблюдения')}</p> : o?.text ? <p className="map-excerpt">{o.text}</p> : <p className="map-excerpt">{index < path.steps.length - 1 ? 'Сохранена связь со следующим адресом' : 'Текст страницы не извлечён'}</p>}
              <small>{o ? methods[o.method] || o.method : 'Нет наблюдения'}</small><span className="map-node-action">Посмотреть источник<ArrowUpRight size={14} /></span>
            </button>
            {index === path.steps.length - 1 && <small className="map-terminal">{stopped ? 'Продолжение не подтверждено' : 'Последний проверенный адрес'}</small>}
          </li>
        })}</ol>
        <p className="presentation-map-note"><Info size={14} />Стрелки построены по сохранённым связям. HTTP-переход и ссылка на странице — разные наблюдения.</p>
      </>}
    </section>
    {current.limitations.length > 0 && <details className="presentation-limits"><summary>Границы этого анализа · {current.limitations.length}</summary><ul>{current.limitations.map((limit,index) => <li key={index}>{limit}</li>)}</ul></details>}
  </div>
}
