const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const root = path.join(__dirname, '../public');
function snapshot() {
  const values = new Map();
  const ctx = {document: {cookie: 'mt_snapshot=alice'}, Date, localStorage: {
    getItem: k => values.get(k) ?? null, setItem: (k,v) => values.set(k,v), removeItem: k => values.delete(k)
  }};
  vm.createContext(ctx);
  vm.runInContext(fs.readFileSync(path.join(root, 'snapshot.js'), 'utf8') + ';globalThis.store = dashboardSnapshot;', ctx);
  return {ctx, values, store: ctx.store};
}
test('snapshot: sessione, account, scadenza e uscita', () => {
  const {ctx, values, store} = snapshot();
  store.save({auth_required: true, wealth: {cash: 12}});
  assert.equal(store.read().data.wealth.cash, 12);
  ctx.document.cookie = 'mt_snapshot=bob';
  assert.equal(store.read(), null);
  assert.equal(values.size, 0);
  store.save({auth_required: true});
  ctx.document.cookie = '';
  assert.equal(store.read(), null);
  ctx.document.cookie = 'mt_snapshot=alice';
  store.save({auth_required: false});
  assert.equal(values.size, 0);
  store.save({auth_required: true});
  const saved = JSON.parse(values.get(store.key));
  values.set(store.key, JSON.stringify({...saved, at: Date.now() - 8*86400000}));
  assert.equal(store.read(), null);
  values.set(store.key, '{bad');
  assert.equal(store.read(), null);
  store.save({auth_required: true}); store.clear();
  assert.equal(store.read(), null);
});
test('snapshot: storage negato non blocca l’app', () => {
  const {ctx, store} = snapshot();
  ctx.localStorage.getItem = ctx.localStorage.setItem = ctx.localStorage.removeItem = () => { throw Error('denied'); };
  assert.equal(store.read(), null);
  assert.doesNotThrow(() => store.save({auth_required: true}));
});
test('service worker: cache solo pubblica, API e scritture escluse', async () => {
  const handlers = {}, cached = [];
  const ctx = {URL, self: {location: {origin: 'https://app.test'}, clients: {claim() {}}, addEventListener: (name, cb) => handlers[name] = cb},
    caches: {open: async () => ({addAll: files => cached.push(...files), match: async () => 'cached-shell'})}};
  vm.runInNewContext(fs.readFileSync(path.join(root, 'sw.js'), 'utf8'), ctx);
  await new Promise((resolve, reject) => handlers.install({waitUntil: p => p.then(resolve, reject)}));
  assert(cached.includes('/index.html'));
  for (const file of cached) assert(fs.existsSync(path.join(root, file === '/' ? 'index.html' : file)));
  for (const [url, method] of [['/api/dashboard','GET'], ['/api/session','GET'], ['/api/login','POST'], ['/index.html','POST'], ['https://other.test/','GET']]) {
    let intercepted = false;
    handlers.fetch({request: {url: new URL(url, 'https://app.test').href, method}, respondWith() {intercepted = true;}});
    assert.equal(intercepted, false, url);
  }
  let response;
  handlers.fetch({request: {url: 'https://app.test/', method:'GET'}, respondWith: p => response = p});
  assert.equal(await response, 'cached-shell');
});
