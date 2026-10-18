# ClauseGuard — submission package

*Clarity in every clause, confidence in every claim.*

FinTechathon 2026 Shenzhen · International Track · Topic D (AI Insurance Assistant)

**Team:** Bunga Laelatul Muna, Izra, Wan Sabrina — Institut Teknologi Sepuluh Nopember, Indonesia

| | |
|---|---|
| Live web app | https://clauseguard-red.vercel.app (the backend runs on the team's machine; when it is off, the site replays recorded runs and says so) |
| Source code | https://github.com/bungagana/clauseguard |
| Demo video | link in the submission email |

## What ClauseGuard does

An insurance assistant that reads the customer's own policies, answers coverage questions with the clause that decides them, prepares the claim from the customer's documents in the insurer's own form, submits it after the customer confirms, and brings the insurer's decision back to the chat. Every action runs inside permission tiers enforced in code; money and identity changes are never executed by the agent.

## Files in this folder

| File | Checklist item |
|---|---|
| `1_Technical_Documentation.docx` | Technical documentation: architecture, core method, security design |
| `2_Presentation_Deck.pptx` | Presentation deck, 8 slides, under 10 minutes (speaker notes included) |
| `3_Video_Script.md` | Script of the demo video |
| `4_Source_Code_ClauseGuard.zip` | Source code snapshot (same as the repository, without secrets and third-party data) |
| `5_Security_Self_Assessment.docx` | Permission tiers, threat model, test results, known risks |
| `6_Execution_Evidence_Index.docx` | Index of the evidence below and how to reproduce each file |
| `evidence/` | Sandbox operation logs and evaluation reports (see the index) |

The `.docx` files are rendered from the Markdown sources in `clauseguard/docs/`; the deck is built from `clauseguard/docs/DECK.md`.

## Run it yourself

```bash
git clone https://github.com/bungagana/clauseguard.git && cd clauseguard
cd clauseguard && pip install -r requirements.txt && python scripts/serve.py --fresh      # backend, http://127.0.0.1:8000
cd ../clauseguard-web && npm install && npm run dev                                         # web app, http://localhost:3000
```

No API key is needed: without one, every step runs on its deterministic fallback. Tests: `python -m pytest -q` in `clauseguard/`. Full instructions are in the repository README.

## Key evidence

| Claim | Where |
|---|---|
| A complete sandbox operation: four documents uploaded, form prepared, claim confirmed, approved at the desk, decision returned | `evidence/claims_desk_run.md` |
| 33 scripted claim scenarios pass | `evidence/task_report.md` |
| 0 of 27 attacks had an effect; 0 of 15 benign requests blocked | `evidence/adversarial_report.md` |
| 84.6 % accuracy and 1.4 % fabricated denials on a public benchmark | `evidence/bench_report.md` |
| Hash-chained audit log of a clean run | `evidence/audit_log_scripted_tasks_clean.jsonl` (`python scripts/verify_audit.py`) |

## What is simulated

The insurer is a sandbox: claims are filed into our own claims desk, not a real insurer. The three personas and their policies are synthetic; wordings are modelled on public insurer documents. Public datasets (CMS plans, InsuranceQA, UK ombudsman decisions, Indonesian product summaries) are downloaded by script and are not redistributed here.
