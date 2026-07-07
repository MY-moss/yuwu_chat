const CACHE_NAME = 'tavern-cache-v2.2.0.8';
const CACHE_ASSETS = [
    // [AUDIT-Q28] 未缓存主 ES Module 文件（如 app.js/chat.js/rpg.js），无离线能力
    '/',
    '/static/style.css',
    '/static/feedback.css',
    '/static/feedback.js',
    '/static/manifest.json'
];

self.addEventListener('install', (event) => {
    event.waitUntil(
        caches.open(CACHE_NAME).then((cache) => {
            return cache.addAll(CACHE_ASSETS);
        })
    );
    self.skipWaiting();
});

self.addEventListener('activate', (event) => {
    event.waitUntil(
        caches.keys().then((cacheNames) => {
            return Promise.all(
                cacheNames.filter((name) => name !== CACHE_NAME).map((name) => {
                    return caches.delete(name);
                })
            );
        })
    );
    self.clients.claim();
});

self.addEventListener('fetch', (event) => {
    if (event.request.method !== 'GET') return;
    
    event.respondWith(
        caches.match(event.request).then((cachedResponse) => {
            const fetchPromise = fetch(event.request).then((networkResponse) => {
                const ct = networkResponse.headers.get('Content-Type') || '';
                if (networkResponse && networkResponse.status === 200 && ct.startsWith('text/html') === false) {
                    caches.open(CACHE_NAME).then((cache) => {
                        if (!event.request.url.includes('/api/') && 
                            !event.request.url.includes('.db') &&
                            !event.request.url.includes('.json')) {
                            cache.put(event.request, networkResponse.clone());
                        }
                    });
                }
                return networkResponse;
            }).catch(() => {
                if (cachedResponse) {
                    return cachedResponse;
                }
                return new Response('<div style="text-align:center;padding:40px;color:#e8ddd0;background:#1a1410;font-family:sans-serif;"><h2>🍺 云雾酒馆</h2><p style="color:#b8a898;">网络连接断开</p><p style="color:#b8a898;font-size:14px;">请检查网络连接后刷新页面</p></div>', {
                    headers: { 'Content-Type': 'text/html' }
                });
            });

            return cachedResponse || fetchPromise;
        })
    );
});