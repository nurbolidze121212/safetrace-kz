import {scoreText} from './text-score.mjs';

export const ONLINE_API = 'https://safetrace-kz-url.vercel.app/api/check-url';

export function summarizeFetched(page) {
  if (!page || !Array.isArray(page.route) || !page.final_url) throw new Error('Неполный ответ сервера.');
  if (!page.destination_verified) return {kind: 'unreadable', title: 'Страница не прочитана', explanation: 'Сервер дошёл до адреса, но доступного текста для оценки не получил.', score: null};
  const score = scoreText(page.excerpt || '');
  const has = name => score.signals.some(item => item.kind === name);
  if (has('alternative')) return {kind: 'context', title: 'Найден информационный или предупредительный контекст', explanation: 'Игровые слова здесь могут быть частью новости или предупреждения. Посмотрите цитату и страницу.', score};
  if (score.level === 'high') return {kind: 'promotional', title: 'На странице есть признаки продвижения игры', explanation: 'В полученном тексте совпали игровая лексика и призыв к действию. Это приоритет ручной проверки.', score};
  if (has('gambling')) return {kind: 'gaming', title: 'На странице есть игровая лексика', explanation: 'Игровые слова найдены, но скрытое продвижение не доказано.', score};
  return {kind: 'none_found', title: 'Игровые признаки в доступном тексте не найдены', explanation: 'Это не означает, что сайт безопасен: JS, изображения и скрытые переходы не проверены.', score};
}
