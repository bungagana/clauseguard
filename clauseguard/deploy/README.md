# Deployment runbook

Backend: Hugging Face Docker Space or Render (Docker). Web: Vercel. Database: Postgres (Supabase) for the audit chain, conversation history and the claims/tickets mirror; see `storage.md`.
Nothing here needs a credit card. Deploys are manual pushes; no workflow holds a deploy token.

## Runtime data

The Space is built from files assembled by `deploy/hf-space/assemble.sh` (git-tracked and untracked-not-ignored files only).
Verified by running the app from that assembled copy in a clean venv: `/health`, `/login`, `/policies`, `/chat`, `/entitlement/plans`, `/audit/verify` all work for rizky, santoso and dewi with no API key and no `.env`.

| Path | Needed at runtime | In git | In Space |
|---|---|---|---|
| `clauseguard/`, `ui/` | yes | yes | yes |
| `data/personas/policies/*.json` | yes (seed + policies) | yes | yes |
| `data/extracted/*.json` | yes (catalogue) | yes | yes |
| `data/real/cms_plans_py2026.csv`, `cms_rates_py2026.csv`, `catalogue_id.json` | yes (plan selection) | yes | yes |
| `data/real/icd10cm_codes.txt` | yes (ICD-10 coder) | yes | yes |
| `data/real/*.jsonl`, `*.csv` (kff, fos, sample200), `manifest.json` | no | yes | yes (small) |
| `data/adversarial/pdf`, `data/demo`, `data/policies/real` | demo uploads / provenance labels | yes | yes |
| `data/real/riplay/`, `data/real/raw/` | no (only provenance strings and offline research) | no (ignored) | no |
| `data/real/insuranceqa_questions.jsonl` | no | no (ignored) | no |
| `data/sandbox.sqlite`, `data/history.sqlite` | created on first request (seeded) | no | created at boot |
| `evidence/audit_log.jsonl` | created at boot; image starts a fresh hash chain | yes (dev log) | no |
| `data/benchmark`, `data/scripted_tasks`, `tests`, `bench`, `docs` | no (offline evaluation) | yes | no |
| e5 ONNX files (`icd10_embed.py`) | optional; coder degrades without them | no | no |
| `.env` | never | no | never (excluded) |

Nothing in the data folder is missing for the three personas, so no fetch step is needed at build time. `scripts/fetch_real_data.py` is only for local research data.

Findings from the fresh-copy test:
- `requirements.txt` lacks `python-multipart`, which FastAPI needs for the upload routes; the app crashes at import without it. Fixed by the new `requirements-runtime.txt`.
- `requirements.txt` pulls `sentence-transformers` (PyTorch) and `streamlit`, which the backend does not import. They are left out of the image.

Dependency files: `requirements-runtime.txt` (image), `requirements-ci.txt` (runtime plus test and bench deps). `requirements.txt` is unchanged.

## Environment variables

Set in Space settings, "Variables and secrets". All optional: without them the app starts and uses deterministic fallbacks.

| Name | Kind | Purpose |
|---|---|---|
| `GEMINI_API_KEYS` | secret | comma separated key pool; without it planner, fact binder and explainer use rule-based fallbacks |
| `CG_ADMIN_TOKEN` | secret | enables `/admin/kill` and `/backoffice/*` (403 when unset) |
| `CG_STORAGE=postgres`, `DATABASE_URL` | secret | persistence in Postgres (audit chain, history, claims and tickets mirror); omit both to stay on local files/SQLite |
| `CG_ENV` | variable | `production` (set in the image) |
| `PORT` | variable | defaults to 7860, which the Space requires |

### Accounts

With `CG_AUTH=supabase` the backend closes the open persona and guest login. Every request starts from a Supabase access token, and the backend asks Supabase (`/auth/v1/user`) who owns it and whether the email is confirmed. Set on the backend: `CG_AUTH=supabase`, `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY`. Set on the web service before it builds: `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`. In Supabase: Authentication, Providers, Email with "Confirm email" on; Authentication, URL Configuration, Site URL set to the web address. The three sandbox customers are three confirmed Supabase users whose emails are listed in `CG_DEMO_ACCOUNTS`; any other account starts with no policies.

The container filesystem is ephemeral: the sandbox database and uploads reset on every restart or rebuild. With `CG_STORAGE=postgres` the audit chain, conversation history and the claims/tickets mirror survive restarts; without it everything stays local, which is enough for a demo.

## Backend: create the Space

1. huggingface.co, New Space, SDK Docker (blank), name e.g. `clauseguard`, visibility Public (needed for the Vercel rewrite and keepalive).
2. Space settings, Variables and secrets: add `GEMINI_API_KEYS` and `CG_ADMIN_TOKEN` as secrets.
3. Assemble and push (Git Bash, from the repo root):

```bash
bash clauseguard/deploy/hf-space/assemble.sh /tmp/space
cd /tmp/space
git init -b main && git add -A && git commit -m "deploy"
git remote add space https://huggingface.co/spaces/<user>/clauseguard
git push --force space main
```

Use your HF username and an access token with write scope as the password when prompted. Later deploys repeat the same commands.

4. Wait for the build (about 3 to 5 minutes). Open `https://<user>-clauseguard.hf.space/health`; expect `{"ok":true,...}`.

## Web: Vercel

1. Import the GitHub repo in Vercel. Set Root Directory to `clauseguard-web`. Framework Next.js is detected; no `vercel.json` is needed.
2. Environment variable: `BACKEND_URL=https://<user>-clauseguard.hf.space` (no trailing slash needed). `next.config.mjs` reads `BACKEND_URL`, then `NEXT_PUBLIC_API_URL`, then `http://localhost:8000`.
3. Deploy. Redeploy after changing the variable, since rewrites are resolved at build time.

## Keepalive (review window only)

GitHub repo, Settings, Secrets and variables, Actions, Variables: add `SPACE_URL=https://<user>-clauseguard.hf.space`. `.github/workflows/keepalive.yml` then calls `/health` every 10 minutes and skips quietly when the variable is unset. GitHub pauses scheduled workflows after 60 days of repository inactivity and may delay runs under load; disable the workflow after judging.

## CI

`.github/workflows/ci.yml` runs on every push and pull request: backend `pytest -q -x` (offline, empty API keys) and web `npm ci`, `tsc --noEmit`, `next lint`. Two tests are deselected because they depend on the platform (byte-identical PDF regeneration and a float equality in a Wilson interval): `test_generator_is_deterministic` and `test_wilson_interval_known_values`.

## Pre-demo checklist

1. `GET /health` returns `ok: true` and `kill_switch: false`.
2. `GET /audit/verify` (with a session token) returns `chain_ok: true`.
3. `CG_ADMIN_TOKEN` is set; `/backoffice/tickets` with a wrong token returns 401/403, with the right token 200.
4. `GET /system/status` shows `configured: true` and the web status badge shows Gemini available; if not, check `GEMINI_API_KEYS`.
5. Log in as each persona on the Vercel site and send one chat message.

## If the Space sleeps

Free Spaces sleep after about 48 hours without traffic. Open the Space URL (or run the keepalive workflow via "Run workflow") and wait 30 to 60 seconds for the restart. Sandbox data is re-seeded on boot. If it shows a build error, open the Logs tab; a Factory reboot from the Space menu rebuilds it.

## Local container check

With Docker running: `docker build -t clauseguard clauseguard && docker run --rm -p 7860:7860 clauseguard`, then `curl localhost:7860/health`.
