# ClauseGuard — web frontend

A chat-first web interface for ClauseGuard: it reads your own insurance policies and tells
you, in plain language, what is covered, what you are owed, and how to claim it — every
answer backed by the exact clause. Built for students and everyday policyholders, not
insurance professionals.

This is the frontend only. It talks to the existing ClauseGuard Python backend
(`clauseguard/sandbox/api.py` in the sibling `clauseguard` repository) over HTTP and does not
duplicate any of its logic: every verdict, deadline, payable amount and clause quote shown
here comes straight from that API.

## Stack

Next.js 14 (App Router, TypeScript), Tailwind CSS, hand-rolled shadcn-style UI primitives on
Radix, framer-motion for message/card transitions, lucide-react for icons.

## Run locally

```bash
npm install
npm run dev
```

Open http://localhost:3000. By default the app talks to a backend at
`http://localhost:8000`.

### Pointing it at a running backend

Copy `.env.example` to `.env.local` and set `NEXT_PUBLIC_API_URL` to wherever the backend is
reachable:

```bash
copy .env.example .env.local   # Windows
# or: cp .env.example .env.local
```

```
NEXT_PUBLIC_API_URL=http://localhost:8000
```

To actually have a backend to point at, from the sibling `clauseguard` repository:

```bash
cd ../clauseguard
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt
python scripts/serve.py --fresh --port 8000
```

Browser calls never hit the backend directly. The sandbox API ships no CORS headers, so
`next.config.mjs` proxies every call through this app's own origin at `/api/cg/*` (a Next.js
`rewrites()` rule to `NEXT_PUBLIC_API_URL`). This also means the backend URL never needs to be
reachable from the browser — only from wherever this Next.js app is running (your machine in
dev, or Vercel's servers in production).

## Deploying to Vercel

1. Push this `clauseguard-web/` folder to a Git repository (or import it directly from your
   local clone).
2. In the Vercel dashboard: **Add New Project** → import the repo → set the **Root Directory**
   to `clauseguard-web` if the Python backend lives alongside it in the same repo.
3. Add an environment variable: `NEXT_PUBLIC_API_URL` → the public URL of a reachable
   ClauseGuard backend (if you have one deployed), or leave it unset/pointed at localhost if
   you don't — the site still works via the offline fallback described below.
4. Deploy. Vercel auto-detects Next.js; no `vercel.json` is needed.

Or via the CLI from inside `clauseguard-web/`:

```bash
npm i -g vercel
vercel link
vercel env add NEXT_PUBLIC_API_URL
vercel --prod
```

## Offline fallback (why the deployed site still works without a live backend)

Most deployments of this frontend — including the default Vercel deployment, since the
Python backend isn't typically hosted publicly — won't have a reachable backend. The app
detects this automatically:

- On load, it calls `GET /api/cg/health` with a short timeout. No toggle, no setup.
- If the backend doesn't answer, a small banner appears ("Demo backend is offline — showing
  recorded examples") and the three **demo scenes** (reachable from the composer's sparkle
  icon) replay real, pre-recorded exchanges captured from an actual running backend —
  including the confirm-before-submit flow, the hidden-text invoice attack, and a
  misrepresentation refusal — entirely client-side, no network calls.
- Typing a question that exactly matches one of those recorded exchanges still gets its real
  recorded answer; anything else gets a friendly message pointing at the demo scenes instead
  of a guess.
- The fixtures live in `lib/fixtures.generated.ts` (recorded 2026-10-11) and `lib/fixtures.ts`
  (normalizes and re-exports them). They are not hand-written: they were captured by running
  the real backend locally and saving its actual JSON responses.

## Project layout

```
app/                     App Router shell (layout, page, global styles)
components/chat/         The whole product: top bar, composer, message list, panels
components/chat/cards/   Rich content blocks (verdict, allocation, timeline, readiness, ...)
components/ui/           Button/Card/Dialog/Sheet/... primitives (Radix + Tailwind)
lib/api.ts               Typed fetch client for every backend endpoint used
lib/fixtures*.ts         Offline fallback data
lib/types.ts             TypeScript types mirroring the backend's real JSON shapes
```

## Notes on the backend's optional LLM

The backend's agent loop can optionally call an LLM (Gemini) for fact-binding and wording;
every step has a deterministic fallback, so the loop works with or without an API key. In
practice this means two live runs of the exact same message can occasionally come back with
slightly different (still correct) verdicts or wording depending on whether that call
succeeded — the UI renders whatever shape comes back either way, since every card type is
driven by the response's own structured fields, not by assumptions baked into the frontend.
