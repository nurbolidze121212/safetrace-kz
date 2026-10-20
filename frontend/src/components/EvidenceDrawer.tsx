import { ArrowRight, ExternalLink } from 'lucide-react'
import type { Case, Evidence, Material } from '../types'
import { date, methods } from '../lib'
import { Dialog, Empty } from './UI'
import { OriginalImage } from './MaterialsView'

export function evidenceMaterial(current: Case, evidence: Evidence): Material | undefined {
  return current.materials.find(m => m.id === evidence.material_id || m.id === evidence.source_id || m.ocr?.lines.some(line => line.evidence_id === evidence.id))
}
export default function EvidenceDrawer({ current, ids, close, onOriginal, onOpen }: { current: Case; ids: string[]; close: () => void; onOriginal: (materialId: string, evidenceId: string) => void; onOpen: (id: string) => void }) {
  const selected = current.graph.evidence.filter(e => ids.includes(e.id))
  return <Dialog title="Источник вывода" onClose={close} drawer>
    <p className="dialog-intro">Сохраненные фрагменты, на которых основана выбранная связь или причина приоритета.</p>
    {selected.length ? selected.map((e, i) => {
      const material = evidenceMaterial(current, e)
      return <article className="evidence-item" key={e.id}>
        <div className="evidence-heading"><span className="evidence-number">{String(i + 1).padStart(2, '0')}</span><span className="badge">{methods[e.method] || e.method}</span></div>
        {e.url && <div className="source-url"><span className="field-hint">Адрес источника</span><code>{e.url}</code></div>}
        <blockquote>{e.quote || 'Текст в этом наблюдении отсутствует.'}</blockquote>
        {material?.image_id && e.polygon && <OriginalImage material={material} selected={e.id} compact />}
        <dl><dt>Источник</dt><dd>{material?.source || e.source_id}</dd><dt>Наблюдение</dt><dd>{date(e.at)} · UTC+5</dd>{e.confidence !== undefined && <><dt>Оценка OCR</dt><dd>{Math.round(e.confidence * 100)}% — оценка распознавания</dd></>}</dl>
        {e.note && <p className="field-hint">{e.note}</p>}
        {material && <button onClick={() => onOriginal(material.id, e.id)}>Показать в оригинале <ArrowRight size={16} /></button>}
        {e.case_id && e.case_id !== current.id && <button onClick={() => onOpen(e.case_id!)}>Открыть связанный случай <ExternalLink size={16} /></button>}
        <details className="technical-details"><summary>Идентификатор и координаты</summary><code>{e.id}</code>{e.polygon && <pre>{JSON.stringify(e.polygon)}</pre>}</details>
      </article>
    }) : <Empty title="Источник пока недоступен"><p>Дождитесь завершения анализа или повторите его.</p></Empty>}
    <p className="footnote">Наблюдение подтверждает сохраненный фрагмент. Интерпретация требует проверки аналитиком.</p>
  </Dialog>
}
