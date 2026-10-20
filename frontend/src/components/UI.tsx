import { useEffect, useRef } from 'react'
import type { ReactNode } from 'react'
import { AlertTriangle, Circle, CircleHelp, LoaderCircle, X } from 'lucide-react'
import type { Summary } from '../types'
import { levels, statuses } from '../lib'
import { sourceIntervals } from '../highlights'
import type { SourceClaim } from '../highlights'

export function PriorityBadge({ item }: { item: Pick<Summary, 'score' | 'sufficient_data'> }) {
  if (item.sufficient_data === false) return <span className="badge insufficient"><CircleHelp size={15} />Нет данных для оценки</span>
  if (!item.score) return <span className="muted">Еще не оценен</span>
  const Icon = item.score.level === 'high' ? AlertTriangle : Circle
  return <span className={'badge risk ' + item.score.level}><Icon size={14} />{levels[item.score.level]}<b>{item.score.value}</b></span>
}
export function Status({ value }: { value: string }) {
  return <span className={'state ' + value}>{value === 'running' ? <LoaderCircle size={13} className="spin" /> : <span className="state-dot" />}{statuses[value] || value}</span>
}
export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return <div className="empty"><CircleHelp size={28} /><h3>{title}</h3>{children}</div>
}
export function Loading({ children = 'Загрузка…' }: { children?: ReactNode }) {
  return <div className="loading" role="status"><LoaderCircle className="spin" size={22} />{children}</div>
}
export function Dialog({ title, children, onClose, drawer = false, busy = false }: { title: string; children: ReactNode; onClose: () => void; drawer?: boolean; busy?: boolean }) {
  const ref = useRef<HTMLDialogElement>(null)
  const previous = useRef<HTMLElement | null>(null)
  useEffect(() => {
    previous.current = document.activeElement as HTMLElement
    const dialog = ref.current
    dialog?.showModal()
    dialog?.querySelector<HTMLElement>('[data-autofocus]')?.focus()
    return () => { dialog?.close(); previous.current?.focus() }
  }, [])
  return <dialog className={drawer ? 'dialog drawer' : 'dialog'} ref={ref} aria-label={title} onCancel={e => { e.preventDefault(); if (!busy) onClose() }}>
    <header className="dialog-heading"><div><div className="eyebrow">SAFETRACE / РАБОЧАЯ СРЕДА</div><h2>{title}</h2></div><button type="button" className="icon-button" aria-label={drawer ? 'Закрыть источник' : 'Закрыть форму'} disabled={busy} onClick={onClose}><X size={21} /></button></header>
    {children}
  </dialog>
}
export function Highlight({ text, claims }: { text: string; claims: SourceClaim[] }) {
  const intervals = sourceIntervals(text, claims)
  let cursor = 0
  const result: ReactNode[] = []
  for (const [i, range] of intervals.entries()) {
    if (range.start < cursor) continue
    result.push(text.slice(cursor, range.start), <mark key={i}>{text.slice(range.start, range.end)}</mark>)
    cursor = range.end
  }
  result.push(text.slice(cursor))
  return <>{result}</>
}
