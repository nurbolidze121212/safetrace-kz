import type { Case } from './types'

type Message = { title: string; detail: string; tone: 'neutral' | 'attention'; action?: 'materials' | 'route' | 'review' | 'retry'; actionLabel?: string }
const stages: Record<string, [string, string]> = {
  originals: ['Сохраняем исходный материал', 'Оригинал будет доступен для сверки с результатом.'],
  ocr: ['Читаем текст и ссылки на изображении', 'При первом запуске загружается модель OCR. Процент обновляется между этапами, а не во время распознавания.'],
  features: ['Проверяем признаки и контекст', 'Сопоставляем рекламные призывы, игровые признаки и альтернативные объяснения.'],
  links: ['Проверяем доступный маршрут ссылки', 'Недоступные переходы будут отмечены отдельно. Отсутствие ответа не означает безопасность ссылки.'],
  graph: ['Связываем наблюдения с источниками', 'У каждой связи сохраняется основание для ручной проверки.'],
  priority: ['Готовим результат и объяснение', 'Индекс определяет порядок ручной проверки, а не вероятность нарушения.'],
}

export function analysisMessage(item: Pick<Case, 'status' | 'stage' | 'score' | 'sufficient_data' | 'materials' | 'trace'>): Message {
  if (item.status === 'pending') return { title: 'Материал в очереди на анализ', detail: 'Запуск начнётся, когда освободится обработчик. Повторно отправлять материал не нужно.', tone: 'neutral' }
  if (item.status === 'running') {
    const [title, detail] = stages[item.stage] || ['Анализ выполняется', 'Состояние обновляется автоматически.']
    return { title, detail, tone: 'neutral' }
  }
  if (item.status === 'error' || item.status === 'cancelled') return {
    title: item.status === 'error' ? 'Анализ завершился с ошибкой' : 'Анализ отменён',
    detail: 'Этот запуск не даёт окончательного результата. Исходные материалы сохранены; проверьте ограничения ниже и повторите анализ.',
    tone: 'attention', action: 'retry', actionLabel: 'Повторить анализ',
  }
  const review = item.materials.some(m => m.url_reviews?.some(u => u.needs_review && !u.selected_url))
  const interrupted = item.status === 'partial' || item.sufficient_data === false || review
  const missingRoute = item.trace.observations.some(o => Boolean(o.stop))
  if (!item.score || interrupted) return {
    title: item.score?.level === 'high' ? 'Есть признаки продвижения, но проверка неполная' : 'Для вывода нужны дополнительные данные',
    detail: review ? 'Адрес на изображении распознан неоднозначно. Сверьте его с оригиналом и явно подтвердите уточнение перед проверкой переходов.' : missingRoute ? 'Часть маршрута недоступна. Посмотрите причину остановки: результат не подтверждает безопасность ссылки.' : 'Не все этапы или материалы проверены полностью. Откройте исходный материал и ограничения анализа.',
    tone: 'attention', action: review || !missingRoute ? 'materials' : 'route', actionLabel: review ? 'Сверить адрес с изображением' : missingRoute ? 'Почему маршрут не проверен' : 'Проверить исходный материал',
  }
  if (item.score.level === 'high' || item.score.level === 'medium') return {
    title: item.score.level === 'high' ? 'Обнаружены признаки продвижения азартных игр' : 'Есть основания для ручной проверки',
    detail: 'Сверьте выделенные фрагменты и маршрут ссылки. Автоматический анализ не устанавливает нарушение и не заменяет решение аналитика.',
    tone: 'attention', action: 'materials', actionLabel: 'Посмотреть основания в материале',
  }
  return { title: 'Весомых признаков продвижения не обнаружено', detail: 'По доступным материалам приоритет низкий. Это не подтверждение безопасности ссылки: фишинг и другие виды мошенничества здесь не оцениваются.', tone: 'neutral', action: 'review', actionLabel: 'Проверить и сохранить решение' }
}
