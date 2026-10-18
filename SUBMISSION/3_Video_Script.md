# ClauseGuard — demo video script

Length: 4 minutes. Recorded from the web app (`http://localhost:3000`) with the backend running. Narration is about 110 words per minute; cut a sentence rather than speed up. Show the product first; explain after.

## Before recording

1. Backend fresh: `cd clauseguard && python scripts/serve.py --fresh --release-kill-switch`
2. Web app: `cd clauseguard-web && npm run build && npm start` (no dev-server reloads during the take)
3. Browser 1440 px wide, light theme, bookmarks hidden. Open `http://localhost:3000/chat?mode=demo`, pick **Rizky**, click **New chat**.
4. Second tab: `http://localhost:3000/insurer`, back-office token already entered.
5. Have the four files from `clauseguard/data/demo/claim_docs/` ready to drag in.
6. Rehearse once with a stopwatch.

## Shots

| # | Time | What is on screen | Narration |
|---|---|---|---|
| 1 | 0:00–0:10 | Chat. Drag the four PDFs into the composer, type: *I was admitted for dengue on 25 September 2026 at RS Sehat Sentosa, discharged 28 September. Here are my hospital documents.* Send. | Four hospital documents. One sentence. |
| 2 | 0:10–0:40 | The reply appears: the Sompo claim form, filled, with the documents checklist all ticked. Scroll it slowly. Click **Preview** to show the PDF. | ClauseGuard read the invoice, the medical resume, the prescription and the lab results, matched them to Sompo's own document list, took the bill from the invoice, and laid out Sompo's claim form from Sompo's wording. Every field comes from the documents or from what Rizky said. Nothing has been sent. |
| 3 | 0:40–1:00 | Title card over the app: **ClauseGuard — the insurance agent that acts on your claim, and never guesses.** | This is ClauseGuard. It reads your own policies, answers with the clause that decides, prepares your claim, and sends it only after you confirm. |
| 4 | 1:00–1:35 | Back to chat. Click **How was this decided?** Show the clause quote, the facts used, the rules engine line. Open the **What if…** chip and flip one fact. | Decisions are not generated text. The policy is compiled into rules, a rules engine applies them, and the reply quotes the sentence that decided. Flip a fact and every answer is recomputed. |
| 5 | 1:35–2:05 | Click **Confirm and submit**. Reply with the claim number. Switch to the insurer tab: the claim is in the inbox with the form and four attachments. Type a note, click **Approve**. Back to the chat tab: "News from the insurer: … approved …" appears. | Sending needs one tap, bound to a one-time server token. The claim lands on the insurer's desk, a sandbox here, with the form and the files. A person decides, and the decision comes back to Rizky's chat. |
| 6 | 2:05–2:40 | New chat. Type: *Change my payout account to BCA 0123456789.* Show the refusal and the ticket. Then show the **Observe / Draft / Act** switch and, on the insurer tab, **Halt agent**; type a question in chat and show the paused reply. Release. | The agent cannot touch money or identity: there is no tool for it, so it opens a ticket for a person. The customer sets how far it may go. The insurer can halt it for everyone. Every step is in a tamper-evident log. |
| 7 | 2:40–3:10 | Open **Behind the answer**. Point at Conversation Agent, Fact Agent, Rules Engine, Guardian, Explainer, Audit trail. | Five agents read, bind facts and word the reply. Code decides and enforces: the rules engine, the permission guardian, the audit chain. The model never produces a verdict, an amount or a permission. |
| 8 | 3:10–3:40 | Slide with the benchmark chart and three numbers. | On a public insurance-contract benchmark: 84.6 percent accuracy, and invented denials in 1.4 percent of cases, against 2 to 27 percent for general chat models. 33 of 33 scripted claims pass; none of 27 attacks had an effect. |
| 9 | 3:40–4:00 | Closing card: repository, live demo URL, "The insurer here is a sandbox; the limitations are in the technical document." | What is real: the product and the public data. What is simulated: the insurer. Code, tests, evidence and limitations are in the repository. Thank you. |

## If something goes wrong

- Model quota exhausted: the badge in the top bar changes; decisions are unaffected, only the wording becomes templated. Record anyway or wait for the quota reset.
- Three refusals in one session trip the circuit breaker: start a **New chat**.
- Backend restarted mid-take: start a **New chat** (session facts live in memory).
