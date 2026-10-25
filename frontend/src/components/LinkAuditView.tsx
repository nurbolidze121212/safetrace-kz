import { useEffect, useState } from 'react'
import { ArrowUpRight, Download, ShieldQuestion } from 'lucide-react'
import type { Case } from '../types'
import { api, date, errorMessage } from '../lib'
import { Loading } from './UI'

type Finding = { id: string; title: string; detail: string; quote: string; evidence_ids: string[]; url?: string; reference?: string }
type Audit = {
  schema: string; status: string; generated_at: string; source_analyzed_at?: string;
  coverage: { urls_checked: number; urls_available: number; observed_urls: number; held_ocr_urls: number; truncated: boolean };
  urls: { url: string; host: string; unicode_host: string; observed: boolean; brands: { name: string; status: string; source: string; checked_at: string; review_after: string }[] }[];
  findings: Finding[]; checks: { name: string; status: string; detail: string }[]; limitations: string[];
}
const checkNames: Record<string, string> = { checked: 'Выполнено', no_data: 'Нет данных', limited: 'Ограниченная проверка', unavailable: 'Недоступно', not_connected: 'Не подключено', not_implemented: 'Не реализовано', not_verified: 'Не подтверждено' }

export default function LinkAuditView({ current, onEvidence }: { current: Case; onEvidence: (ids: string[]) => void }) {
  const [result, setResult] = useState<Audit>(), [error, setError] = useState('')
  useEffect(() => {
    const controller = new AbortController()
    api<Audit>('/cases/' + current.id + '/link-audit', { signal: controller.signal })
      .then(value => { if (!controller.signal.aborted) setResult(value) })
      .catch(reason => { if (!controller.signal.aborted) setError(errorMessage(reason)) })
    return () => controller.abort()
  }, [current.id])
  if (error) return <div role="alert" className="alert error">{error} Перезагрузите страницу для повторной проверки.</div>
  if (!result) return <Loading>Разбираем сохранённые адреса…</Loading>
  return <section className="link-audit" aria-label="Дополнительные признаки угроз">
    <header><div><div className="eyebrow">ЭКСПЕРИМЕНТ · ВНЕ ТРЕКА 2</div><h2><ShieldQuestion size={22} />Другие признаки угроз</h2><p>Разбор адресов и сохранённого текста. Новые сайты не открываются; файлы не запускаются.</p></div><a className="button" href={'/api/cases/' + current.id + '/link-audit?download=true'} download><Download size={16} />Скачать JSON</a></header>
    <div className="audit-summary"><strong>{result.status === 'source_incomplete' ? 'Основной анализ ещё не завершён успешно' : result.status === 'needs_review' ? 'Есть признаки, требующие проверки' : 'Выбранные признаки обмана не обнаружены'}</strong><p>Вероятность мошенничества не рассчитана. Это не заключение о безопасности.</p><small>Разобрано адресов: {result.coverage.urls_checked} из {result.coverage.urls_available}. Сохранён ответ страницы: {result.coverage.observed_urls}. Ожидают сверки OCR: {result.coverage.held_ocr_urls}.</small>{result.coverage.truncated && <p>Достигнут лимит 100 адресов; остальные не проверены этим модулем.</p>}</div>
    <div className="audit-checks">{result.checks.map(check => <article key={check.name}><h3>{check.name}</h3><span className="badge">{checkNames[check.status] || check.status}</span><p>{check.detail}</p></article>)}</div>
    <h3>Наблюдаемые признаки · {result.findings.length}</h3>
    {result.findings.length === 0 && <p>Отсутствие этих признаков не исключает другие способы обмана.</p>}
    {result.findings.map(finding => <article className="audit-finding" key={finding.id}><h4>{finding.title}</h4><blockquote>{finding.quote}</blockquote><p>{finding.detail}</p>{finding.evidence_ids.length > 0 && <button className="text-button" onClick={() => onEvidence(finding.evidence_ids)}>Сохранённый источник<ArrowUpRight size={15} /></button>}{finding.reference && <a href={finding.reference} target="_blank" rel="noreferrer">Источник справочника</a>}</article>)}
    <details><summary>Проверенные адреса · {result.urls.length}</summary>{result.urls.map(row => <article className="audit-url" key={row.url}><code>{row.url}</code><p>Фактический узел: <strong>{row.host || 'не определён'}</strong>{row.unicode_host !== row.host && <> · Unicode: <strong>{row.unicode_host}</strong></>}</p><small>{row.observed ? 'Ответ страницы сохранён в основном анализе' : 'Сохранённого ответа страницы нет'}</small>{row.brands.map(brand => <p key={brand.name}>{brand.name}: {brand.status === 'domain_match' ? 'совпадение с доменом справочника' : 'справочник требует обновления'}. Сверка: {brand.checked_at}; пересмотр: {brand.review_after}. Это не проверка акции, владельца или лицензии.</p>)}</article>)}</details>
    <details><summary>Границы проверки</summary><ul>{result.limitations.map(limit => <li key={limit}>{limit}</li>)}</ul></details>
    <small>Отчёт: {date(result.generated_at)} · {result.schema}{result.source_analyzed_at && <> · исходный анализ: {date(result.source_analyzed_at)}</>}</small>
  </section>
}
