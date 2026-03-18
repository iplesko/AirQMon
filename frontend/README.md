# Frontend

## Overview

The frontend is a React + Vite single-page application written in TypeScript.
It fetches measurements from the backend API and visualizes them with Chart.js.

Current frontend features:

- Current CO2, temperature, and humidity display
- Historical charts with selectable time ranges
- Point-limited mobile portrait queries for lighter chart payloads
- Config modal for alert thresholds, display brightness, and night mode
- Browser push notification enable/disable controls
- Theme toggle
- PWA install support

## Access Control Assumption

This frontend is expected to be deployed behind Cloudflare Access (Zero Trust) protection.
The Config modal logout button intentionally redirects to `/cdn-cgi/access/logout` to end the Cloudflare Access session and force re-authentication.

## Build

```bash
npm install
npm run build
```

The build outputs to `dist/` which the backend serves.

## Environment Setup

Copy the sample env file and set your real backend API address:

```bash
cd frontend
cp .env.development.example .env.development.local
```

Then edit `.env.development.local` and set:

```env
DEV_API_PROXY_TARGET=http://your-backend-host:8000
```

## Development (Recommended)

Run the Vite dev server for HMR and proxying to the backend API. In one terminal run:

```bash
cd frontend
npm install
npm run dev
```

## API Proxy

The frontend proxies `/api` during development.

- Default target: `http://localhost:8000`
- Override with `DEV_API_PROXY_TARGET`
- See `vite.config.ts`

## PWA

The frontend is now configured as a baseline Progressive Web App:

- `public/manifest.webmanifest` defines install metadata.
- `public/service-worker.js` provides basic app-shell and runtime caching.
- `src/main.tsx` registers the service worker in production builds.

To test installability:

```bash
cd frontend
npm run build
npm run preview
```

Then open the preview URL from your phone (same network) and use browser "Add to Home Screen".

Production note: PWA install/service worker requires HTTPS in normal browser contexts.
