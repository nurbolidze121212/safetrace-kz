'use strict';
const $ = id => document.getElementById(id);
const el = (tag, text, cls) => { const n = document.createElement(tag); if (text != null) n.textContent = text; if (cls) n.className = cls; return n; };
const pct = x => x == null ? '—' : (100 * x).toFixed(1) + '%';
const measure = (row, key) => { const ci = row[key + '_ci'] || row[key + '_wilson95']; return pct(row[key]) + (ci ? ' [' + ci.map(pct).join('–') + ']' : ''); };
function showEvidence(doc, ids) {
  const box = $('evidence'); box.replaceChildren();
  const selected = doc.graph.evidence.filter(e => ids.includes(e.id));
  if (!selected.length) box.append(el('p', 'Для этого элемента отдельная цитата не сохранена.'));
  for (const e of selected) { box.append(el('h4', e.method), el('blockquote', e.quote || 'Наблюдение без текстового фрагмента')); }
}
function showCase(doc, index) {
  [...$('examples').children].forEach((n, i) => n.setAttribute('aria-pressed', String(i === index)));
  $('case-title').textContent = doc.title;
  const mat = doc.materials[0]; $('source').textContent = mat.source;
  $('original').textContent = mat.text || 'Текст получен из изображения, без подсказки в поле сообщения.';
  $('original-image').hidden = !doc.image_preview;
  if (doc.image_preview) $('original-image').src = doc.image_preview;
  $('ocr-box').hidden = !mat.ocr; $('ocr-box').open = Boolean(mat.ocr); $('ocr').textContent = mat.ocr?.text || '';
  $('score').textContent = doc.score.value;
  $('level').textContent = {high:'Высокий приоритет',medium:'Средний приоритет',low:'Низкий приоритет'}[doc.score.level];
  $('coverage').textContent = doc.sufficient_data ? 'Данных достаточно для применённых правил.' : 'Часть данных требует сверки. Низкий индекс не подтверждает безопасность.';
  $('reasons').replaceChildren();
  for (const c of doc.score.contributions) { const b = el('button', null, 'reason'); b.append(el('span', c.title), el('strong', (c.weight > 0 ? '+' : '') + c.weight + ' ↗')); b.onclick = () => showEvidence(doc, c.evidence_ids); $('reasons').append(b); }
  if (!doc.score.contributions.length) $('reasons').append(el('p', 'Положительные сочетания признаков не подтверждены.'));
  $('limits').replaceChildren(...doc.limitations.map(x => el('li',x)));
  $('download').href = doc.download;
  $('route').replaceChildren();
  for (const o of doc.trace.observations) { const b = el('button',null,'route-button'); b.append(el('b',o.url),el('small',(o.status_code ? 'HTTP '+o.status_code : 'Остановка')+' · '+o.method)); b.onclick = () => showEvidence(doc,[o.evidence_id]); $('route').append(b); }
  if (!doc.trace.observations.length) $('route').append(el('p','Переходов нет. Адрес может отсутствовать или ожидать сверки OCR.'));
  showEvidence(doc, doc.image_preview && doc.trace.observations[0] ? [doc.trace.observations[0].evidence_id] : (doc.score.contributions[0]?.evidence_ids || [mat.source_evidence_id]));
}
fetch('data.json').then(r => { if(!r.ok) throw Error('Не удалось загрузить примеры'); return r.json(); }).then(data => {
  $('loading').hidden = true;
  const cases = [...data.cases].sort((a, b) => Number(Boolean(b.image_preview)) - Number(Boolean(a.image_preview)));
  cases.forEach((doc, i) => {const b = el('button', doc.title); b.onclick = () => showCase(doc, i); $('examples').append(b);});
  showCase(cases[0],0);
  const labels = {'all':'Все случаи','language:ru':'Русский','language:kk':'Казахский','language:mixed':'Смешанный','language:translit':'Транслит','format:image':'Изображения','format:text':'Текст'};
  for (const [name,row] of [['all',data.evaluation.full],...Object.entries(data.evaluation.slices)]) {const tr=el('tr'); for(const val of [labels[name]||name,row.n,measure(row,'precision'),measure(row,'recall'),measure(row,'fpr')]) tr.append(el('td',val)); $('metric-rows').append(tr);}
}).catch(e => {$('loading').textContent=e.message;});
fetch('network.json').then(r=>{if(!r.ok)throw Error();return r.json();}).then(data=>{
  $('network-summary').textContent=`${data.counts.entities} сущностей · ${data.counts.materials} материалов · ${data.counts.communities} групп Louvain. Внешние сайты не запрашивались. Общий хаб не объединяет группы автоматически.`;
  data.communities.forEach((c,i)=>{const option=el('option',`Группа ${i+1} · ${c.size} материалов`);option.value=c.id;$('network-group').append(option);});
  const ns='http://www.w3.org/2000/svg';
  function draw(){const svg=$('network-svg');svg.replaceChildren();const chosen=data.communities.find(c=>c.id===$('network-group').value);const selected=chosen?new Set(chosen.case_ids):null;const nodes=data.nodes.filter(n=>!selected||n.case_ids.some(c=>selected.has(c)));const ids=new Set(nodes.map(n=>n.id));const coords=new Map();nodes.forEach((n,i)=>{const angle=i*2*Math.PI/nodes.length;const radius=n.type==='material'?180:220+(i%3)*12;coords.set(n.id,[500+Math.cos(angle)*radius*1.65,260+Math.sin(angle)*radius]);});
    for(const e of data.edges){if(!ids.has(e.source)||!ids.has(e.target))continue;const a=coords.get(e.source),b=coords.get(e.target);const line=document.createElementNS(ns,'line');for(const [k,v]of Object.entries({x1:a[0],y1:a[1],x2:b[0],y2:b[1],stroke:e.type==='matching_identifier'?'#bd842b':'#d7e0ec','stroke-width':e.type==='matching_identifier'?1.4:.5}))line.setAttribute(k,v);svg.append(line);}
    nodes.forEach(n=>{const [x,y]=coords.get(n.id),circle=document.createElementNS(ns,'circle');for(const[k,v]of Object.entries({cx:x,cy:y,r:n.type==='material'?6:3.5,fill:{material:'#315fe2',source:'#138d76',identifier:'#bd842b'}[n.type]||'#8fa1b8',tabindex:'0',role:'button','aria-label':n.label}))circle.setAttribute(k,v);const select=()=>{$('network-detail').textContent=n.type+': '+n.label+' · случаев: '+n.case_ids.length;};circle.onclick=select;circle.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();select();}};const title=document.createElementNS(ns,'title');title.textContent=n.label;circle.append(title);svg.append(circle);});}
  $('network-group').onchange=draw;draw();
}).catch(()=>{$('network-summary').textContent='Сетевой пример недоступен. Откройте локальный экран «Сеть материалов».';});
