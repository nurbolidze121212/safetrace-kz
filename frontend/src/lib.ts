export const statuses: Record<string, string> = { pending: 'Ожидает', running: 'Выполняется', completed: 'Завершен', partial: 'Частично', error: 'Ошибка', cancelled: 'Отменен' }
export const levels: Record<string, string> = { high: 'Высокий', medium: 'Средний', low: 'Низкий' }
export const modes: Record<string, string> = { local: 'Локальный анализ', cloud: 'Облачный контекст', synthetic: 'Синтетический стенд', replay: 'Сохраненный повтор' }
export const methods: Record<string, string> = { local_rule: 'Локальное правило', cloud_model: 'Облачная модель', network: 'Сетевое наблюдение', synthetic_transport: 'Синтетический транспорт', ocr: 'OCR · распознавание', user_supplied: 'Заявлено при импорте', source_text: 'Текст источника', scoped_exact_match: 'Совпадение в области домена', url_parser: 'Разбор URL' }
export const edgeNames: Record<string, string> = { published: 'Заявленный источник', contains_link: 'Содержит ссылку', redirects: 'HTTP-переход', page_link: 'Ссылка на странице', contains_identifier: 'Содержит идентификатор', matching_identifier: 'Совпадение идентификатора', observed: 'Наблюдение', on_domain: 'Домен' }
export const stageNames: Record<string, string> = { originals: 'Оригинал', ocr: 'OCR', features: 'Признаки', links: 'Переходы', graph: 'Связи', priority: 'Приоритет', interrupted: 'Прервано перезапуском' }
export const decisions: Record<string, string> = { confirmed: 'Подтвердить признаки', false_positive: 'Ложное срабатывание', needs_data: 'Нужны данные' }
export const contexts: Record<string, string> = { promotion: 'Продвижение', warning: 'Предупреждение', news: 'Новость', education: 'Образовательный разбор', free_game: 'Бесплатная игра', ordinary: 'Обычный контекст', affiliate: 'Партнерское предложение', ambiguous: 'Неоднозначно' }
export const date = (value: string) => {
  const d = new Date(value)
  return Number.isNaN(d.getTime()) ? 'Дата не указана' : new Intl.DateTimeFormat('ru-RU', { timeZone: 'Asia/Qyzylorda', day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' }).format(d)
}
export const pct = (n: number | null | undefined) => n == null || !Number.isFinite(n) ? '—' : (n * 100).toFixed(1) + '%'
export const errorMessage = (error: unknown) => error instanceof Error ? error.message : String(error)
export const isActive = (status: string) => status === 'running' || status === 'pending'
export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response
  try { response = await fetch('/api' + path, init) }
  catch { throw new Error('Нет соединения с локальным сервером. Проверьте, что приложение запущено, и повторите действие.') }
  if (!response.ok) {
    const body = await response.json().catch(() => ({}))
    throw new Error(typeof body.detail === 'string' ? body.detail : 'Не удалось выполнить действие. Проверьте заполненные поля.')
  }
  return response.json()
}
export const post = <T,>(path: string, data: unknown = {}) => api<T>(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) })
