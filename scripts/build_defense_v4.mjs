import fs from 'node:fs/promises';
import path from 'node:path';
import { pathToFileURL } from 'node:url';
import { Presentation, PresentationFile } from '@oai/artifact-tool';

const workspaceDir = 'C:/Users/nurbo/Desktop/vvv/safetrace-kz';
const buildDir = path.join(workspaceDir, 'tmp/defense-v4');
const reportDir = path.join(workspaceDir, 'reports/defense-v4');
const SKILL_DIR = 'C:/Users/nurbo/.codex/plugins/cache/openai-primary-runtime/presentations/26.1017.22135/skills/presentations';
const RUNTIME_PYTHON = 'C:/Users/nurbo/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe';
const { finalizePresentation, resolvePresentationFont, applyPresentationChartFont } = await import(pathToFileURL(path.join(SKILL_DIR, 'container_tools/artifact_tool_utils.mjs')).href);
const font = resolvePresentationFont({ fontFamily: 'Segoe UI' });
const p = Presentation.create({ slideSize: { width: 1280, height: 720 } });
const ink='#14243D', muted='#526781', accent='#2F5EB8', pale='#AABDD9', green='#326554';
const read = async f => JSON.parse(await fs.readFile(path.join(workspaceDir,f),'utf8'));
const old = await read('reports/versions/synthetic-v4/v3-evaluation.json');
const current = await read('reports/versions/synthetic-v4/evaluation.json');
const notes=[];
function text(s,value,x,y,w,h,size=27,color=ink,bold=false){
  const t=s.shapes.add({geometry:'textbox',position:{left:x,top:y,width:w,height:h},fill:'none',line:{width:0,fill:'none'}});
  t.text=value;t.text.style={typeface:font,fontSize:size,color,bold,insets:0,autoFit:'none',verticalAlignment:'top',wrap:'square'};return t;
}
function slide(title,n,dark=false){const s=p.slides.add();s.background.fill=dark?ink:'#FFFFFF';if(title)text(s,title,64,42,1152,112,46,dark?'#FFFFFF':ink,true);text(s,String(n).padStart(2,'0'),1160,667,56,28,21,dark?pale:muted);return s;}
function note(s,title,speech,sources){s.speakerNotes.text=speech+'\n\nИсточники: '+sources.join('; ');notes.push({title,speech,sources});}
async function picture(s,name,x,y,w,h,alt,crop){const b=await fs.readFile(path.join(workspaceDir,name));s.images.add({blob:b.buffer.slice(b.byteOffset,b.byteOffset+b.byteLength),contentType:'image/png',fit:'contain',crop,alt,position:{left:x,top:y,width:w,height:h}});}
function chart(s,categories,series,x,y,w,h,max){
 const c=s.charts.add('bar',{position:{left:x,top:y,width:w,height:h},categories,series,
 title:'',hasLegend:true,legend:{position:'bottom',textStyle:{fontSize:23,fill:muted}},
 barOptions:{direction:'column',grouping:'clustered',gapWidth:100},
 xAxis:{textStyle:{fontSize:23,fill:muted},line:{width:1,fill:'#D9E1EC'},majorGridlines:null},
 yAxis:{min:0,max,majorUnit:10,numberFormatCode:'0',textStyle:{fontSize:22,fill:muted},majorGridlines:{width:1,fill:'#E5EAF1'}},
 dataLabels:{showValue:true,position:'outEnd',numberFormatCode:'0',textStyle:{fontSize:26,fill:ink,bold:true}},
 chartFill:'#FFFFFF',plotAreaFill:'#FFFFFF',chartLine:{width:0,fill:'none'}});applyPresentationChartFont(c,{fontFamily:font});return c;
}

let s=slide('',1,true);
text(s,'SafeTrace KZ',64,175,1152,110,80,'#FFFFFF',true);
text(s,'Проверка скрытого продвижения\nигровых ресурсов',68,315,1100,132,42,'#FFFFFF');
text(s,'Трек 2 «Скрытая игра» · локальный MVP',68,577,1100,50,27,pale);
note(s,'SafeTrace KZ','SafeTrace помогает аналитику проверить скрытое продвижение игровых ресурсов. В публикации может не быть слова «казино»: только бонус, приглашение или QR. Мы собираем путь к назначению и сохраняем источник каждого вывода. Решение принимает человек; индекс показывает приоритет проверки.', ['SPEC.md','docs/PROJECT_REPORT_V4.md']);

s=slide('Проверяемый маршрут',2);
await picture(s,'reports/acceptance-v4/browser-graph-evidence.png',64,157,1152,458,'Реальный интерфейс v4: связь графа открывает наблюдение синтетического перехода');
text(s,'Материал → посредник → назначение → источник связи',64,622,1110,40,27,muted);
note(s,'Проверяемый маршрут','Здесь новый материал проходит OCR и разрешённые переходы. В демо страницы синтетические, это явно подписано. HTTP-переход и ссылка внутри страницы — разные наблюдения. Второй материал можно связать по точному идентификатору в одной области назначения. Открытие стрелки показывает источник; совпадение не доказывает общего владельца.', ['reports/acceptance-v4/browser-acceptance.json','reports/acceptance-v4/browser-graph-evidence.png']);

s=slide('Сверка спорного адреса',3);
await picture(s,'reports/acceptance-v4/browser-ocr-source-full.png',64,230,550,367,'Фрагмент реальной панели исходника: сырой URL, оригинал и координаты OCR',{left:0.53,top:0.24,right:0.04,bottom:0.27});
text(s,'Сырой OCR остаётся',674,183,542,63,35,ink,true);
text(s,'Спорный адрес остановлен.\nАналитик сверяет оригинал\nи явно выбирает уточнение.',674,271,542,148,31,muted);
text(s,'Новый анализ сохраняет\nпредыдущую попытку',674,451,542,105,35,ink,true);
text(s,'Ручной результат отдельно от автоматических метрик',674,588,542,72,25,accent);
note(s,'Сверка спорного адреса','Ошибка одной буквы может поменять назначение. Поэтому спорный URL не исправляется молча. Оригинал, координаты и первичный текст остаются; дополнительные чтения — только предложения. После явного уточнения начинается новый анализ с историей. Проверены отмена, повтор, перезапуск и настоящий ZIP. Ручной успех не прибавляется к автоматической точности.', ['docs/METHODOLOGY.md','reports/acceptance-v4/browser-lifecycle.json','reports/acceptance-v4/browser-cancel-export.json']);

s=slide('Сравнение на новых 80 случаях',4);
text(s,'40 положительных · 40 отрицательных · авторский синтетический набор',64,151,1152,45,26,muted);
chart(s,['Найдено из 40','Ложных из 40'],[
 {name:'v3',values:[old.variants.full.tp,old.variants.full.fp],fill:'#B8C7DF'},
 {name:'v4',values:[current.variants.full.tp,current.variants.full.fp],fill:accent}],64,220,780,350,40);
text(s,'93,75%',890,230,310,66,49,accent,true);text(s,'precision v4',894,301,310,40,26,muted);
text(s,'75% recall',890,375,310,55,36,ink,true);text(s,'74 / 80',890,465,310,55,36,ink,true);text(s,'достаточно данных',894,521,310,40,23,muted);
text(s,'9 классификаций исправлены, 3 ухудшились. Цели 95% precision / 80% recall не достигнуты.',64,610,1110,65,24,muted);
note(s,'Сравнение на новых 80 случаях','До новых входов заморожены код, веса и протокол. На одинаковых 80 случаях ложные тревоги снизились с девяти до двух, но найдено 30 положительных из 40 вместо 31. Precision 93,75%, recall 75%, достаточные данные в 74 случаях. Шесть положительных отказов входят в пропуски. Девять классификаций исправлены, три ухудшились. Цели precision 95 и recall 80 не достигнуты. Интервалы широкие: precision 79,85–98,27%, recall 59,81–85,81%. Независимых разметчиков нет.', ['reports/EVALUATION_V4.md','reports/versions/synthetic-v4/comparison.json']);

s=slide('Автоматическое принятие OCR-адресов',5);
text(s,'31 ожидаемый URL на 28 изображениях с видимым адресом',64,151,1152,45,27,muted);
chart(s,['Правильных','Неверных','Пропущенных'],[
 {name:'v3',values:[old.extraction.automatic_url.tp,old.extraction.automatic_url.fp,old.extraction.automatic_url.fn],fill:'#B8C7DF'},
 {name:'v4',values:[current.extraction.automatic_url.tp,current.extraction.automatic_url.fp,current.extraction.automatic_url.fn],fill:accent}],64,220,1152,340,30);
text(s,'Первичное OCR одинаковое. Правильный набор среди подсказок: 27/28. QR: 8/8.',64,587,1125,40,24,muted);
text(s,'Полный процесс на изображениях: recall 12/16 → 10/16; ложные тревоги 2 → 0.',64,633,1110,40,24,muted);
note(s,'Автоматическое принятие OCR-адресов','Мы не заявляем, что первичное распознавание стало точнее: оно одинаковое. Проверка остановила все девять неверных автоматически принятых адресов, но остановила и один правильный. Правильный набор среди подсказок доступен на 27 из 28 изображений; это потенциал ручной сверки. На изображениях общий recall снизился с 12 из 16 до 10 из 16. Казахские отрицания, межфразовая связь и повреждённые слова остаются задачами следующего цикла.', ['reports/ERROR_ANALYSIS_V4.md','reports/versions/synthetic-v4/evaluation.json']);

s=slide('Досье и следующий шаг',6);
text(s,'Проверенный локальный процесс',64,180,1152,60,36,ink,true);
text(s,'Оригиналы, наблюдения и история\nHTML + JSON + SHA-256\nWindows CPU, без облачного ключа',64,283,680,168,31,muted);
text(s,'Независимая проверка',814,283,402,92,34,ink,true);
text(s,'Новые разрешённые примеры\nРазметка двумя людьми\nВремя аналитика и ошибки',814,397,402,164,28,muted);
text(s,'Холодный снимок 9,96 с · повтор с кэшем 0,196 с',64,539,680,84,29,green,true);
text(s,'Видео — следующий ограниченный этап; спецификация подготовлена',64,638,1110,36,23,muted);
note(s,'Досье и следующий шаг','Результат — досье с исходниками, наблюдениями и историей. Контрольные суммы подтверждают целостность, а не юридическую истинность. На текущем CPU холодный снимок занял 9,96 секунды, повтор с кэшем 0,196 секунды. Это технический замер, экономия времени человека не измерена. Следующий шаг — независимые разрешённые примеры, исправление выявленных причин на новом dev и замер работы аналитика. Видео имеет отдельную спецификацию; прямые эфиры и массовый сбор в MVP не входят.', ['reports/acceptance-v4/runtime.json','reports/acceptance-v4/offline-check.json','docs/ROADMAP.md','docs/VIDEO_NEXT.md']);

await fs.mkdir(reportDir,{recursive:true});
for(const [i,item] of p.slides.items.entries()){
 const blob=await p.export({slide:item,format:'png',scale:1});await fs.writeFile(path.join(reportDir,`slide-${i+1}.png`),new Uint8Array(await blob.arrayBuffer()));
 const layout=await item.export({format:'layout'});await fs.writeFile(path.join(buildDir,`slide-${i+1}.layout.json`),await layout.text());
}
await fs.writeFile(path.join(reportDir,'speaker-notes.json'),JSON.stringify(notes,null,2));
await fs.writeFile(path.join(buildDir,'presentation.json'),JSON.stringify(p.toProto()));
const candidatePath=path.join(buildDir,'candidate.pptx');await (await PresentationFile.exportPptx(p)).save(candidatePath);
const result=await finalizePresentation({explicitTotalSlideCount:6,requiredNativeChartOwnerSlides:[4,5],requiredNativeTableOwnerSlides:[],materializeLiteralChartWorkbooks:true,workspaceDir,candidatePath,finalPath:path.join(workspaceDir,'deliverables/SafeTrace-KZ-defense-v4-r3.pptx'),pythonExecutable:RUNTIME_PYTHON,integrityValidatorPath:path.join(SKILL_DIR,'container_tools/inspect_presentation_package_integrity.py'),layoutValidatorPath:path.join(SKILL_DIR,'container_tools/inspect_presentation_layout_geometry.py'),layoutArgs:['--expected-slide-size-emu','12192000,6858000','--validate-bullet-geometry','--validate-heading-fit'],fontPolicy:{basis:'design',families:[font]},verifyArtifactToolImport:true,receiptPath:path.join(buildDir,'validation-r3.json')});
console.log(JSON.stringify({path:result.finalPath,sha256:result.finalSha256,bytes:result.byteCount}));
