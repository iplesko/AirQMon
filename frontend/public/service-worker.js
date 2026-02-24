const SW_VERSION = new URL(self.location.href).searchParams.get('v') || 'dev'
const CACHE_NAME = `airqmon-cache-${SW_VERSION}`
const APP_SHELL = ['/', '/index.html', '/manifest.webmanifest']

function isCacheableResponse(response) {
  return Boolean(response && response.status === 200)
}

async function putInCache(request, response) {
  if (!isCacheableResponse(response)) return

  const requestUrl = new URL(request.url)
  if (requestUrl.origin !== self.location.origin) return
  if (requestUrl.pathname === '/service-worker.js') return

  const cache = await caches.open(CACHE_NAME)
  await cache.put(request, response.clone())
}

async function networkFirst(request, fallbackToRoot) {
  try {
    const networkResponse = await fetch(request)
    await putInCache(request, networkResponse)
    return networkResponse
  } catch (error) {
    const cachedResponse = await caches.match(request)
    if (cachedResponse) {
      return cachedResponse
    }

    if (fallbackToRoot) {
      const rootFallback = await caches.match('/')
      if (rootFallback) {
        return rootFallback
      }
    }

    throw error
  }
}

async function cacheFirst(request) {
  const cachedResponse = await caches.match(request)
  if (cachedResponse) {
    return cachedResponse
  }

  const networkResponse = await fetch(request)
  await putInCache(request, networkResponse)
  return networkResponse
}

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(APP_SHELL))
  )
  self.skipWaiting()
})

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(
          keys
            .filter((key) => key !== CACHE_NAME)
            .map((key) => caches.delete(key))
        )
      )
      .then(() => self.clients.claim())
  )
})

self.addEventListener('fetch', (event) => {
  if (event.request.method !== 'GET') {
    return
  }

  const request = event.request
  const requestUrl = new URL(request.url)
  if (requestUrl.origin === self.location.origin && requestUrl.pathname.startsWith('/api/')) {
    // Let API requests bypass the service worker and hit the network directly.
    return
  }

  if (request.mode === 'navigate') {
    event.respondWith(networkFirst(request, true))
    return
  }

  if (requestUrl.origin === self.location.origin && requestUrl.pathname === '/service-worker.js') {
    event.respondWith(fetch(request))
    return
  }

  event.respondWith(cacheFirst(request))
})

self.addEventListener('push', (event) => {
  let payload = {
    title: 'AirQMon Alert',
    body: 'New air quality alert.',
    url: '/',
  }

  if (event.data) {
    try {
      payload = { ...payload, ...event.data.json() }
    } catch (error) {
      payload = { ...payload, body: event.data.text() || payload.body }
    }
  }

  event.waitUntil(
    self.registration.showNotification(payload.title, {
      body: payload.body,
      tag: payload.type || 'airqmon-alert',
      icon: '/icons/notification-icon-192.png',
      badge: '/icons/notification-badge-72.png',
      data: { url: payload.url || '/' },
    })
  )
})

self.addEventListener('notificationclick', (event) => {
  event.notification.close()
  const targetUrl = event.notification?.data?.url || '/'

  event.waitUntil(
    self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then((clients) => {
      for (const client of clients) {
        if ('focus' in client) {
          if ('navigate' in client) {
            client.navigate(targetUrl)
          }
          return client.focus()
        }
      }
      if (self.clients.openWindow) {
        return self.clients.openWindow(targetUrl)
      }
      return undefined
    })
  )
})
