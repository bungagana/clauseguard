// Inline SVG so it follows the theme tokens in light and dark. A strict grid, orthogonal arrows:
// five AI agents around one rules engine, a code guardian at the gate, an audit trail on the side.
const P = "hsl(var(--primary))";
const D = "hsl(var(--destructive))";
const S = "hsl(var(--success))";
const M = "hsl(var(--muted-foreground))";
const C = "hsl(var(--card))";

function Agent({ x, y, w, title, role, badge = "AI agent" }: { x: number; y: number; w: number; title: string; role: string[]; badge?: string }) {
  const h = 50 + role.length * 13 + 8;
  return (
    <g>
      <rect x={x} y={y} width={w} height={h} rx={12} fill={C} stroke="currentColor" strokeWidth={1.6} />
      <rect x={x + 10} y={y + 9} width={badge.length * 6.1 + 12} height={16} rx={8} fill={P} fillOpacity={0.12} />
      <text x={x + 16} y={y + 20.5} fontSize={9} fontWeight={700} fill={P}>{badge}</text>
      <text x={x + 10} y={y + 42} fontSize={13} fontWeight={700} fill="currentColor">{title}</text>
      {role.map((l, i) => (
        <text key={i} x={x + 10} y={y + 57 + i * 13} fontSize={10} fill={M}>{l}</text>
      ))}
    </g>
  );
}

function Arrow({ d, color = "currentColor", dashed = false }: { d: string; color?: string; dashed?: boolean }) {
  return <path d={d} fill="none" stroke={color} strokeWidth={1.5} markerEnd="url(#arch-arrow)" strokeDasharray={dashed ? "4 3" : undefined} />;
}

export function ArchitectureDiagram() {
  return (
    <svg
      viewBox="0 0 1180 700"
      role="img"
      aria-label="ClauseGuard agent team: a Conversation Agent and a Fact Agent read the customer's message; a Document Reader Agent turns policy PDFs into structured rules after local redaction; a Rules Engine in pure code decides coverage, payer order, fixes and plan choice; a Guardian in code allows automatic reads, requires a tap for claim submission, and never lets money or identity change; an Explainer Agent phrases the answer and every number is checked; a Watchdog Agent flags deadlines; an audit trail records every step."
      className="h-auto w-full text-foreground"
      style={{ fontFamily: "inherit" }}
    >
      <defs>
        <marker id="arch-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
          <path d="M0,0 L10,5 L0,10 z" fill="currentColor" />
        </marker>
      </defs>

      {/* inputs */}
      <rect x={60} y={30} width={240} height={44} rx={10} fill="none" stroke={M} strokeWidth={1.3} strokeDasharray="5 4" />
      <text x={180} y={57} textAnchor="middle" fontSize={12} fontWeight={600} fill={M}>You, in chat (any language)</text>
      <rect x={430} y={30} width={240} height={44} rx={10} fill="none" stroke={M} strokeWidth={1.3} strokeDasharray="5 4" />
      <text x={550} y={57} textAnchor="middle" fontSize={12} fontWeight={600} fill={M}>Your policy PDFs and claim documents</text>

      {/* agents row 1 */}
      <Arrow d="M180 74 V98" />
      <Agent x={60} y={100} w={240} title="Conversation Agent" role={["Understands what you mean: a new situation,", "an answer to its question, or a what-if."]} />
      <Arrow d="M550 74 V98" />
      <Agent x={430} y={100} w={240} title="Document Reader Agent" role={["Removes personal data first, then turns the", "policy wording into structured rules."]} />

      {/* agents row 2 */}
      <Arrow d="M180 183 V207" />
      <Agent x={60} y={209} w={240} title="Fact Agent" role={["Fills in the facts of your case: dates, days", "in hospital, bill, accident or illness."]} />
      <Arrow d="M550 183 V207" />
      <rect x={430} y={209} width={240} height={60} rx={12} fill={C} stroke="currentColor" strokeWidth={1.6} />
      <text x={550} y={235} textAnchor="middle" fontSize={13} fontWeight={700} fill="currentColor">Policy rule book</text>
      <text x={550} y={252} textAnchor="middle" fontSize={10} fill={M}>every rule linked to its sentence in your policy</text>

      {/* merge into engine */}
      <path d="M180 292 V318 H363" fill="none" stroke="currentColor" strokeWidth={1.5} />
      <path d="M550 269 V318 H367" fill="none" stroke="currentColor" strokeWidth={1.5} />
      <Arrow d="M365 318 V342" color={P} />

      {/* rules engine */}
      <rect x={60} y={344} width={610} height={104} rx={12} fill={P} fillOpacity={0.07} stroke={P} strokeWidth={2} />
      <text x={76} y={366} fontSize={13} fontWeight={700} fill={P}>Rules Engine, pure code: the only part that decides</text>
      {[
        ["Coverage check", "covered or not, and why"],
        ["Who pays first", "order across your policies"],
        ["Fix a rejection", "smallest legitimate change"],
        ["Plan finder", "fills your gaps on budget"],
      ].map(([t, s], i) => (
        <g key={t}>
          <rect x={76 + i * 146} y={380} width={136} height={54} rx={8} fill={C} stroke={P} strokeWidth={1.2} />
          <text x={144 + i * 146} y={402} textAnchor="middle" fontSize={11} fontWeight={600} fill={P}>{t}</text>
          <text x={144 + i * 146} y={418} textAnchor="middle" fontSize={9.5} fill={M}>{s}</text>
        </g>
      ))}

      {/* guardian */}
      <Arrow d="M365 448 V472" />
      <rect x={225} y={474} width={280} height={56} rx={12} fill={C} stroke="currentColor" strokeWidth={1.6} />
      <text x={365} y={497} textAnchor="middle" fontSize={13} fontWeight={700} fill="currentColor">Guardian (code)</text>
      <text x={365} y={514} textAnchor="middle" fontSize={10} fill={M}>decides what runs by itself and what needs you</text>

      <Arrow d="M225 502 H178" color={S} />
      <rect x={40} y={480} width={136} height={44} rx={10} fill={C} stroke={S} strokeWidth={1.4} />
      <text x={108} y={498} textAnchor="middle" fontSize={11} fontWeight={700} fill={S}>Automatic</text>
      <text x={108} y={512} textAnchor="middle" fontSize={9.5} fill={M}>read, calculate, explain</text>

      <Arrow d="M365 530 V554" />
      <rect x={245} y={556} width={240} height={44} rx={10} fill={C} stroke="currentColor" strokeWidth={1.4} />
      <text x={365} y={574} textAnchor="middle" fontSize={11} fontWeight={700} fill="currentColor">Only after your tap</text>
      <text x={365} y={588} textAnchor="middle" fontSize={9.5} fill={M}>submit a claim, book a call-back</text>

      <Arrow d="M505 502 H552" color={D} />
      <rect x={554} y={480} width={150} height={44} rx={10} fill={C} stroke={D} strokeWidth={1.4} />
      <text x={629} y={498} textAnchor="middle" fontSize={11} fontWeight={700} fill={D}>A person handles it</text>
      <text x={629} y={512} textAnchor="middle" fontSize={9.5} fill={M}>money, bank account, beneficiary</text>

      {/* explainer + watchdog */}
      <Arrow d="M704 502 H748" />
      <Agent x={750} y={458} w={230} title="Explainer Agent" role={["Writes the answer in your language.", "Every amount, date and name is checked", "against the engine before you see it."]} />
      <Agent x={750} y={344} w={230} title="Watchdog Agent" role={["Watches your deadlines and lapses", "and warns you before money is lost."]} />
      <path d="M670 396 H748" fill="none" stroke="currentColor" strokeWidth={1.5} markerEnd="url(#arch-arrow)" />

      {/* audit */}
      <rect x={1010} y={100} width={140} height={500} rx={12} fill="none" stroke={M} strokeWidth={1.4} strokeDasharray="5 4" />
      <text x={1080} y={126} textAnchor="middle" fontSize={12} fontWeight={700} fill={M}>Audit trail</text>
      <text x={1080} y={142} textAnchor="middle" fontSize={9.5} fill={M}>every step recorded,</text>
      <text x={1080} y={155} textAnchor="middle" fontSize={9.5} fill={M}>tamper-evident</text>
      <text x={1080} y={580} textAnchor="middle" fontSize={9.5} fill={M}>written by code only</text>
      <Arrow d="M670 142 H1008" color={M} dashed />
      <Arrow d="M980 396 H1008" color={M} dashed />
      <Arrow d="M980 502 H1008" color={M} dashed />

      {/* output */}
      <Arrow d="M865 565 V620" />
      <rect x={720} y={622} width={290} height={44} rx={10} fill="none" stroke={M} strokeWidth={1.3} strokeDasharray="5 4" />
      <text x={865} y={649} textAnchor="middle" fontSize={12} fontWeight={600} fill={M}>Answer + the policy sentence behind it + PDF</text>
    </svg>
  );
}
