import {checkUrlInput} from './url-score.mjs';
import {ONLINE_API, summarizeFetched} from './online-url.mjs';

const form = document.getElementById('url-form');
const input = document.getElementById('url-input');
const result = document.getElementById('url-result');

form.addEventListener('submit', async event => {
  event.preventDefault();
  result.replaceChildren();
  try {
    const value = checkUrlInput(input.value);
    const title = document.createElement('h3');
    title.textContent = value.status === 'authored_demo_route' ? 'Учебный маршрут: игровая страница' :
      value.status === 'address_signals' ? 'Есть признаки в адресе' : 'Назначение не установлено';
    const summary = document.createElement('p'); summary.textContent = value.conclusion;
    const host = document.createElement('p'); host.className = 'muted'; host.textContent = `Домен: ${value.hostname}`;
    result.append(title, summary, host);
    if (value.route) { const route = document.createElement('p'); route.textContent = 'Сохранённый маршрут: ' + value.route.join(' → '); result.append(route); }
    if (value.evidence.length) {
      const heading = document.createElement('strong'); heading.textContent = 'Наблюдения в адресе';
      const list = document.createElement('ul');
      for (const signal of value.evidence) { const li = document.createElement('li'); li.textContent = signal; list.append(li); }
      result.append(heading, list);
    }
    const note = document.createElement('p'); note.className = 'muted'; note.textContent = 'Проверка доступной страницы…'; result.append(note);
    const details = document.createElement('details'), summaryNode = document.createElement('summary'), pre = document.createElement('pre');
    summaryNode.textContent = 'JSON результата'; pre.textContent = JSON.stringify(value, null, 2); details.append(summaryNode, pre); result.append(details);
    if (value.status === 'authored_demo_route') {note.textContent = 'Учебный .test-адрес не открывался · 0 реальных переходов.'; return;}
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 19000);
    try {
      const response = await fetch(ONLINE_API, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({url:value.url}), signal:controller.signal});
      const page = await response.json();
      if (!response.ok) throw new Error(page.error || `Сервер ответил ${response.status}`);
      const verdict = summarizeFetched(page);
      title.textContent = verdict.title;
      summary.textContent = verdict.explanation;
      note.textContent = page.destination_verified ? 'Конечная страница прочитана сервером · оценка только доступного HTML/текста.' : 'Конечную страницу не удалось прочитать.';
      const routeTitle = document.createElement('strong'); routeTitle.textContent = 'Реальная цепочка переходов';
      const routeList = document.createElement('ol');
      for (const hop of page.route) {const item=document.createElement('li'); item.textContent=`HTTP ${hop.status} · ${hop.url}`; routeList.append(item);}
      result.insertBefore(routeTitle, details); result.insertBefore(routeList, details);
      const final = document.createElement('p'); final.textContent = `Конечный адрес: ${page.final_url}`; result.insertBefore(final, details);
      if (page.destination_verified && page.excerpt) {
        const excerpt = document.createElement('blockquote'); excerpt.textContent = page.excerpt.slice(0, 450); result.insertBefore(excerpt, details);
      }
      pre.textContent = JSON.stringify({address:value, online:{...page, excerpt:page.excerpt?.slice(0,1000)}, interpretation:verdict}, null, 2);
    } catch (error) {
      note.textContent = `Серверная проверка не завершена: ${error.name === 'AbortError' ? 'превышено время ожидания' : error.message}. Показаны только признаки адреса; конечная страница не проверена.`;
    } finally {clearTimeout(timeout);}
  } catch (error) { result.textContent = error.message; }
});

document.querySelectorAll('[data-url-example]').forEach(button => button.addEventListener('click', () => {
  input.value = button.dataset.urlExample; form.requestSubmit();
}));
