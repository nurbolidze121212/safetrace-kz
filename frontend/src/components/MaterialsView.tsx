import { useEffect, useRef, useState } from 'react'
import { ArrowUpRight, FileText, QrCode, ScanText, ZoomIn, ZoomOut } from 'lucide-react'
import type { Case, Material } from '../types'
import { contexts, date, isActive } from '../lib'
import { Empty, Highlight, PriorityBadge } from './UI'

export function OriginalImage({ material, selected, onSelect, compact = false }: { material: Material; selected?: string; onSelect?: (id: string) => void; compact?: boolean }) {
  const [zoom, setZoom] = useState(1)
  const [showBoxes, setShowBoxes] = useState(true)
  const dimensions = material.ocr || material.qr
  const imageRef = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const area = imageRef.current?.querySelector<SVGPolygonElement>('[data-selected="true"]')
    if (area && !compact) {
      area.scrollIntoView({ block: 'center', inline: 'nearest' })
      area.focus({ preventScroll: true })
    }
  }, [selected, zoom, compact])
  if (!material.image_id) return null
  return <div className={'image-viewer ' + (compact ? 'compact' : '')}>
    {!compact && <div className="viewer-tools"><span>Оригинальное изображение</span><div><button className="icon-button" aria-label="Уменьшить изображение" disabled={zoom <= 1} onClick={() => setZoom(Math.max(1, zoom - .5))}><ZoomOut size={17} /></button><button className="zoom-reset" onClick={() => setZoom(1)} aria-label="Вписать изображение">{zoom === 1 ? 'Вписать' : Math.round(zoom * 100) + '%'}</button><button className="icon-button" aria-label="Увеличить изображение" disabled={zoom >= 3} onClick={() => setZoom(Math.min(3, zoom + .5))}><ZoomIn size={17} /></button><button aria-pressed={showBoxes} aria-label="Области OCR и QR" className="quiet" onClick={() => setShowBoxes(!showBoxes)}>Области</button></div></div>}
    <div className="image-scroll" ref={imageRef}><div className="image-surface" style={{ width: zoom * 100 + '%' }}>
      <img src={'/api/images/' + material.image_id} alt={'Оригинал: ' + material.source} />
      {showBoxes && dimensions && <svg className="ocr-overlay" viewBox={'0 0 ' + dimensions.width + ' ' + dimensions.height} aria-label="Области распознанного текста и QR">
        {material.ocr?.lines.map((line, i) => <polygon key={line.evidence_id} points={line.polygon.map(p => p.join(',')).join(' ')} className={selected === line.evidence_id ? 'selected' : line.uncertain ? 'uncertain' : ''} data-selected={selected === line.evidence_id} role={onSelect ? 'button' : undefined} tabIndex={onSelect ? 0 : undefined} aria-label={'Строка ' + (i + 1) + ': ' + line.text} onClick={() => onSelect?.(line.evidence_id)} onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onSelect?.(line.evidence_id) } }} />)}
        {material.qr?.codes.map((code, i) => <polygon key={code.evidence_id} points={code.polygon.map(p => p.join(',')).join(' ')} className={selected === code.evidence_id ? 'selected' : 'qr-area'} data-selected={selected === code.evidence_id} role={onSelect ? 'button' : undefined} tabIndex={onSelect ? 0 : undefined} aria-label={'QR ' + (i + 1) + ': ' + code.text.slice(0,160)} onClick={() => onSelect?.(code.evidence_id)} onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onSelect?.(code.evidence_id) } }} />)}
      </svg>}
    </div></div>
    {!compact && <p className="field-hint">{dimensions ? dimensions.width + ' × ' + dimensions.height + ' px · Выберите строку или QR, чтобы увидеть область.' : 'Распознавание еще не получено. Оригинал сохранен.'}</p>}
  </div>
}

export default function MaterialsView({ current, materialId, selectedEvidence, onMaterial, onEvidence }: { current: Case; materialId: string; selectedEvidence?: string; onMaterial: (id: string) => void; onEvidence: (ids: string[]) => void }) {
  const material = current.materials.find(m => m.id === materialId) || current.materials[0]
  const [lineId, setLineId] = useState<string>()
  const selected = lineId || selectedEvidence
  if (!material) return <Empty title="Материалов пока нет" />
  const claims = (current.claims || []).filter(c => c.source_id === material.id)
  const quotes = claims.map(c => c.quote)
  return <section className="materials-workspace">
    <div className="material-switcher" aria-label="Выбор материала">{current.materials.map((m, i) => <button key={m.id} aria-pressed={material.id === m.id} className={material.id === m.id ? 'selected' : ''} onClick={() => { onMaterial(m.id); setLineId(undefined) }}><FileText size={16} /><span>Материал {i + 1}<small>{m.source}</small></span></button>)}</div>
    <div className="material-heading"><div><h2>{material.source}</h2><p>Источник заявлен при импорте; авторство не проверено.{material.published_at ? ' · ' + date(material.published_at) : ''}</p></div><span className="badge">{material.image_id ? 'Текст + изображение' : 'Текст / URL'}</span></div>
    {material.score && <div className="case-meta" aria-label="Оценка материала"><span>{isActive(current.status) ? 'Предыдущая оценка материала' : 'Оценка этого материала'}</span><PriorityBadge item={material} />{material.context && <span>Контекст: {contexts[material.context.context] || material.context.context}</span>}{current.score?.material_id === material.id && <span>Определяет индекс случая</span>}</div>}
    {material.context?.context === 'promotion' && <p className="field-hint">Рекламная лексика и призыв в материале сами по себе не подтверждают игровое назначение. Оно проверяется отдельно по маршруту.</p>}
    <div className={'material-columns ' + (material.image_id ? '' : 'text-only')}>
      <div className="original-column">
        {material.text && <section className="source-block"><div className="section-title"><FileText size={17} /><h3>Текст публикации</h3></div><div className="source-text"><Highlight text={material.text} claims={claims} /></div>{quotes.length > 0 && <p className="field-hint"><span className="highlight-key" />Выделены цитаты, подтвержденные в источнике</p>}</section>}
        {material.url && <div className="source-url"><span className="field-hint">Исходная ссылка</span><code>{material.url}</code></div>}
        <OriginalImage key={material.id} material={material} selected={selected} onSelect={setLineId} />
        {material.qr && <section className="qr-results"><div className="section-title"><QrCode size={18} /><h3>QR-коды</h3><span className="badge">{material.qr.codes.length}</span></div>
          {material.qr.codes.length ? <><p className="field-hint">Содержимое декодировано из изображения. HTTP/HTTPS-адреса проходят ту же проверку переходов, что и текстовые ссылки.</p>{material.qr.codes.map(code => <article className="qr-result" key={code.evidence_id}><code>{code.text}</code>{code.truncated && <p className="warning-text">Показаны первые 2048 символов; адрес не передается в проверку.</p>}{code.reason && <p className="warning-text">{code.reason}. Содержимое показано как текст.</p>}<button className="text-button" onClick={() => onEvidence([code.evidence_id])}>Источник QR <ArrowUpRight size={14} /></button></article>)}</> : <p className="field-hint">QR-коды не распознаны. Это не исключает мелкий или поврежденный код.</p>}
        </section>}
      </div>
      <div className="extracted-column">
        <div className="section-title"><ScanText size={18} /><h3>{material.image_id ? 'Распознанный текст' : 'Подтвержденные фрагменты'}</h3><span className="badge">{material.image_id ? material.ocr?.lines.length ?? 0 : quotes.length}</span></div>
        {material.image_id ? material.ocr?.lines.length ? <>
          <p className="field-hint">Оценка OCR относится к распознаванию символов. URL и коды не исправляются автоматически.</p>
          {material.ocr.raw_lines && <p className="field-hint">Соседние фрагменты объединены в строки. Исходные сегменты сохранены ниже.{material.ocr.rotation_ccw ? ' Для чтения применен поворот ' + material.ocr.rotation_ccw + '° против часовой стрелки; области показаны на оригинале.' : ''}</p>}
          <ol className="ocr-lines">{material.ocr.lines.map((line, i) => <li key={line.evidence_id} className={selected === line.evidence_id ? 'selected' : ''}>
            <button className="ocr-line" aria-pressed={selected === line.evidence_id} onClick={() => setLineId(line.evidence_id)}><span className="line-number">{String(i + 1).padStart(2, '0')}</span><span>{line.text}</span><span className={'confidence ' + (line.uncertain ? 'uncertain' : '')}>{Math.round(line.confidence * 100)}%</span></button>
            {line.uncertain && <p className="warning-text">Проверьте символы по оригиналу{line.warnings?.length ? ': ' + line.warnings.join('; ') : '.'}</p>}
            <button className="text-button line-evidence" onClick={() => onEvidence([line.evidence_id])}>Источник строки <ArrowUpRight size={14} /></button>
          </li>)}</ol>
          <details className="technical-details"><summary>Модель и исходные сегменты</summary><p>{material.ocr.model}</p><pre>{JSON.stringify(material.ocr.raw_lines || material.ocr.lines.map(l => ({ text: l.text, polygon: l.polygon })), null, 2)}</pre></details>
        </> : <Empty title="Распознанных строк пока нет"><p>Проверьте состояние этапа OCR и ограничения анализа.</p></Empty>
        : quotes.length ? <div className="claim-list">{(current.claims || []).filter(c => c.source_id === material.id).map(c => <button key={c.evidence_id} onClick={() => onEvidence([c.evidence_id])}><span>«{c.quote}»</span><ArrowUpRight size={16} /></button>)}</div> : <Empty title="Подтвержденных признаков нет"><p>Отсутствие признаков само по себе не гарантирует безопасность материала.</p></Empty>}
      </div>
    </div>
  </section>
}
