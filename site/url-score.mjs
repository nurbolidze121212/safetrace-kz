// Public-page URL triage. This module never opens the URL or sends it to a service.
export const URL_TRIAGE_VERSION = 'browser-url-1.0';
const LESSON = new Map([
  ['https://go.safetrace.test/r/q7', ['go.safetrace.test', 'hub.safetrace.test', 'arena.safetrace.test']],
  ['https://go.safetrace.test/r/second', ['go.safetrace.test', 'hub.safetrace.test', 'arena.safetrace.test']],
]);
const gambling = /(?:^|[^\p{L}\p{N}])(?:casino|kazino|казино|slots?|слот|roulette|рулетк|bet|ставк|aviator|авиатор)\d{0,4}(?:$|[^\p{L}\p{N}])/iu;
const alternative = /(?:^|[^\p{L}\p{N}])(?:news|article|warning|anti|новост|предупрежд|ескерту|мақала)(?:$|[^\p{L}\p{N}])/iu;

export function checkUrlInput(raw) {
  if (typeof raw !== 'string' || raw.length > 4000) throw new Error('Вставьте ссылку длиной до 4000 символов.');
  const candidate = raw.trim().match(/https?:\/\/[^\s<>"']+/iu)?.[0] || (/^www\./iu.test(raw.trim()) ? 'https://' + raw.trim() : raw.trim());
  let url;
  try { url = new URL(candidate); } catch { throw new Error('Нужна ссылка с https:// или http://.'); }
  if (!['https:', 'http:'].includes(url.protocol) || !url.hostname || url.username || url.password) throw new Error('Поддерживаются только HTTP(S)-адреса без логина и пароля.');
  const normalized = url.href.replace(/\/$/u, '');
  const lesson = LESSON.get(normalized);
  const evidence = [];
  const host = url.hostname.toLowerCase();
  let path = url.pathname;
  try { path = decodeURIComponent(path); } catch { /* preserve raw path */ }
  const visible = `${host} ${path}`.toLowerCase();
  if (gambling.test(visible)) evidence.push('Игровое слово в домене или пути адреса');
  if (alternative.test(visible)) evidence.push('В адресе есть маркер новости или предупреждения');
  if (host.startsWith('xn--') || host.includes('.xn--')) evidence.push('Домен содержит IDN/punycode: написание стоит сверить');
  if (/[\d]{2,}$/.test(host.split('.')[0] || '')) evidence.push('Цифровой суффикс доменного имени');
  for (const key of ['ref', 'promo', 'affiliate', 'partner']) if (url.searchParams.has(key)) evidence.push(`Параметр ${key}: возможное отслеживание перехода`);
  const nested = [...url.searchParams].find(([key, value]) => /^(?:url|target|redirect|to|next)$/iu.test(key) && /^https?:\/\//iu.test(value));
  if (nested) evidence.push(`В параметре ${nested[0]} указан другой адрес: ${nested[1].slice(0, 180)}`);
  const gamingInAddress = gambling.test(visible);
  const warningInAddress = alternative.test(visible);
  const status = lesson ? 'authored_demo_route' : gamingInAddress && !warningInAddress ? 'address_signals' : 'unverified';
  return {
    version: URL_TRIAGE_VERSION, input: raw, url: url.href, hostname: host, status,
    route: lesson || null, evidence, links_opened: 0, destination_verified: false,
    conclusion: lesson
      ? 'В сохранённом учебном .test-маршруте этот адрес ведёт к игровой странице. Это не проверка реального сайта.'
      : status === 'address_signals'
        ? 'В написании адреса есть игровые признаки. Содержимое и конечная страница не проверены.'
        : 'По одному адресу нельзя установить, ведёт ли он к казино. Содержимое и конечная страница не проверены.',
  };
}
