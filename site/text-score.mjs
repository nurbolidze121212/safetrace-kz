// Browser-only text triage. No fetch, OCR, storage, URL navigation or model downloads.
export const VERSION = 'browser-text-1.0';
const boundary = '[\\p{L}\\p{N}_]';
const glyphs = {к:'кk',а:'аa@🅰',з:'зz3',и:'иiuℹ',н:'нhn',о:'оo0🅾',с:'сcs',л:'лl',т:'тt',р:'рpr',у:'уyu',е:'еe',ф:'фf',п:'пpn',б:'бb6'};
const words = ['казино','слот','рулетка','фриспин','бонус'];
function view(original) {
  let text = '', map = [];
  let offset = 0;
  for (const character of original) {
    const value = character.normalize('NFKC').toLocaleLowerCase('ru');
    text += value;
    map.push(...Array.from({length:value.length}, () => [offset, offset + character.length]));
    offset += character.length;
  }
  const urls = [...text.matchAll(/https?:\/\/\S+/gu)].map(m => [m.index,m.index+m[0].length]);
  const replacements = [];
  for (const word of words) {
    const body = [...word].map(c => '(' + [...(glyphs[c] || c)].map(x => x.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|') + ')\\ufe0f?').join('[\\s._\\-\\u200b-\\u200d]{0,3}');
    for (const match of text.matchAll(new RegExp('(?<!'+boundary+')'+body+'(?!'+boundary+')','gu'))) {
      const a = match.index, b = a + match[0].length;
      if (!urls.some(([s,e]) => a < e && b > s) && !replacements.some(x => a < x.b && b > x.a)) replacements.push({a,b,word});
    }
  }
  for (const {a,b,word} of replacements.sort((x,y) => y.a-x.a)) {
    const span = [map[a][0],map[b-1][1]];
    text = text.slice(0,a)+word+text.slice(b);
    map.splice(a,b-a,...Array.from({length:word.length},()=>span));
  }
  return {text,map};
}
const patterns = {
  gambling: 'казино|casino|слот[а-я]*|slots?|рулетк[а-я]*|фриспин[а-я]*|құмар\\s+ойын[а-яәіңғүұқөһ]*|qumar\\s+oiyn[a-z]*',
  call: 'регистриру[а-я]*|переход[а-я]*|играй[а-я]*|забирай[а-я]*|вноси[а-я]*|тіркел[а-яәіңғүұқөһ]*|қосыл(?:ыңыз)?|ойна(?:ңыз|ңдар|йық)?|tirkel[a-z]*|qosyl|join|play',
  bonus: 'бонус[а-я]*|bonus|промокод[а-я]*|сыйлық[а-яәіңғүұқөһ]*',
  alternative: 'осторожно|мошеннич[а-я]*|предупрежд[а-я]*|новост[а-я]*|расследован[а-я]*|мақала|ескерту|сақтаныңыз|ойнама[а-яәіңғүұқөһ]*|қатыспа[а-яәіңғүұқөһ]*|oinama[a-z]*|тегін\\s+ойын|без\\s+денежных\\s+ставок',
};
export function scoreText(original) {
  if (typeof original !== 'string' || original.length > 20000) throw new Error('Введите не больше 20 000 символов.');
  const {text,map} = view(original), signals = [];
  const urls = [...text.matchAll(/https?:\/\/\S+/gu)].map(m => [m.index,m.index+m[0].length]);
  for (const [kind,pattern] of Object.entries(patterns)) {
    for (const match of text.matchAll(new RegExp('(?<!'+boundary+')(?:'+pattern+')(?!'+boundary+')','gu'))) {
      const a = match.index, b = a+match[0].length;
      if (urls.some(([s,e])=>s<=a && a<e)) continue;
      if (kind==='call' && /(?:не|ешқашан)\s+$/u.test(text.slice(Math.max(0,a-25),a))) continue;
      if (kind==='gambling' && /^\s+(?:емес|жоқ|emes|joq)(?![\p{L}\p{N}_])/u.test(text.slice(b))) continue;
      if (kind==='gambling' && /(?:процентная|строительная)\s+$/u.test(text.slice(Math.max(0,a-30),a))) continue;
      signals.push({kind,start:map[a][0],end:map[b-1][1],quote:original.slice(map[a][0],map[b-1][1])});
    }
  }
  const has = kind => signals.some(s=>s.kind===kind);
  const promotional = has('gambling') && has('call');
  const value = has('alternative') ? 0 : promotional ? (has('bonus') ? 80 : 65) : has('gambling') && has('bonus') ? 40 : 0;
  const sufficient = !!original.trim() && !(urls.length && !has('gambling') && !has('alternative'));
  return {version:VERSION,scope:'browser_text_only',value,level:value>=65?'high':value>=35?'medium':'low',sufficient,
    signals,links_opened:0,meaning:'Индекс приоритета проверки текста, не вероятность нарушения.'};
}
