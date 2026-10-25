import {test} from 'node:test';
import assert from 'node:assert/strict';
import {parseTarget, publicIPv4, inspectUrl, pinnedLookup} from './inspector.mjs';

test('pinned lookup handles both Node single and all-address modes', async () => {
  const lookup = pinnedLookup('1.1.1.1');
  const single = await new Promise((resolve, reject) => lookup('safe.example.org', {}, (error, address, family) => error ? reject(error) : resolve({address, family})));
  const all = await new Promise((resolve, reject) => lookup('safe.example.org', {all: true}, (error, addresses) => error ? reject(error) : resolve(addresses)));
  assert.deepEqual(single, {address: '1.1.1.1', family: 4});
  assert.deepEqual(all, [{address: '1.1.1.1', family: 4}]);
});

test('private and reserved destinations are denied', () => {
  for (const address of ['127.0.0.1','10.0.0.1','172.17.0.1','192.168.1.1','169.254.169.254','100.64.0.1','192.0.2.1','203.0.113.1']) assert.equal(publicIPv4(address), false);
  assert.equal(publicIPv4('1.1.1.1'), true);
  for (const url of ['http://127.0.0.1','http://[::1]','http://localhost','http://x.local','http://user:pass@example.org','http://example.org:8080']) assert.throws(() => parseTarget(url));
});

test('each redirect hop is resolved and final visible text is returned', async () => {
  const visited = [];
  const result = await inspectUrl('https://go.example.org/go', {
    resolve: async host => {visited.push(host); return '1.1.1.1';},
    request: async url => url.hostname === 'go.example.org'
      ? {status: 302, location: 'https://play.example.org/casino'}
      : {status: 200, contentType: 'text/html', body: '<title>Casino</title><script>secret</script><p>Играй в казино: забирай бонус</p>'},
  });
  assert.deepEqual(visited, ['go.example.org','play.example.org']);
  assert.equal(result.destination_verified, true);
  assert.equal(result.route.length, 2);
  assert.match(result.excerpt, /Играй в казино/);
  assert.doesNotMatch(result.excerpt, /secret/);
});

test('redirect to private address is denied before making another request', async () => {
  let count = 0;
  await assert.rejects(() => inspectUrl('https://go.example.org/go', {
    resolve: async () => '1.1.1.1',
    request: async () => {count++; return {status: 302, location: 'http://127.0.0.1/latest/meta-data'};},
  }));
  assert.equal(count, 1);
});

test('DNS answer is checked even through injectable resolver', async () => {
  await assert.rejects(() => inspectUrl('https://go.example.org/', {resolve: async () => '169.254.169.254', request: async () => {throw new Error('should not call');}}));
});
