import type { Case } from '../types'

const names = { track1: 'Трек 1 · платное участие в розыгрыше', track3: 'Трек 3 · инвестиционные обещания и вовлечение' }
const levels: Record<string, string> = { low: 'Низкий', medium: 'Средний', high: 'Высокий' }
export default function TrackExtensions({ current, onMaterial }: { current: Case; onMaterial: (id: string) => void }) {
  if (!current.extensions || ['pending', 'running'].includes(current.status)) return null
  return <details className="analysis-details"><summary>Расширения треков 1 и 3</summary><div className="analysis-details-body">
    <p>Отдельные признаки для ручной проверки. Они не повышают индекс основного трека 2.</p>
    {current.extensions.materials.map(material => <article key={material.material_id}>
      <button className="text-button" onClick={() => onMaterial(material.material_id)}>Открыть исходный материал</button>
      {(['track1', 'track3'] as const).map(track => { const result = material[track]; return <section key={track}>
        <h3>{names[track]}</h3><p>{levels[result.level]} приоритет · {result.value} / 100</p>
        <ul>{result.signals.map((signal, index) => <li key={index}>«{signal.quote}»</li>)}</ul>
        {result.alternative_context && <p>Учтён альтернативный контекст: {result.alternative_context}</p>}
      </section> })}
    </article>)}
  </div></details>
}
