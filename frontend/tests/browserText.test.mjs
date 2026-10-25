import test from 'node:test';
import assert from 'node:assert/strict';
import {scoreText} from '../../site/text-score.mjs';

test('browser triage exposes three levels and original quotations',()=>{
  for(const [text,level] of [['Играй в к@зино, бонус 200%!','high'],['Казино, бонус.','medium'],['Кафе: бонус за заказ.','low']]){
    const result=scoreText(text);assert.equal(result.level,level);
    for(const s of result.signals)assert.equal(text.slice(s.start,s.end),s.quote);
  }
});
test('warnings, KK negation, URL and emoji are not a verdict',()=>{
  for(const text of ['Казино емес. Тіркел.','Осторожно: казино обещает бонус. Не переходите.','🅰️ 🎰','https://casino.example/join'])assert.equal(scoreText(text).level,'low');
  assert.equal(scoreText('https://casino.example/join').sufficient,false);
  assert.equal(scoreText('К а з и н о: регистрируйся!').level,'high');
  assert.equal(scoreText('🎲 Играй в к🅰️зино!').level,'high');
});
