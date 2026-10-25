import {inspectUrl} from '../inspector.mjs';

const ORIGIN = 'https://nurbolidze121212.github.io';
const buckets = new Map();
export default async function handler(req, res) {
  res.setHeader('Access-Control-Allow-Origin', ORIGIN);
  res.setHeader('Access-Control-Allow-Methods', 'POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
  res.setHeader('Cache-Control', 'no-store');
  if (req.method === 'OPTIONS') return res.status(204).end();
  if (req.method !== 'POST' || req.headers.origin !== ORIGIN) return res.status(405).json({error:'Метод или источник не разрешён.'});
  const ip = String(req.headers['x-forwarded-for'] || '').split(',')[0].slice(0, 80);
  const now = Date.now();
  const bucket = buckets.get(ip) || {until: now + 60000, count: 0};
  if (bucket.until < now) {bucket.until = now + 60000; bucket.count = 0;}
  bucket.count++;
  buckets.set(ip, bucket);
  if (bucket.count > 10) return res.status(429).json({error:'Лимит: не более 10 проверок в минуту.'});
  try {
    const raw = typeof req.body === 'object' && req.body !== null ? req.body.url : undefined;
    const result = await inspectUrl(raw);
    return res.status(200).json(result);
  } catch (error) {
    console.error('URL inspection rejected or failed:', error.message);
    return res.status(422).json({error: error.message});
  }
}
