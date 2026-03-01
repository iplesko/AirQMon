export function getAirqmonServiceWorkerUrl(): string {
  return `/service-worker.js?v=${encodeURIComponent(__AIRQMON_BUILD_ID__)}`
}

export async function registerAirqmonServiceWorker(): Promise<ServiceWorkerRegistration> {
  const registration = await navigator.serviceWorker.register(getAirqmonServiceWorkerUrl(), {
    updateViaCache: 'none',
  })
  await registration.update()
  return registration
}
