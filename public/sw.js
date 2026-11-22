/* Solo file pubblici: le API e i dati finanziari non entrano nella Cache API. */
const SHELL = 'mt-shell-v2';
const FILES = ['/', '/index.html', '/snapshot.js', '/vendor/chart.umd.min.js',
  '/vendor/dm-mono-400.ttf', '/vendor/dm-mono-500.ttf', '/vendor/plus-jakarta-sans-400.ttf', '/vendor/plus-jakarta-sans-500.ttf', '/vendor/plus-jakarta-sans-600.ttf', '/vendor/plus-jakarta-sans-800.ttf',
  '/manifest.webmanifest', '/logo-mark.svg', '/logo-mark-light.svg',
  '/glass-icon.webp', '/onde-saldo.jpg', '/caricamento.webp', '/vuoto.webp'];
self.addEventListener('install', event => {
  event.waitUntil(caches.open(SHELL).then(cache => cache.addAll(FILES)).then(() => self.skipWaiting()));
});
// Sostituisce anche il vecchio worker ancora aperto: la prossima apertura usa la nuova interfaccia.
self.addEventListener('activate', event => {
  event.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(k => k.startsWith('mt-shell-') && k !== SHELL)
    .map(k => caches.delete(k)))).then(() => self.clients.claim()));
});
self.addEventListener('fetch', event => {
  const url = new URL(event.request.url);
  if (event.request.method !== 'GET' || url.origin !== self.location.origin || !FILES.includes(url.pathname)) return;
  event.respondWith(caches.open(SHELL).then(async cache => {
    const cached = await cache.match(url.pathname);
    return cached || fetch(event.request);
  }));
});
