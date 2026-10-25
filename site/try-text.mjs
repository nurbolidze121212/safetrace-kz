import {scoreText} from './text-score.mjs';
const form=document.getElementById('text-form'), input=document.getElementById('text-input'), result=document.getElementById('text-result');
const labels={low:'Низкий',medium:'Средний',high:'Высокий'};
form.addEventListener('submit',event=>{
  event.preventDefault(); result.replaceChildren();
  try {
    const value=scoreText(input.value);
    const title=document.createElement('h3'); title.textContent=value.sufficient?`${labels[value.level]} приоритет · ${value.value} / 100`:'Недостаточно данных для текстовой оценки';
    const info=document.createElement('p'); info.textContent=value.meaning;
    const list=document.createElement('ul');
    const names={gambling:'Игровая лексика',call:'Призыв',bonus:'Бонус',alternative:'Альтернативный контекст'};
    for(const signal of value.signals.slice(0,18)){const item=document.createElement('li');item.textContent=`${names[signal.kind]}: «${signal.quote}»`;list.append(item);}
    if(!value.signals.length){const item=document.createElement('li');item.textContent='Известных текстовых признаков не найдено. Содержимое ссылок не проверено.';list.append(item);}
    const details=document.createElement('details'),summary=document.createElement('summary'),pre=document.createElement('pre');summary.textContent='JSON результата';pre.textContent=JSON.stringify(value,null,2);details.append(summary,pre);
    result.append(title,info,list,details);
  } catch(error){result.textContent=error.message;}
});
document.querySelectorAll('[data-text-example]').forEach(button=>button.addEventListener('click',()=>{input.value=button.dataset.textExample;form.requestSubmit();}));
