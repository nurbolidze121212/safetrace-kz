import { useState } from 'react'
import { ArrowUpRight, Check, Link2 } from 'lucide-react'
import type { Case, Material, URLCorrectionRequest, URLReview as Reading } from '../types'
import { date, errorMessage, isActive } from '../lib'

export default function URLReview({ current, material, onEvidence, onCorrect }: {
  current: Case; material: Material; onEvidence: (ids: string[]) => void;
  onCorrect: (value: URLCorrectionRequest) => Promise<void>;
}) {
  if (!material.url_reviews?.length) return null
  return <section className="url-review-panel" aria-label="Проверка OCR-адресов">
    <div className="section-title"><Link2 size={18} /><h3>Адреса на изображении</h3></div>
    <p className="field-hint">Сомнительный адрес не открывается до уточнения. Вариант распознавания — подсказка для сверки с оригиналом.</p>
    {material.url_reviews.map(reading => <AddressCard key={material.id + (current.analysis_id || '') + reading.raw_url}
      reading={reading} current={current} material={material} onEvidence={onEvidence} onCorrect={onCorrect} />)}
    {!!material.url_corrections?.length && <details className="technical-details"><summary>История уточнений адресов · {material.url_corrections.length}</summary>
      <ol className="url-correction-history">{material.url_corrections.map(change => <li key={change.id}>
        <time>{date(change.at)} · UTC+5</time><code>{change.original_url}</code><span>Уточнено как</span><code>{change.corrected_url}</code><p>{change.comment}</p>
      </li>)}</ol>
    </details>}
  </section>
}

function AddressCard({ reading, current, material, onEvidence, onCorrect }: {
  reading: Reading; current: Case; material: Material; onEvidence: (ids: string[]) => void;
  onCorrect: (value: URLCorrectionRequest) => Promise<void>;
}) {
  const [url, setUrl] = useState(reading.selected_url || reading.raw_url)
  const [comment, setComment] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const disabled = saving || isActive(current.status) || current.mode === 'replay' || !current.analysis_id
  return <article className={'url-review-card ' + (!reading.selected_url ? 'needs-review' : '')}>
    <strong>{reading.correction_id ? 'Уточнён аналитиком' : reading.needs_review ? 'Нужна сверка с оригиналом' : 'Извлечён из OCR'}</strong>
    <span className="field-hint">Первичное распознавание</span><code>{reading.raw_url}</code>
    {!!reading.reasons.length && <ul className="field-hint">{reading.reasons.map(reason => <li key={reason}>{reason}</li>)}</ul>}
    {reading.correction_id && <><span className="field-hint">Используется в новом анализе</span><code>{reading.selected_url}</code></>}
    <button className="text-button" onClick={() => onEvidence(reading.source_evidence_ids)}>Источник адреса <ArrowUpRight size={14} /></button>
    <details className="url-correction-form"><summary>{reading.correction_id ? 'Уточнить ещё раз' : 'Сверить и уточнить адрес'}</summary>
      <form onSubmit={async e => {
        e.preventDefault()
        if (disabled || !current.analysis_id) return
        setSaving(true); setError('')
        try { await onCorrect({ material_id: material.id, analysis_id: current.analysis_id, original_url: reading.raw_url, corrected_url: url, comment }) }
        catch (cause) { setError(errorMessage(cause)) }
        finally { setSaving(false) }
      }}>
        <fieldset disabled={disabled}>
          {!!reading.suggestions.length && <div className="url-suggestions"><p className="field-hint">Варианты для сверки — автоматически не использованы</p>{reading.suggestions.map(suggestion => <div key={suggestion.url}><code>{suggestion.url}</code><button type="button" className="quiet" onClick={() => setUrl(suggestion.url)}>Подставить вариант</button></div>)}</div>}
          <label>Уточнённый URL<input type="url" required maxLength={2048} value={url} onChange={e => setUrl(e.target.value)} spellCheck={false} autoComplete="off" /></label>
          <label>Что проверено на оригинале<textarea required minLength={3} maxLength={1000} rows={2} value={comment} onChange={e => setComment(e.target.value)} placeholder="Например: буква в имени узла и весь путь после косой черты" /></label>
        </fieldset>
        <p className="field-hint">Будет создан новый анализ с ручным уточнением. Оригинал, прежний OCR и автоматический результат сохранятся в истории.</p>
        {error && <p className="alert error" role="alert">{error}</p>}
        <button className="primary" type="submit" disabled={disabled || comment.trim().length < 3} aria-busy={saving}><Check size={16} />{saving ? 'Сохранение…' : 'Сохранить уточнение и повторить анализ'}</button>
      </form>
    </details>
  </article>
}
