import {checkUrlInput} from './url-score.mjs';

const form = document.getElementById('url-form');
const input = document.getElementById('url-input');
const result = document.getElementById('url-result');

form.addEventListener('submit', event => {
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
    const note = document.createElement('p'); note.className = 'muted'; note.textContent = 'Запрос к этому сайту не выполнялся · 0 переходов · результат не является проверкой безопасности.'; result.append(note);
    const details = document.createElement('details'), summaryNode = document.createElement('summary'), pre = document.createElement('pre');
    summaryNode.textContent = 'JSON результата'; pre.textContent = JSON.stringify(value, null, 2); details.append(summaryNode, pre); result.append(details);
  } catch (error) { result.textContent = error.message; }
});

document.querySelectorAll('[data-url-example]').forEach(button => button.addEventListener('click', () => {
  input.value = button.dataset.urlExample; form.requestSubmit();
}));
