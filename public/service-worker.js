// 発注スキャン集計 - Service Worker
// オフライン対応とキャッシュ管理

const CACHE_NAME = 'order-scan-v1';
const RUNTIME_CACHE = 'order-scan-runtime';

// キャッシュするリソース
const STATIC_RESOURCES = [
  '/',
  '/app.js',
  '/styles.css',
  '/manifest.webmanifest',
  '/icons/icon-192.png',
  '/icons/icon-512.png',
  'https://cdn.tailwindcss.com',
  'https://cdn.jsdelivr.net/npm/@fortawesome/fontawesome-free@6.4.0/css/all.min.css',
  'https://cdn.jsdelivr.net/npm/axios@1.6.0/dist/axios.min.js',
  'https://cdn.jsdelivr.net/npm/tesseract.js@5/dist/tesseract.min.js'
];

// インストール時
self.addEventListener('install', (event) => {
  console.log('[Service Worker] インストール中...');
  
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then((cache) => {
        console.log('[Service Worker] 静的リソースをキャッシュ');
        return cache.addAll(STATIC_RESOURCES.map(url => new Request(url, { cache: 'reload' })));
      })
      .catch((error) => {
        console.error('[Service Worker] キャッシュエラー:', error);
      })
  );
  
  self.skipWaiting();
});

// アクティベーション時
self.addEventListener('activate', (event) => {
  console.log('[Service Worker] アクティベート中...');
  
  event.waitUntil(
    caches.keys().then((cacheNames) => {
      return Promise.all(
        cacheNames
          .filter((cacheName) => {
            return cacheName !== CACHE_NAME && cacheName !== RUNTIME_CACHE;
          })
          .map((cacheName) => {
            console.log('[Service Worker] 古いキャッシュを削除:', cacheName);
            return caches.delete(cacheName);
          })
      );
    })
  );
  
  self.clients.claim();
});

// フェッチ時（キャッシュ戦略）
self.addEventListener('fetch', (event) => {
  const { request } = event;
  const url = new URL(request.url);
  
  // APIリクエストはネットワーク優先
  if (url.pathname.startsWith('/api/')) {
    event.respondWith(networkFirst(request));
    return;
  }
  
  // 外部CDNリソースはキャッシュ優先
  if (url.origin !== location.origin) {
    event.respondWith(cacheFirst(request));
    return;
  }
  
  // その他の静的リソースはキャッシュ優先
  event.respondWith(cacheFirst(request));
});

// キャッシュ優先戦略
async function cacheFirst(request) {
  const cache = await caches.open(CACHE_NAME);
  const cached = await cache.match(request);
  
  if (cached) {
    console.log('[Service Worker] キャッシュから取得:', request.url);
    return cached;
  }
  
  try {
    const response = await fetch(request);
    
    if (response && response.status === 200) {
      // ランタイムキャッシュに保存
      const runtimeCache = await caches.open(RUNTIME_CACHE);
      runtimeCache.put(request, response.clone());
    }
    
    return response;
  } catch (error) {
    console.error('[Service Worker] フェッチエラー:', error);
    
    // ランタイムキャッシュから取得を試行
    const runtimeCache = await caches.open(RUNTIME_CACHE);
    const runtimeCached = await runtimeCache.match(request);
    
    if (runtimeCached) {
      return runtimeCached;
    }
    
    // オフラインページを返す（オプション）
    if (request.destination === 'document') {
      return new Response(
        '<html><body><h1>オフラインです</h1><p>インターネット接続を確認してください。</p></body></html>',
        { headers: { 'Content-Type': 'text/html' } }
      );
    }
    
    throw error;
  }
}

// ネットワーク優先戦略
async function networkFirst(request) {
  try {
    const response = await fetch(request);
    
    if (response && response.status === 200) {
      const cache = await caches.open(RUNTIME_CACHE);
      cache.put(request, response.clone());
    }
    
    return response;
  } catch (error) {
    console.error('[Service Worker] ネットワークエラー:', error);
    
    // キャッシュから取得を試行
    const cache = await caches.open(RUNTIME_CACHE);
    const cached = await cache.match(request);
    
    if (cached) {
      return cached;
    }
    
    throw error;
  }
}

// バックグラウンド同期（オプション）
self.addEventListener('sync', (event) => {
  console.log('[Service Worker] バックグラウンド同期:', event.tag);
  
  if (event.tag === 'sync-orders') {
    event.waitUntil(syncOrders());
  }
});

async function syncOrders() {
  // IndexedDBから未送信データを取得して送信
  // この機能はapp.jsのprocessQueuedOrders()と連携
  console.log('[Service Worker] 未送信データを同期中...');
}

// プッシュ通知（将来の拡張用）
self.addEventListener('push', (event) => {
  console.log('[Service Worker] プッシュ通知受信:', event);
  
  const options = {
    body: event.data ? event.data.text() : '新しい通知があります',
    icon: '/icons/icon-192.png',
    badge: '/icons/icon-192.png',
    vibrate: [200, 100, 200]
  };
  
  event.waitUntil(
    self.registration.showNotification('発注スキャン集計', options)
  );
});

// 通知クリック時
self.addEventListener('notificationclick', (event) => {
  console.log('[Service Worker] 通知クリック:', event);
  
  event.notification.close();
  
  event.waitUntil(
    clients.openWindow('/')
  );
});
