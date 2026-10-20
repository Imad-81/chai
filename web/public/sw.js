// Minimal PWA Service Worker for Chai Local Assistant
const CACHE_NAME = 'chai-pwa-v1';

self.addEventListener('install', (event) => {
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(self.clients.claim());
});

self.addEventListener('fetch', (event) => {
  // Pass API requests straight through
  if (event.request.url.includes('/api/')) {
    return;
  }
  // Network first with fallback
  event.respondWith(
    fetch(event.request).catch(() => caches.match(event.request))
  );
});
