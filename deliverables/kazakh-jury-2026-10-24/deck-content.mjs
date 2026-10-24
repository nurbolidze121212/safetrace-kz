// Live Artifact Session callbacks. The cover is authored in the first session cell.
// All diagrams, charts, tables and text below remain editable.
import {fileURLToPath} from 'node:url';
const ROOT=fileURLToPath(new URL('../../',import.meta.url)).replace(/\\/g,'/');
const GH='https://github.com/nurbolidze121212/safetrace-kz/blob/main/';
const C={ink:'#071C20',paper:'#F5F3EB',mint:'#A9E7CA',green:'#176954',body:'#263E40',muted:'#657571',red:'#B44738',white:'#FFFFFF'};
function text(s,name,value,x,y,w,h,size=28,color=C.ink,bold=false){
  const q=s.shapes.add({geometry:'textbox',name,position:{left:x,top:y,width:w,height:h},fill:'none',line:{fill:'none',width:0}});
  q.text=value; q.text.style={typeface:'Arial',fontSize:size,color,bold,insets:0,wrap:'square',autoFit:'none'};return q;
}
function base(p,n,title,dark=false){
  const s=p.slides.add({width:1280,height:720});s.background.fill=dark?C.ink:C.paper;
  text(s,'title',title,72,62,1136,110,44,dark?C.white:C.ink,true);
  text(s,'page',String(n).padStart(2,'0'),1160,662,48,28,18,dark?'#A3BFB5':C.muted);return s;
}
function note(s,t,source){s.speakerNotes.text=t+'\n\nДереккөздер:\n'+source.map(x=>GH+x).join('\n');}
function image(s,path,alt,x,y,w,h,crop){return s.images.add({path:ROOT+path,alt,position:{left:x,top:y,width:w,height:h},fit:'contain',...(crop?{crop}:{})});}
function node(s,name,title,url,x,y,w=330,h=158){const q=s.shapes.add({geometry:'rect',name,position:{left:x,top:y,width:w,height:h},fill:'#0F2A2D',line:{fill:'#528579',width:1.5}});text(s,name+'-title',title,x+20,y+22,w-40,42,28,C.mint,true);text(s,name+'-url',url,x+20,y+79,w-40,62,22,C.white);return q;}
function edge(s,a,b){s.shapes.connect(a,b,{kind:'straight',fromSide:'right',toSide:'left',line:{fill:C.mint,width:2},tail:{type:'triangle',width:'sm',length:'sm'}});}

const builders={
  2(p){const s=base(p,2,'«Казино» сөзі жоқ.\nЖарнама болуы мүмкін');
    image(s,'examples/import/picture.png','Өзіміз жасаған қазақша хабарламаның бастапқы суреті',72,235,1000,290);
    text(s,'mechanism','Бонус пен шақыру көрінеді.\nСілтеменің соңғы беті әлі белгісіз.',72,558,1060,74,29,C.body);
    text(s,'disclosure','Авторлық оқу материалы · тек сурет жүктелді, мәтін қолмен қосылған жоқ',72,661,1070,28,19,C.muted);
    note(s,'0:20–0:45. Мына хабарламада «казино» деген сөз жоқ. Тек бонус, шақыру және сілтеме бар. Соңғы бет аралық сайттың артында қалуы мүмкін. Пайдаланушы осы скриншотты өзі жүктейді. OCR суреттегі қазақша мәтін мен URL-ді оқиды. Түпнұсқа сақталады, сондықтан нәтижені қайта тексеруге болады. Бұл суретті біз оқу көрсетілімі үшін жасадық.', ['reports/PUBLIC_DEMO_2026_10_24.md','examples/import/picture.png']);
  },
  3(p){const s=base(p,3,'Сілтемелер тізбегі\nжасырын ұсынысты ашады',true);
    const a=node(s,'first','01  Сілтеме','go.safetrace.test\n/r/q7',72,292);
    const b=node(s,'middle','02  Аралық бет','hub.safetrace.test\n/offer',475,292);
    const c=node(s,'target','03  Ойын ұсынысы','arena.safetrace.test\n/welcome?ref=QALA7',878,292);
    edge(s,a,b);edge(s,b,c);
    text(s,'http-label','HTTP 302',315,233,230,34,22,C.mint,true).text.alignment='center';
    text(s,'html-label','Бет ішіндегі сілтеме',718,233,345,34,22,C.mint,true).text.alignment='center';
    text(s,'observations','Үш бет. Екі түрлі өту. Әр байланыстың сақталған дерегі бар.',72,504,1136,80,31,C.white);
    text(s,'disclosure','Синтетикалық стенд: мекенжайлар мен беттер оқу үшін жасалған. OCR нақты орындалды.',72,636,1065,54,21,'#B5CEC4');
    note(s,'0:45–1:20. Картада үш бет пен екі өту бар. Алғашқы мекенжай HTTP 302 арқылы аралық бетке бағыттайды. Одан кейінгі байланыс — HTML бетіндегі сілтеме. Соңғы бетте ойын белгілері мен QALA7 реферальды коды көрінеді. Қадамды басып, сақталған деректі ашуға болады. Бұл нақты казино желісіне жасалған зерттеу емес, өзіміздің синтетикалық стенд. Сілтеме түрлерін бөлек сақтау аналитикке қорытындының негізін тексеруге мүмкіндік береді.', ['fixtures/pages.json','reports/PUBLIC_DEMO_2026_10_24.md','docs/METHODOLOGY.md']);
  },
  4(p){const s=base(p,4,'Әр ұпайдың дереккөзі бар');
    text(s,'index','80',72,208,250,166,146,C.green,true);
    text(s,'index-name','Тексеру басымдығының\nиндексі · 0–100',72,388,500,78,29,C.body,true);
    text(s,'probability','80 ұпай ≠ 80% ықтималдық',72,491,575,45,29,C.red,true);
    image(s,'reports/public-demo-2026-10-24/https-desktop.png','Қолданбадағы индекс пен оның екі үлесі',658,224,550,353,{left:0.492,top:0.213,right:0.035,bottom:0.522});
    text(s,'excerpt','Қолданбадан алынған үзінді · 24.10.2026',658,590,550,34,21,C.muted);
    text(s,'analyst','Дереккөзді ашу, түпнұсқамен салыстыру, досьені жүктеу. Соңғы шешімді талдаушы қабылдайды.',72,637,1070,54,22,C.body);
    note(s,'1:20–1:55. Осы нәтижедегі 80 ұпай тексерудің басымдығын білдіреді. Оның 65 ұпайы суреттегі шақырудың ойын белгілері бар бетпен байланысына берілді. Тағы 15 ұпай жарнамалық контекстегі бонусқа тиесілі. Оң жақта қолданбаның нақты үзіндісі тұр. Себепті басқанда бастапқы сурет, OCR үзіндісі және сақталған бет ашылады. ZIP досьесінде есеп пен түпнұсқалар бар. 80 саны казино болуының 80 пайыз ықтималдығы емес. Соңғы шешімді талдаушы қабылдайды.\n\nҚосымша дерек: жүктелген safetrace-800f2ec6.zip, case.json, rules-4.0; +65 destination_and_call, +15 bonus_in_promotion.', ['reports/PUBLIC_DEMO_2026_10_24.md','docs/METHODOLOGY.md']);
  },
  5(p){const s=base(p,5,'Ескерту де «казино» сөзін қолданады');
    text(s,'warning-quote','«Казино жарнамасындағы\nсілтемеге өтпеңіз.\nДепозит салмаңыз.»',72,216,760,190,43,C.ink,true);
    text(s,'quote-caption','Тексерілген орысша ескерту үлгісінің мағыналық аудармасы',72,434,735,65,22,C.muted);
    text(s,'zero','0',930,195,220,190,170,C.green,true);
    text(s,'zero-label','Осы үлгідегі\nбасымдық индексі',897,414,300,86,28,C.body);
    text(s,'context','Бұл үлгі жарнама ретінде белгіленбеді.\nБасқа күрделі контекстерде қателер әлі бар.',72,560,1100,94,31,C.body);
    note(s,'1:55–2:20. Енді қарсы мысалға назар аударайық. Мұнда да казино, сілтеме және депозит туралы айтылады. Бірақ автор қатысуға шақырмайды, қауіптен сақтандырады. Тексерілген осы үлгінің индексі нөл болды. Слайдтағы мәтін — орысша түпнұсқаның мағыналық аудармасы, дәл осы қазақша сөйлеммен жаңа өлшеу жүргізілген жоқ. Бұл барлық ескертуді мінсіз түсінеміз деген уәде емес. Терістеу мен жаңалық контексінде қателер бар. Нөлдік индекс сілтеменің қауіпсіздігін растамайды.', ['reports/message-demo/verification.json','docs/MESSAGE_DEMO.md','reports/ERROR_ANALYSIS_V4.md']);
  },
  6(p){const s=base(p,6,'80 авторлық синтетикалық жағдай');
    text(s,'sample','40 жарнамалық · 40 жарнамалық емес · тәуелсіз сарапшы бағаламаған',72,178,1136,52,26,C.muted);
    const metrics=[{x:72,value:'93,75%',name:'Оң нәтижелердің\nдұрыстығы',ratio:'30 / 32 · precision'},{x:486,value:'75%',name:'Анықтау\nтолықтығы',ratio:'30 / 40 · recall'},{x:900,value:'5%',name:'Жалған дабыл\nүлесі',ratio:'2 / 40 · FPR'}];
    for(let i=0;i<metrics.length;i++){const m=metrics[i];text(s,'metric-'+i,m.value,m.x,291,i===2?308:385,115,i===0?83:96,C.green,true);text(s,'definition-'+i,m.name,m.x,436,340,90,31,C.ink,true);text(s,'ratio-'+i,m.ratio,m.x,547,345,45,25,C.muted);}
    text(s,'scope','Бұл — жасырын жарнама әдісінің v4 бағасы. Нақты интернет ағынындағы сапа әлі белгісіз.',72,641,1072,50,22,C.body);
    note(s,'2:20–2:55. Негізгі әдісті 80 авторлық синтетикалық жағдайда өлшедік. Оның жартысы жарнамалық, жартысы жарнамалық емес. Оң белгіленген 32 жағдайдың 30-ы дұрыс: precision 93,75 пайыз. Жарнамасы бар 40 жағдайдың 30-ын таптық: recall 75 пайыз. Жарнамасы жоқ 40 жағдайдың екеуінде жалған дабыл болды: FPR 5 пайыз. Деректер мен ережелерді бір автор дайындаған, тәуелсіз бағалау жоқ. Бұл көрсеткіштерді нақты интернетке де, қосымша фишинг модуліне де тікелей көшіруге болмайды.', ['reports/EVALUATION_V4.md','docs/EVALUATION_PROTOCOL_V4.md']);
  },
  7(p){const s=base(p,7,'Жалған дабыл азайды. Өткізіп алу қалды');
    s.charts.add('bar',{position:{left:66,top:210,width:720,height:378},categories:['Жалған дабыл','Өткізіп алу'],series:[{name:'v3',values:[9,9],fill:'#AAB7AF'},{name:'v4',values:[2,10],fill:C.green}],barOptions:{direction:'column',grouping:'clustered',gapWidth:95},hasLegend:true,legend:{position:'bottom',overlay:false,textStyle:{fontSize:23,fill:C.body}},titlePlacement:'none',chartFill:C.paper,plotAreaFill:C.paper,xAxis:{textStyle:{fontSize:23,fill:C.body},line:{fill:'#9DAEA5',width:1},majorGridlines:null},yAxis:{min:0,max:12,majorUnit:3,numberFormatCode:'0',textStyle:{fontSize:21,fill:C.muted},line:{fill:'none',width:0},majorGridlines:{fill:'#DDE2D9',width:1}},dataLabels:{showValue:true,position:'outEnd',numberFormatCode:'0',textStyle:{fontSize:26,bold:true,fill:C.ink}}});
    text(s,'image-metric','62,5%',864,239,345,110,80,C.red,true);
    text(s,'image-meaning','Суретпен берілген\nжарнамалық жағдайлардың\n10/16-сы анықталды',864,369,345,128,27,C.body);
    text(s,'priority','Келесі басымдық:\nOCR мекенжайлары\nмен қазақша контекст',864,527,345,102,25,C.body,true);
    text(s,'boundary','Бірдей 80 кіріс. Precision ≥95% және recall ≥80% мақсаттарына әлі жеткен жоқпыз.',72,651,1070,34,21,C.muted);
    note(s,'2:55–3:25. v3 пен v4 нұсқаларын бірдей кірістерде салыстырдық. Жалған дабыл тоғыздан екіге азайды. Бірақ өткізіп алу тоғыздан онға өсті. Суретпен берілген 16 жарнамалық жағдайдың онын анықтадық, яғни толықтық 62,5 пайыз. Бұл OCR таңбаларын тану дәлдігі емес, суреті бар жағдайларды толық талдаудың көрсеткіші. Сондықтан келесі жұмысты қазақша контекст пен күмәнді OCR мекенжайларына бағыттаймыз. Precision 95 және recall 80 пайыз мақсаттарына әлі жеткен жоқпыз.', ['reports/EVALUATION_V4.md','reports/ERROR_ANALYSIS_V4.md']);
  },
  8(p){const s=base(p,8,'Интерфейс браузерде.\nТалдау компьютерде орындалады',true);
    text(s,'client','Браузер',72,251,550,52,34,C.mint,true);
    text(s,'client-description','Мәтін, сілтеме немесе фотоны\nпайдаланушы өзі қосады.',72,315,590,88,31,C.white);
    text(s,'server','Сервер',72,447,550,52,34,C.mint,true);
    text(s,'server-description','OCR, ережелер және SQLite.\nДемо деректері бөлек сақталады.',72,511,610,86,30,C.white);
    image(s,'reports/public-demo-2026-10-24/https-mobile.png','Мобильді өлшемдегі тексеру нәтижесінің үзіндісі',847,220,325,380,{left:0,top:0.14,right:0,bottom:0.60});
    text(s,'mobile-caption','Браузердегі мобильді көрініс',814,609,394,32,20,'#B5CEC4');
    text(s,'deployment-limits','Уақытша HTTPS · компьютер қосулы болуы керек. Нақты телефондағы сынақ алда.',72,657,1080,31,21,'#B5CEC4');
    note(s,'3:25–3:50. Сайтты HTTPS арқылы ашуға болады. Интерфейс браузерде, ал OCR мен талдау автордың компьютеріндегі серверде жұмыс істейді. Демоға жеке деректер қоры бөлінген, кіру коды бар. Браузердің 390×844 өлшемін тексердік, физикалық телефонда әлі сынаған жоқпыз. Қазіргі мекенжай уақытша. Компьютер мен интернет қосулы болуы қажет. WhatsApp-ты автоматты оқымаймыз, материалды пайдаланушы өзі жүктейді. Суреттегі интерфейс орысша, қазақша кіріс материалы талданады.', ['reports/PUBLIC_DEMO_2026_10_24.md','docs/PUBLIC_DEMO.md']);
  },
  9(p){const s=base(p,9,'Сол материалдағы қосымша белгілер');
    text(s,'host','apple.com.claim.example',72,228,1136,82,50,C.ink,true);
    text(s,'host-meaning','Бұл мекенжай apple.com доменіне жатпайды.',72,332,1100,62,31,C.body);
    text(s,'secret','Жүлде уәдесі + құпия код сұрау',72,435,1136,65,38,C.green,true);
    text(s,'separation','Негізгі міндет — жасырын құмар ойын жарнамасы.\nҚосымша белгі казиноға қатыстылықты өздігінен дәлелдемейді.',72,546,1110,94,29,C.body);
    text(s,'experimental','Тәжірибелік модуль · бренд анықтамалығында әзірше тек Apple · жеке сапа бағасы жоқ',72,660,1080,30,19,C.muted);
    note(s,'3:50–4:10. Негізгі трек өзгермейді. Сол материалдағы қосымша алдау белгілерін бөлек көрсетеміз. Мысалы, apple.com басқа доменнің ішіне енгізілуі немесе жүлде уәдесімен бірге құпия код сұрау. Мекенжай — оқу мысалы. Анықтамалықта әзірше Apple ғана бар. Бұл модульдің сапасы негізгі метрикалармен өлшенген жоқ. Ол вирусты іске қосып талдамайды, лицензияны немесе сайт иесін растамайды. Сигнал казиноға қатыстылықты өздігінен дәлелдемейді.', ['docs/EXTENDED_ANALYSIS.md','reports/LINK_AUDIT_2_3.md']);
  },
  10(p){const s=base(p,10,'SafeTrace KZ',true);
    text(s,'closing','Талдаушы әр қорытындының\nдереккөзін тексере алады',72,206,1120,130,51,C.white,true);
    const next=[['01','Жаңа RU/KK материалдарын тәуелсіз бағалау'],['02','OCR мен қазақша контекстегі өткізіп алуды азайту'],['03','Нақты телефондар мен тұрақты серверде пилот']];
    for(let i=0;i<next.length;i++){text(s,'step-'+i,next[i][0],72,391+i*66,70,46,27,C.mint,true);text(s,'next-'+i,next[i][1],160,391+i*66,1040,46,29,C.white);}
    const link=text(s,'github','github.com/nurbolidze121212/safetrace-kz',72,627,1090,44,27,C.mint,true);link.text.get('github.com/nurbolidze121212/safetrace-kz').link={uri:'https://github.com/nurbolidze121212/safetrace-kz',isExternal:true};
    note(s,'4:10–5:00. Жобаның құндылығы — талдаушы әр қорытындыны бастапқы дерекке дейін тексере алады. Ол суреттегі мәтінді, сілтемелер тізбегін және ойын белгілерін бір талдауда көреді. Күмәнді OCR мекенжайын жүйе үнсіз түзетпейді. Досьені есеп пен түпнұсқаларымен бірге жүктеуге болады. Код, әдістеме және қателер GitHub-та ашық тұр. Ендігі кезең — тәуелсіз бағалау. Жаңа қазақша және орысша материалдар арқылы өткізіп алуды азайтып, нақты телефондарда және тұрақты серверде пилот өткізу керек. Қазір негізгі оқу мысалын көрсетіп, оның дереккөзін бірге ашуға дайынмын.\n\nУақыт белгілері — 5 минутқа арналған жоспар, өлшенген репетиция емес. 11–12-слайдтар сұрақтарға арналған қосымша.', ['docs/FOR_JUDGES.md','docs/RESEARCH_DOSSIER.md','reports/ERROR_ANALYSIS_V4.md','README.md']);
  },
  11(p){const s=base(p,11,'Қосымша · Бағалау хаттамасы');
    const vals=[['Нұсқа','TP','FP','TN','FN'],['v3 full','31','9','31','9'],['v4 full','30','2','38','10']];
    const table=s.tables.add({rows:3,columns:5,left:72,top:223,width:1136,height:207,columnWidths:[336,200,200,200,200],values:vals});
    table.borders.assign({fill:'#D9DFD5',width:1,style:'solid'});
    for(let r=0;r<3;r++)for(let c=0;c<5;c++){const cell=table.getCell(r,c);cell.fill=r===0?C.ink:(r===2?'#E3EEE3':C.paper);cell.text.style={typeface:'Arial',fontSize:29,color:r===0?C.white:C.ink,bold:r===0||r===2,insets:14,alignment:c===0?'left':'center'};}
    text(s,'protocol','Ереже тест деректерінен бұрын бекітілді.\nОң шешім: индекс ≥65 және дерек жеткілікті.\nДерек жетіспеген 6 оң жағдай FN құрамына кіреді.',72,468,1136,128,28,C.body);
    text(s,'kk','Қазақша шағын топ: n=19, recall 55,56%. Нақты ағынға жалпылауға болмайды.',72,641,1090,49,22,C.red);
    note(s,'Сұрақтарға арналған қосымша. TP — дұрыс оң, FP — жалған оң, TN — дұрыс теріс, FN — өткізіп алынған оң жағдай. 40 оң және 40 теріс үлгі. Ережелер мен деректерді бір автор дайындаған. Ядро 22.10.2026 01:37:49, жаңа деректер 01:41:52 (Asia/Qyzylorda). Деректерді тәуелсіз маман белгілеген жоқ. Қамту 74/80. Есептің толық кестелерінде Wilson аралықтары мен тілдер бойынша бөлінген нәтижелер бар. Бұрынғы басқа тест жиынтығындағы нәтижелерді осы сандармен тікелей салыстырмаймыз.', ['reports/EVALUATION_V4.md','docs/EVALUATION_PROTOCOL_V4.md']);
  },
  12(p){const s=base(p,12,'Қосымша · Жюри сұрақтарына жауап');
    const rows=[['Нақты казино желісі зерттелді ме?','Көрсетілімнің беттері мен маршруты синтетикалық.'],['100% анықтай ма?','80 авторлық синтетикалық үлгіде:\n10 өткізіп алу, 2 жалған дабыл.'],['Вирус не лицензия тексеріле ме?','Қазіргі нұсқада бұл тексерулер орындалмайды.'],['Телефонға арналған қолданба ма?','Браузерлік интерфейс. PWA және нақты құрылғы сынағы алда.'],['Бірдей код бір иені дәлелдей ме?','Жоқ. Байланыс — тексеруге арналған белгі, иелік дәлелі емес.']];
    for(let i=0;i<rows.length;i++){text(s,'question-'+i,rows[i][0],72,207+i*87,506,72,27,C.ink,true);text(s,'answer-'+i,rows[i][1],631,207+i*87,577,72,26,C.body);}
    note(s,'Бұл слайдты сұрақ-жауап кезінде пайдалану. Досьедегі SHA-256 файлдың кейін өзгермегенін тексеруге көмектеседі. Ол мәтіннің шындығын немесе заңдық жарамдылығын өздігінен растамайды. URL беделін тексеретін сыртқы қызмет қосылмаған. Қазіргі сыртқы стенд сыртқы сайттарды сұратпайды. HTTPS адресі уақытша, ортақ кезекке кіру коды бар. Дерек көзі жоқ тексеруді «орындалмады» деп көрсету керек.', ['docs/METHODOLOGY.md','docs/EXTENDED_ANALYSIS.md','reports/PUBLIC_DEMO_2026_10_24.md','reports/EVALUATION_V4.md']);
  }
};
export async function addBatch({presentation,input}){
  if(presentation.slides.items.length!==input.from-1)throw new Error('Unexpected slide count; inspect before appending');
  for(let n=input.from;n<=input.to;n++)builders[n](presentation);
  return {slideCount:presentation.slides.items.length,added:[input.from,input.to]};
}

export async function addCover({presentation}){
  const s=presentation.slides.items[0]??presentation.slides.add({width:1280,height:720});
  if(presentation.slides.items.length!==1||s.shapes.items.length||s.images.items.length)throw new Error('Cover requires one empty slide');
  s.background.fill=C.ink;
  image(s,'deliverables/kazakh-jury-2026-10-24/assets/cover-concept.png','Жасырын жарнама байланыстарының тұжырымдамалық иллюстрациясы',0,0,1280,720);
  text(s,'track','2-ТРЕК · «СКРЫТАЯ ИГРА»',72,68,650,40,22,C.mint,true);
  text(s,'project','SafeTrace KZ',68,202,700,116,80,C.white,true);
  text(s,'subject','Құмар ойындардың\nжасырын жарнамасын\nанықтау',72,334,670,180,43,'#F6F6EF',true);
  text(s,'event','SafeNet KZ · Шымкент · 2026',72,638,650,36,22,'#BDCCC8');
  const fs=await import('node:fs/promises');
  const notes=JSON.parse(await fs.readFile(ROOT+'deliverables/kazakh-jury-2026-10-24/speaker-notes.json','utf8'));
  s.speakerNotes.text=notes[0].notes;
  return {slideCount:1};
}
