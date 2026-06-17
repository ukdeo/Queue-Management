# Pālo Queue Management — Frontend

Vite + React + TypeScript frontend for the Pālo queue management system.

## Tech Stack
- **Vite** — Build tool & dev server
- **React 18** — UI framework
- **TypeScript** — Type safety
- **Tailwind CSS v4** — Styling (via `@tailwindcss/vite` plugin)
- **Axios** — HTTP client
- **Lucide React** — Icons

## Setup

### 1. Install dependencies
```bash
npm install
```

### 2. Run the development server
```bash
npm run dev
```

The app will be available at `http://localhost:5173`.

> **Note:** The frontend proxies `/api/*` requests to `http://localhost:8000` (the backend). Make sure the backend is running first.

### 3. Build for production
```bash
npm run build
```

## Project Structure

```
frontend/
├── src/
│   ├── App.tsx                      # Root component (health check + routing)
│   ├── main.tsx                     # Entry point
│   ├── index.css                    # Global styles + Tailwind v4 import
│   ├── services/
│   │   └── api.ts                   # Axios API client
│   ├── pages/
│   │   ├── Setup.tsx                # Org + queue creation wizard
│   │   └── Dashboard.tsx            # Main dashboard with view switcher
│   └── components/
│       ├── JoinQueueView.tsx         # Customer-facing token join screen
│       ├── OperatorDashboard.tsx     # Operator queue management panel
│       └── DisplayBoard.tsx         # Public display board (full-screen)
├── index.html
├── vite.config.ts                   # Vite config with API proxy
├── package.json
└── tsconfig.json
```

## Views

| View | Path (in-app) | Description |
|------|--------------|-------------|
| Join Queue | `/` (Join tab) | Customers enter phone/email and get a token |
| Operator | Operator tab | Staff call next tokens, mark completions |
| Display Board | Display tab | Full-screen board for lobby monitors |
