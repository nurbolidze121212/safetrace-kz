import test from 'node:test';
import assert from 'node:assert/strict';
import {checkUrlInput} from '../../site/url-score.mjs';
import {summarizeFetched} from '../../site/online-url.mjs';

test('known authored route is explicitly marked as a synthetic saved example', () => {
  const result = checkUrlInput('https://go.safetrace.test/r/q7');
  assert.equal(result.status, 'authored_demo_route');
  assert.equal(result.destination_verified, false);
  assert.equal(result.links_opened, 0);
  assert.equal(result.route.at(-1), 'arena.safetrace.test');
});
test('arbitrary casino-like URL has only address signals, no destination claim', () => {
  const result = checkUrlInput('https://new-casino27.example/offer?ref=abc');
  assert.equal(result.status, 'address_signals');
  assert.equal(result.destination_verified, false);
  assert.equal(result.links_opened, 0);
  assert.ok(result.evidence.some(e => e.includes('Игровое слово')));
});
test('news and neutral links remain unverified', () => {
  for (const url of ['https://news.example/article/casino-warning', 'https://example.com/']) {
    const result = checkUrlInput(url);
    assert.equal(result.status, 'unverified');
    assert.equal(result.links_opened, 0);
  }
});
test('pasted message extracts URL, rejects credentials and non-HTTP schemes', () => {
  assert.equal(checkUrlInput('Пришло: https://example.com/offer?promo=X').hostname, 'example.com');
  for (const url of ['javascript:alert(1)', 'file:///secret', 'https://user:pass@example.com/']) assert.throws(() => checkUrlInput(url));
});
test('online text interpretation distinguishes promotion, warning and unreadable pages', () => {
  const base = {route:[{url:'https://x.org/',status:200}],final_url:'https://x.org/',destination_verified:true};
  assert.equal(summarizeFetched({...base,excerpt:'Играй в казино, регистрируйся и забирай бонус!'}).kind,'promotional');
  assert.equal(summarizeFetched({...base,excerpt:'Осторожно: реклама казино. Не играйте.'}).kind,'context');
  assert.equal(summarizeFetched({...base,excerpt:'Кафе открылось сегодня.'}).kind,'none_found');
  assert.equal(summarizeFetched({...base,destination_verified:false,excerpt:''}).kind,'unreadable');
});
