# ClauseGuard — presentation deck

Eight slides, under ten minutes. One idea per slide, one sentence of text, one picture. The numbers
come from `evidence/`; the pictures come from the running product. `docs/deck/build_deck.py` reads
this file and writes `docs/deck/ClauseGuard_deck.pptx`.

Format: `## Slide N: title`, then `Line:` (one sentence shown large), optional `Image:` / `Image2:`
(paths relative to the repository root), optional `Chart: benchmark`, up to three `- ` bullets, and
`Notes:` (spoken, at most 60 words).

## Slide 1: ClauseGuard
Line: Clarity in every clause, confidence in every claim.
Image: clauseguard-web/public/brand/logo-wordmark.png
- Bunga Laelatul Muna · Izra · Wan Sabrina — Institut Teknologi Sepuluh Nopember, Indonesia
- FinTechathon 2026 · International Track · Topic D
Notes: ClauseGuard is an insurance assistant that reads your own policies, prepares your claim from your documents, sends it only after you confirm, and brings the insurer's decision back to you. Every answer points to the sentence of the policy that decides it.

## Slide 2: The problem
Line: Claims fail on paperwork and deadlines, not on coverage.
- A household holds three to five policies, each a 40-page wording with its own document list and filing clock
- People do not know which policy pays first, how much, or what to send by when
- Chatbots answer fluently — and invent denials that are not in the policy
Notes: Most people never read their policies. When something happens they face several wordings, several document checklists and a filing deadline. Generic chat assistants answer confidently but make up exclusions. The problem is not understanding insurance in general; it is acting correctly on your own policies.

## Slide 3: Four documents, one sentence, claim ready
Line: Drop your hospital documents in the chat; the insurer's own claim form comes back, filled.
Image: clauseguard/docs/deck/img/form_crop.png
Notes: Rizky attaches four hospital documents and one sentence. The agent reads them, matches them to Sompo's document list, takes the bill from the invoice, and lays out Sompo's own claim form from Sompo's wording. Every field is filled from typed facts; the customer sees the form before anything leaves.

## Slide 4: Every answer cites the clause
Line: Covered, for how much, by when — and the exact sentence that decides it.
Image: clauseguard-web/public/screens/focus-verdict.png
- A rules engine decides; the model only reads, binds facts and words the reply
- One question is asked only when one missing fact would change the outcome
Notes: The decision is not generated text. Policies are compiled into typed rules, and a deterministic engine applies them. The reply shows the amount, the filing deadline and the quoted clause. If a single missing fact would flip the result, the agent asks for that fact and nothing else.

## Slide 5: It acts, and the decision comes back
Line: After one tap, the claim reaches the insurer's desk; the adjuster's decision returns to the chat.
Image: clauseguard-web/public/screens/focus-insurer.png
Image2: clauseguard/docs/deck/img/decision_crop.png
Notes: Submission needs a Confirm tap bound to a one-time server token. The claim, the form and the attachments land on the insurer's desk, a sandbox in this entry. A person reviews, decides with a note, and the decision appears in the customer's chat. The agent prepares and reports; it never decides a claim.

## Slide 6: It cannot touch your money
Line: Permission is enforced in code: read, compute, send after Confirm — money and identity, never.
Image: clauseguard-web/public/screens/focus-refusal.png
- Observe / Draft / Act switch, insurer-side halt switch, hash-chained audit log
- Uploaded documents are data: hidden instructions are detected and ignored
Notes: Four permission tiers live in code, not in a prompt. Changing a payout account has no tool at all; the agent opens a ticket for a person. The insurer can halt the agent for every customer. Every step is written to a tamper-evident log. In our attack suite, none of 27 attacks had an effect.

## Slide 7: Measured, with limits
Line: Fewer invented denials than general chat models, measured on a public benchmark.
Chart: benchmark
- 84.6 % accuracy on 390 benchmark labels; 1.4 % fabricated denials (general models: 2.4 % to 26.6 %)
- 33 of 33 scripted claims, 0 of 27 attacks succeeded, 0 of 15 benign requests blocked
Notes: On a public insurance-contract benchmark, ClauseGuard reaches 84.6 percent accuracy and invents a denial in 1.4 percent of cases. We do not claim to beat frontier models on accuracy; the difference is that answers are traced to clauses and denials are not fabricated. Scripted claims and the attack suite pass fully.

## Slide 8: What is real, what is next
Line: Live web app, sandbox insurer, public data — and an honest list of what is not built yet.
- Real: six insurer wordings, 30 Indonesian product summaries, 834 CMS plans, consumer questions, ombudsman decisions
- Sandbox: the insurer's desk and the three personas; no real insurer receives a claim
- Next: a real insurer API, session state that survives restarts, an external red team
- github.com/bungagana/clauseguard · clauseguard-red.vercel.app
Notes: What is real is public data and a working product. What is simulated is the insurer: our desk is a sandbox, so no real claim is filed. The next steps are an insurer API, persistent sessions and an external red team. The code, tests, evidence and limitations are all in the repository. Thank you.
