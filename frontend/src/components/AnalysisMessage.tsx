import { ArrowRight, Info, LoaderCircle } from 'lucide-react'
import { useEffect, useRef } from 'react'
import type { Case } from '../types'
import { isActive } from '../lib'
import { analysisMessage } from '../analysis-message'

function focusView(view: string) {
  document.getElementById('tab-' + view)?.focus({ preventScroll: true })
  document.getElementById('panel-' + view)?.scrollIntoView({ block: 'start' })
}

export default function AnalysisMessage({ current, view, busy, onView, onRetry }: { current: Case; view: string; busy: boolean; onView: (view: string) => void; onRetry: () => void }) {
  const message = analysisMessage(current)
  const active = isActive(current.status)
  const pendingJump = useRef<string | null>(null)
  useEffect(() => {
    if (pendingJump.current === view) { focusView(view); pendingJump.current = null }
  }, [view])
  function openNext() {
    if (!message.action) return
    if (message.action === 'retry') { onRetry(); return }
    if (message.action === view) focusView(view)
    else { pendingJump.current = message.action; onView(message.action) }
  }
  return <section className={'analysis-message ' + message.tone} aria-label="Что означает результат">
    <div className="message-icon">{active ? <LoaderCircle className="spin" size={23} /> : <Info size={23} />}</div>
    <div><div className="eyebrow">{active ? 'ХОД ПРОВЕРКИ' : 'ПРОВЕРКА СКРЫТОГО ПРОДВИЖЕНИЯ'}</div>
      <h2 aria-live="polite">{message.title}</h2><p>{message.detail}</p>
      {message.action && <button className="text-button" disabled={busy || (message.action === 'retry' && current.mode === 'replay')} onClick={openNext}>{message.actionLabel}<ArrowRight size={17} /></button>}
      {!active && current.elapsed_ms != null && <small className="analysis-duration">Обработка: {(current.elapsed_ms / 1000).toLocaleString('ru-RU', { maximumFractionDigits: 1 })} с{current.mode === 'replay' ? ' · сохранённый запуск' : ''} · время ожидания в очереди не включено</small>}
    </div>
  </section>
}
