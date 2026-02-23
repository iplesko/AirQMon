# Frontend

## Overview

The frontend is a React + Vite single-page application written in TypeScript.
It fetches measurements from the backend API (`/api/latest` and `/api/data`) and visualizes them with Chart.js.

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

The frontend is configured to proxy `/api` to `http://localhost:8000` during development (see `vite.config.ts`).
