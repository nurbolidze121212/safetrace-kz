import type { Case } from '../types'
import { date, isActive } from '../lib'
import { compareAnalysisVersions } from '../analysisVersions'

export default function AnalysisDetails({ current, runtimeVersions }: { current: Case; runtimeVersions?: Record<string, string> }) {
  // While queued, the document can still contain the previous analysis metadata.
  if (isActive(current.status)) return null
  const comparison = compareAnalysisVersions(current.versions, runtimeVersions)
  return <details className="analysis-details">
    <summary><span>Сведения о сохраненном анализе</span><span className={comparison.state === 'different' ? 'badge historical-version' : 'field-hint'}>{comparison.state === 'different' ? 'Версии отличаются' : comparison.state === 'match' ? 'Записанные версии совпадают' : 'Версии указаны не полностью'}</span></summary>
    <div className="analysis-details-body">
      <dl className="analysis-identifiers"><div><dt>Начало анализа</dt><dd>{current.analyzed_at ? date(current.analyzed_at) + ' · UTC+5' : 'Время не записано'}</dd></div><div><dt>Идентификатор анализа</dt><dd><code>{current.analysis_id || 'Не записан'}</code></dd></div></dl>
      {comparison.state === 'different' && <p>{current.mode === 'replay' ? 'Это сохраненный повтор. Для проверки текущей версией создайте новый анализ исходных материалов.' : 'Для проверки текущей версией используйте «Повторить анализ».'}</p>}
      {comparison.state === 'unknown' && <p>Полные сведения о версиях пока недоступны. Известные значения приведены ниже.</p>}
      <div className="analysis-version-scroll" role="region" aria-label="Сравнение версий компонентов" tabIndex={0}><table><thead><tr><th>Компонент</th><th>Сохранено с результатом</th><th>Сейчас запущено</th></tr></thead><tbody>{comparison.rows.map(row => <tr key={row.key} className={row.saved && row.running && row.saved !== row.running ? 'version-difference' : undefined}><th scope="row">{row.label}</th><td>{row.saved || 'Не записано'}</td><td>{row.running || 'Не получено'}</td></tr>)}</tbody></table></div>
      <p className="analysis-scroll-hint">Таблицу можно прокручивать по горизонтали.</p>
    </div>
  </details>
}
