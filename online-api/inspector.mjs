import {lookup as dnsLookup} from 'node:dns/promises';
import {request as httpRequest} from 'node:http';
import {request as httpsRequest} from 'node:https';
import {isIP} from 'node:net';

const MAX_HOPS = 4;
const MAX_BYTES = 128 * 1024;
const TIMEOUT_MS = 4000;

export function publicIPv4(value) {
  if (isIP(value) !== 4) return false;
  const octets = value.split('.').map(Number);
  const [a, b, c] = octets;
  return a > 0 && a < 224 && a !== 10 && a !== 127 &&
    !(a === 100 && b >= 64 && b <= 127) &&
    !(a === 169 && b === 254) &&
    !(a === 172 && b >= 16 && b <= 31) &&
    !(a === 192 && b === 168) &&
    !(a === 192 && b === 0 && c === 0) &&
    !(a === 192 && b === 0 && c === 2) &&
    !(a === 198 && (b === 18 || b === 19 || (b === 51 && c === 100))) &&
    !(a === 203 && b === 0 && c === 113) &&
    a !== 255;
}

export function parseTarget(raw) {
  if (typeof raw !== 'string' || raw.length > 2048) throw new Error('Адрес должен быть строкой до 2048 символов.');
  let url;
  try { url = new URL(raw); } catch { throw new Error('Нужна полная ссылка http:// или https://.'); }
  if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password ||
      (url.port && !['80', '443'].includes(url.port)) || isIP(url.hostname) ||
      !url.hostname.includes('.') ||
      /(?:^|\.)(?:localhost|local|internal|test|example|invalid)$/iu.test(url.hostname)) {
    throw new Error('Этот адрес не разрешён для онлайн-проверки.');
  }
  url.hash = '';
  return url;
}

async function resolvePublic(hostname) {
  const records = await dnsLookup(hostname, {all: true, family: 4});
  if (!records.length || !records.every(item => publicIPv4(item.address))) throw new Error('Домен не указывает на разрешённый публичный IPv4-адрес.');
  return records[0].address;
}

function getPage(url, pinnedAddress) {
  return new Promise((resolve, reject) => {
    const client = url.protocol === 'https:' ? httpsRequest : httpRequest;
    const req = client(url, {
      method: 'GET',
      agent: false,
      timeout: TIMEOUT_MS,
      lookup: (_host, _options, done) => done(null, pinnedAddress, 4),
      headers: {'User-Agent': 'SafeTrace-KZ/3.0 (+https://github.com/nurbolidze121212/safetrace-kz)', 'Accept': 'text/html, text/plain;q=0.8', 'Cookie': '', 'Range': `bytes=0-${MAX_BYTES - 1}`},
    }, response => {
      const status = response.statusCode || 0;
      const location = response.headers.location;
      if (status >= 300 && status < 400 && location) {response.destroy(); resolve({status, location}); return;}
      const contentType = String(response.headers['content-type'] || '').toLowerCase();
      if (!contentType.includes('text/html') && !contentType.includes('text/plain')) {response.destroy(); resolve({status, contentType, body: null}); return;}
      const chunks = []; let size = 0;
      response.on('data', chunk => {
        size += chunk.length;
        if (size > MAX_BYTES) {response.destroy(); reject(new Error('Страница превышает ограничение чтения.')); return;}
        chunks.push(chunk);
      });
      response.on('end', () => resolve({status, contentType, body: Buffer.concat(chunks).toString('utf8')}));
      response.on('error', reject);
    });
    req.on('timeout', () => req.destroy(new Error('Сайт не ответил за 4 секунды.')));
    req.on('error', reject);
    req.end();
  });
}

function visibleText(html) {
  return html.replace(/<script\b[^>]*>[\s\S]*?<\/script>/giu, ' ')
    .replace(/<style\b[^>]*>[\s\S]*?<\/style>/giu, ' ')
    .replace(/<[^>]+>/gu, ' ')
    .replace(/&(?:nbsp|amp|quot|lt|gt);/giu, ' ')
    .replace(/\s+/gu, ' ').trim().slice(0, 5000);
}

export async function inspectUrl(raw, adapters = {}) {
  const resolve = adapters.resolve || resolvePublic;
  const request = adapters.request || getPage;
  let url = parseTarget(raw);
  const route = [];
  for (let hop = 0; hop <= MAX_HOPS; hop++) {
    const address = await resolve(url.hostname);
    if (!publicIPv4(address)) throw new Error('Домен не указывает на разрешённый публичный IPv4-адрес.');
    const page = await request(url, address);
    route.push({url: url.href, status: page.status});
    if (page.location) {
      if (hop === MAX_HOPS) throw new Error('Слишком длинная цепочка переходов.');
      url = parseTarget(new URL(page.location, url).href);
      continue;
    }
    const text = page.body ? visibleText(page.body) : '';
    return {
      version: 'online-url-1.0', input: raw, final_url: url.href, route,
      destination_verified: !!text && page.status >= 200 && page.status < 300,
      content_type: page.contentType || null, excerpt: text,
      limitation: 'Прочитан только ограниченный HTML/текст. Нет JS-рендеринга, OCR, вирусной проверки или проверки лицензии.',
    };
  }
}
