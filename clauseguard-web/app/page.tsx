import Image from "next/image";
import Link from "next/link";
import {
  ArrowRight,
  BadgeCheck,
  Bot,
  CalendarClock,
  Code2,
  FileSearch,
  FileText,
  Layers,
  ListChecks,
  MessageSquareText,
  ScanLine,
  ShieldCheck,
  Sparkles,
  Wallet,
  Wrench,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { ThemeToggle } from "@/components/chat/ThemeToggle";
import { AgentFlow } from "@/components/landing/AgentFlow";
import { ArchitectureDiagram } from "@/components/landing/ArchitectureDiagram";
import { BarChart, StatTile } from "@/components/landing/Charts";
import { Reveal } from "@/components/landing/Reveal";

const REPO_URL = "https://github.com/Bungalm/LOMBA-CHHINA";

const NAV = [
  ["#features", "What it does"],
  ["#screens", "See it"],
  ["#how", "How it works"],
  ["#results", "Results"],
  ["#safety", "Safety"],
] as const;

const HERO_STATS = [
  ["33 / 33", "test scenarios passed"],
  ["27 / 27", "attacks blocked"],
  ["84.6 %", "on a public benchmark"],
] as const;

const TINTS = [
  "bg-sky-100 text-sky-700 dark:bg-sky-900/40 dark:text-sky-300",
  "bg-teal-100 text-teal-700 dark:bg-teal-900/40 dark:text-teal-300",
  "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300",
  "bg-rose-100 text-rose-700 dark:bg-rose-900/40 dark:text-rose-300",
  "bg-violet-100 text-violet-700 dark:bg-violet-900/40 dark:text-violet-300",
  "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300",
];

// Each idea lives in exactly one section: outcomes here, proof in "See it", mechanism in
// "How it works", numbers in "Results", limits of the agent in "Safety".
const FEATURES = [
  { icon: FileSearch, title: "Ask in plain language", body: "A clear yes or no, the amount, and the sentence in your policy that says so." },
  { icon: Layers, title: "See every policy together", body: "National health, your employer's plan and your own cover, read as one portfolio: where you pay twice and where nothing would pay." },
  { icon: Wallet, title: "Know who pays first", body: "When several policies could respond, they are put in the right order, with what each one needs from you." },
  { icon: CalendarClock, title: "Keep every deadline", body: "Filing windows, grace periods and expiry dates on one timeline, each with the money at stake." },
  { icon: Wrench, title: "Fix a refusal", body: "The smallest legitimate change that turns a refused claim into a paid one: a document, a date, a report." },
  { icon: ListChecks, title: "Close the gaps", body: "Real plans with real premiums, matched to what you lack and what you can afford. A suggestion, not a sale." },
] as const;

const SCREENS = [
  {
    src: "/screens/focus-verdict.png",
    eyebrow: "A claim question",
    title: "Covered for Rp 1.5 million, filed by 26 November, one fact still open",
    body: "Three days in hospital with dengue. The hospital-cash plan pays; the national plan depends on whether the hospital is a partner facility, so that is the only question asked.",
  },
  {
    src: "/screens/focus-allocation.png",
    eyebrow: "An accident with four policies",
    title: "Rp 22 million recovered instead of Rp 20 million",
    body: "The road-accident fund pays first and the platform cover tops it up. The personal-accident policy is out because the licence had expired, and the card says why.",
  },
  {
    src: "/screens/focus-refusal.png",
    eyebrow: "A request it will not carry out",
    title: "Changing a payout account goes to a person",
    body: "The assistant opens a ticket for the insurer, states that nothing on the account has changed, and does not make an exception for urgency.",
  },
  {
    src: "/screens/focus-whatif.png",
    eyebrow: "What if",
    title: "Flip a fact and every answer is recomputed",
    body: "Only facts that would change an outcome for your policies are offered. With a valid licence, the personal-accident policy moves from refused to one open question.",
  },
  {
    src: "/screens/focus-confirm.png",
    eyebrow: "Before anything is sent",
    title: "Submission waits for your tap",
    body: "A claim with missing documents is held back and the list is shown. Choosing to submit anyway still ends at a confirmation card; nothing leaves before you press Confirm.",
  },
] as const;

const STEPS = [
  { icon: FileText, title: "You upload a policy", body: "Any PDF. Names, ID numbers and account numbers are removed on your side before the AI reads a word." },
  { icon: ScanLine, title: "The Document Reader builds a rule book", body: "Every rule keeps a link to the sentence it came from, so every later answer can point back to the page." },
  { icon: Bot, title: "The engine decides, the agents ask", body: "A rules engine checks your facts against the rule book. The Conversation and Fact agents understand what you said; if one missing fact would change the answer, they ask for that one fact." },
  { icon: BadgeCheck, title: "The Explainer writes it up", body: "In English or Indonesian, in your words. Every amount, date and name is checked against the engine before you see it, and the Watchdog keeps watching your deadlines afterwards." },
] as const;

const STACK = [
  "Gemini Flash behind the five agents",
  "Rules engine in Python, no model inside",
  "Checked generation: every figure verified before display",
  "Tamper-evident audit trail",
  "Local redaction and hidden-text detection",
  "FastAPI · Next.js 14 · TypeScript",
  "532 automated tests · Playwright end-to-end",
] as const;

const BENCH_ACC = [
  { label: "Gemini 3", value: 65.2, note: "benchmark authors' run, web chat, n = 580" },
  { label: "ChatGPT 5.3", value: 72.9, note: "benchmark authors' run, web chat, n = 580" },
  { label: "Claude Sonnet 4.6", value: 87.8, note: "benchmark authors' run, web chat, n = 580" },
  {
    label: "ClauseGuard", value: 84.6, highlight: true, ceiling: 91.8, ceilingLabel: "ceiling with perfect reading",
    note: "our run, Gemini Flash + rules engine, n = 390. The lighter extension is the engine on the benchmark's own rules (91.8 %): what remains is reading, not reasoning",
  },
];

const BENCH_FAB = [
  { label: "Gemini 3", value: 26.6 },
  { label: "ChatGPT 5.3", value: 6.7 },
  { label: "Claude Sonnet 4.6", value: 2.4 },
  { label: "ClauseGuard", value: 1.4, highlight: true },
];

const SAFETY_ROWS = [
  ["Read your own policies and claims", "Runs by itself", "text-success"],
  ["Calculate, explain, draft a letter", "Runs by itself", "text-success"],
  ["Submit a claim, book a call-back", "Only after you tap Confirm", "text-warning-foreground"],
  ["Move money, change a bank account or beneficiary", "Never. A person at the insurer does it.", "text-destructive"],
] as const;

const SAFETY_POINTS = [
  { title: "Documents cannot give orders", body: "Text hidden in an uploaded invoice (white on white, off the page) is detected, labelled untrusted and ignored." },
  { title: "Nothing is interpreted as an instruction", body: "What a document or a tool returns is shown to you; it is never pasted into the agents' instructions." },
  { title: "Every step is on record", body: "Each action is written by code to a hash-chained log. Alter one line and the verifier points at it." },
  { title: "New policies start unverified", body: "A policy you upload is usable at once but marked unverified until a person has reviewed the extracted rules." },
] as const;

export default function LandingPage() {
  return (
    <div className="flex min-h-dvh flex-col bg-background text-foreground">
      <header className="sticky top-0 z-30 border-b border-border/60 bg-background/80 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-4 py-3 sm:px-6">
          <Link href="/" className="flex items-center gap-2">
            <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-navy text-navy-foreground">
              <ShieldCheck className="h-4 w-4" />
            </div>
            <span className="font-display text-sm font-semibold">ClauseGuard</span>
          </Link>
          <nav className="hidden items-center gap-6 text-sm text-muted-foreground md:flex">
            {NAV.map(([href, label]) => (
              <a key={href} href={href} className="transition-colors hover:text-foreground">
                {label}
              </a>
            ))}
          </nav>
          <div className="flex items-center gap-2">
            <ThemeToggle />
            <Button asChild variant="outline" size="sm" className="hidden sm:inline-flex">
              <Link href="/chat?mode=demo">Open the demo</Link>
            </Button>
            <Button asChild size="sm">
              <Link href="/chat?mode=production">Try with your policy</Link>
            </Button>
          </div>
        </div>
      </header>

      <main className="flex-1">
        {/* Hero */}
        <section className="hero-glow relative overflow-hidden">
          <div className="grid-fade pointer-events-none absolute inset-0" aria-hidden />
          <div className="relative mx-auto grid max-w-6xl items-center gap-10 px-4 pb-16 pt-14 sm:px-6 lg:grid-cols-[1.05fr_1fr] lg:pb-24 lg:pt-20">
            <div className="flex flex-col items-start gap-5">
              <span className="inline-flex items-center gap-1.5 rounded-full border border-primary/25 bg-primary/10 px-3 py-1 text-xs font-medium text-primary">
                <Sparkles className="h-3 w-3" />
                FinTechathon 2026 · AI Insurance Assistant
              </span>
              <h1 className="font-display text-balance text-4xl font-extrabold leading-[1.05] tracking-tight sm:text-5xl lg:text-[3.5rem]">
                Know exactly what your insurance covers. <span className="text-gradient">With the sentence to prove it.</span>
              </h1>
              <p className="max-w-xl text-balance text-base text-muted-foreground sm:text-lg">
                ClauseGuard reads your real policies and tells you what you are owed, how to claim it, and which line in the
                policy says so. It asks only when a missing fact would change the answer, and it never moves money.
              </p>
              <div className="flex w-full flex-col gap-3 sm:w-auto sm:flex-row">
                <Button asChild size="lg" className="glow-primary w-full sm:w-auto">
                  <Link href="/chat?mode=demo">
                    Open the demo <ArrowRight className="h-4 w-4" />
                  </Link>
                </Button>
                <Button asChild size="lg" variant="outline" className="w-full sm:w-auto">
                  <Link href="/chat?mode=production">Upload your own policy</Link>
                </Button>
              </div>
              <dl className="mt-2 grid w-full grid-cols-3 gap-4 border-t border-border/70 pt-5">
                {HERO_STATS.map(([v, l]) => (
                  <div key={l}>
                    <dt className="font-display text-xl font-semibold tabular-nums sm:text-2xl">{v}</dt>
                    <dd className="text-xs text-muted-foreground sm:text-sm">{l}</dd>
                  </div>
                ))}
              </dl>
            </div>

            <AgentFlow />
          </div>
        </section>

        {/* What it does */}
        <Section id="features" eyebrow="What it does" title="Six things a policyholder needs, none of them a guess">
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {FEATURES.map((f, i) => (
              <Reveal key={f.title} delay={i * 0.06}>
                <div className="card-lift h-full rounded-2xl border border-border bg-card p-5 shadow-soft">
                  <div className={`flex h-11 w-11 items-center justify-center rounded-xl ${TINTS[i % TINTS.length]}`}>
                    <f.icon className="h-5 w-5" />
                  </div>
                  <p className="mt-4 font-display text-[15px] font-semibold">{f.title}</p>
                  <p className="mt-1.5 text-sm leading-relaxed text-muted-foreground">{f.body}</p>
                </div>
              </Reveal>
            ))}
          </div>
        </Section>

        {/* See it */}
        <Section id="screens" eyebrow="See it" title="Five moments from the running app" lead="Cropped from real conversations, not mock-ups." tone="muted">
          <div className="flex flex-col gap-14">
            {SCREENS.map((s, i) => (
              <Reveal key={s.src}>
                <figure className={`grid items-center gap-6 md:grid-cols-[1.15fr_1fr] md:gap-12 ${i % 2 ? "md:[&>*:first-child]:order-2" : ""}`}>
                  <Frame src={s.src} alt={s.title} tilt={i % 2 ? "right" : "left"} />
                  <figcaption>
                    <p className="text-xs font-semibold uppercase tracking-[0.14em] text-primary">{s.eyebrow}</p>
                    <p className="mt-2 font-display text-xl font-semibold leading-snug sm:text-2xl">{s.title}</p>
                    <p className="mt-2 text-sm leading-relaxed text-muted-foreground sm:text-base">{s.body}</p>
                  </figcaption>
                </figure>
              </Reveal>
            ))}
          </div>
        </Section>

        {/* How it works */}
        <Section
          id="how"
          eyebrow="How it works"
          title="Five AI agents around one rules engine"
          lead="The agents read, ask and explain. The rules engine decides, in code, so the same facts always give the same answer and every answer can be checked."
        >
          <Reveal>
            <div className="overflow-hidden rounded-2xl border border-border bg-card p-3 shadow-soft sm:p-6">
              <ArchitectureDiagram />
            </div>
          </Reveal>
          <ol className="mt-6 grid gap-4 md:grid-cols-2 lg:grid-cols-4">
            {STEPS.map((s, i) => (
              <Reveal key={s.title} delay={i * 0.06}>
                <li className="card-lift h-full rounded-2xl border border-border bg-card p-5 shadow-soft">
                  <div className="flex items-center justify-between">
                    <div className={`flex h-11 w-11 items-center justify-center rounded-xl ${TINTS[i % TINTS.length]}`}>
                      <s.icon className="h-5 w-5" />
                    </div>
                    <span className="font-display text-2xl font-extrabold text-primary/20">0{i + 1}</span>
                  </div>
                  <p className="mt-4 font-display text-[15px] font-semibold">{s.title}</p>
                  <p className="mt-1.5 text-sm leading-relaxed text-muted-foreground">{s.body}</p>
                </li>
              </Reveal>
            ))}
          </ol>
          <ul className="mt-6 flex flex-wrap gap-2">
            {STACK.map((s) => (
              <li key={s} className="rounded-full border border-border bg-card px-3 py-1 text-xs text-muted-foreground">
                {s}
              </li>
            ))}
          </ul>
        </Section>

        {/* Results */}
        <Section
          id="results"
          eyebrow="Results"
          title="How well does it work?"
          lead="Measured on a public benchmark, our own test scenarios, an attack suite and 500 real households. Every figure can be regenerated from the repository."
          tone="dark"
        >
          <div className="grid gap-4 lg:grid-cols-2">
            <BarChart
              title="Accuracy on the public benchmark"
              caption="Mridul et al. 2026: 58 scenarios × 10 life-insurance contracts, every answer traced to a clause."
              rows={BENCH_ACC}
            />
            <BarChart
              title="How often the system invents a refusal"
              caption="Share of answers that said 'denied' when the policy simply did not apply, the costliest mistake for a customer."
              rows={BENCH_FAB}
              max={30}
              lowerIsBetter
            />
          </div>
          <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <StatTile value="0 / 15" label="Honest requests wrongly refused" note="The attack suite's benign twins: none was blocked" />
            <StatTile value="20 / 20" label="Same answer, different wording" note="The same case asked twenty ways gave the same decision every time" />
            <StatTile value="47 %" label="Households where the usual claim order loses money" note="500 real plan sets; USD 988 more recovered on average with the right order" />
            <StatTile value="532" label="Automated tests" note="Backend and end-to-end, run without an API key" />
          </div>
          <div className="mt-6 grid gap-4 md:grid-cols-2">
            <div className="rounded-2xl border border-border bg-secondary/50 p-5">
              <p className="text-sm font-semibold">Real data behind the numbers</p>
              <ul className="mt-2 space-y-1 text-sm text-muted-foreground">
                <li>834 US Marketplace plans with real premiums (CMS)</li>
                <li>30 Indonesian product summaries (RIPLAY); two demo policies quote them word for word</li>
                <li>150 UK Financial Ombudsman decisions</li>
                <li>A public, clause-traced benchmark of 580 labelled questions</li>
              </ul>
            </div>
            <div className="rounded-2xl border border-border bg-secondary/50 p-5">
              <p className="text-sm font-semibold">Limits we state up front</p>
              <ul className="mt-2 space-y-1 text-sm text-muted-foreground">
                <li>The published model scores were produced by the benchmark authors in web chat on all 580 items; ours is an API run on 390. Our own same-model comparison is a statistical tie.</li>
                <li>USD 988 is a simulation over real plan terms, not money paid out.</li>
                <li>The insurer behind the demo is our own sandbox, not a live insurer.</li>
              </ul>
            </div>
          </div>
        </Section>

        {/* Safety */}
        <Section id="safety" eyebrow="Safety" title="What runs by itself, what waits for you, what never happens" tone="muted">
          <div className="grid gap-8 lg:grid-cols-[1fr_1.1fr]">
            <Reveal>
              <div className="overflow-hidden rounded-2xl border border-border bg-card shadow-soft">
                <table className="w-full text-sm">
                  <thead className="bg-muted/60 text-left text-xs uppercase tracking-wide text-muted-foreground">
                    <tr>
                      <th className="px-4 py-2.5 font-medium">Action</th>
                      <th className="px-4 py-2.5 font-medium">Who allows it</th>
                    </tr>
                  </thead>
                  <tbody>
                    {SAFETY_ROWS.map(([a, g, cls]) => (
                      <tr key={a} className="border-t border-border">
                        <td className="px-4 py-3">{a}</td>
                        <td className={`px-4 py-3 font-medium ${cls}`}>{g}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Reveal>
            <div className="grid gap-4 sm:grid-cols-2">
              {SAFETY_POINTS.map((s, i) => (
                <Reveal key={s.title} delay={i * 0.06}>
                  <div className="card-lift h-full rounded-2xl border border-border bg-card p-5 shadow-soft">
                    <ShieldCheck className="h-5 w-5 text-primary" />
                    <p className="mt-3 font-display text-[15px] font-semibold">{s.title}</p>
                    <p className="mt-1 text-sm leading-relaxed text-muted-foreground">{s.body}</p>
                  </div>
                </Reveal>
              ))}
            </div>
          </div>
        </Section>

        {/* CTA */}
        <section className="px-4 py-16 sm:px-6">
          <div className="band-dark dark relative mx-auto max-w-6xl overflow-hidden rounded-3xl px-6 py-14 text-center text-foreground sm:px-12">
            <h2 className="relative font-display text-balance text-3xl font-bold tracking-tight sm:text-4xl">Try it on your own policy</h2>
            <p className="relative mx-auto mt-3 max-w-xl text-balance text-muted-foreground">
              Upload a PDF and ask what it covers. The demo runs on a sandbox insurer, so nothing you do here reaches a real account.
            </p>
            <div className="relative mt-7 flex flex-col justify-center gap-3 sm:flex-row">
              <Button asChild size="lg" className="glow-primary">
                <Link href="/chat?mode=production">
                  Upload a policy <ArrowRight className="h-4 w-4" />
                </Link>
              </Button>
              <Button asChild size="lg" variant="outline">
                <a href={REPO_URL} target="_blank" rel="noreferrer">
                  <Code2 className="h-4 w-4" /> Source code
                </a>
              </Button>
            </div>
          </div>
        </section>
      </main>

      <footer className="border-t border-border px-4 py-6 sm:px-6">
        <div className="mx-auto flex max-w-6xl flex-col items-center justify-between gap-3 text-xs text-muted-foreground sm:flex-row">
          <p className="inline-flex items-center gap-1.5">
            <MessageSquareText className="h-3.5 w-3.5" /> ClauseGuard · Institut Teknologi Sepuluh Nopember, Surabaya · FinTechathon 2026 International Track
          </p>
          <p>Research prototype, not legal or financial advice. Talk to a licensed agent before buying or cancelling cover.</p>
        </div>
      </footer>
    </div>
  );
}

function Section({
  id, eyebrow, title, lead, tone = "plain", children,
}: {
  id: string; eyebrow: string; title: string; lead?: string; tone?: "plain" | "muted" | "dark"; children: React.ReactNode;
}) {
  const cls = tone === "muted" ? "border-y border-border/60 bg-muted/40" : tone === "dark" ? "dark band-dark text-foreground" : "";
  return (
    <section id={id} className={`scroll-mt-20 px-4 py-16 sm:px-6 lg:py-20 ${cls}`}>
      <div className="mx-auto max-w-6xl">
        <p className="text-xs font-semibold uppercase tracking-[0.14em] text-primary">{eyebrow}</p>
        <h2 className="mt-2 max-w-2xl font-display text-balance text-2xl font-bold tracking-tight sm:text-3xl lg:text-4xl">{title}</h2>
        {lead && <p className="mt-3 max-w-2xl text-balance text-sm text-muted-foreground sm:text-base">{lead}</p>}
        <div className="mt-8">{children}</div>
      </div>
    </section>
  );
}

function Frame({ src, alt, tilt }: { src: string; alt: string; tilt?: "left" | "right" }) {
  const tiltCls = tilt === "left" ? "md:[transform:perspective(1400px)_rotateY(6deg)]" : tilt === "right" ? "md:[transform:perspective(1400px)_rotateY(-6deg)]" : "";
  return (
    <div className={`frame-glow overflow-hidden rounded-2xl border border-border bg-card transition-transform duration-500 hover:[transform:none] ${tiltCls}`}>
      <Image src={src} alt={alt} width={1420} height={900} className="h-auto w-full" sizes="(min-width: 1024px) 640px, 100vw" />
    </div>
  );
}
