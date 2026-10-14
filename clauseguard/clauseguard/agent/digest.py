"""Deadline digest: what is coming due across a household's policies and open claims, with the
money that turns on each date and one suggested next action.

Dates come from timeline.build_timeline (filing deadlines through derive.filing_deadline, grace
period ends, policy expiry, waiting-period and survival-period ends) plus the premium schedule
(next instalment, unpaid instalments). Actions are suggestions the user can click: start a claim
plan (which still needs its own confirmations), or information about paying a premium or renewing.
Nothing here moves money or changes a policy. Deterministic; no language model runs here.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any, Optional

from pydantic import Field

from ..portfolio import add_months
from ..schema import PolicyRecord, Strict
from ..timeline import OpenClaim, build_timeline

HORIZON_DAYS = 90
PAST_WINDOW_DAYS = 45
KIND_RANK = {"CLAIM_STATUS": -1, "FILING_DEADLINE": 0, "GRACE_ENDS": 1, "PREMIUM_OVERDUE": 2, "PREMIUM_DUE": 3, "POLICY_EXPIRES": 4, "SURVIVAL_PERIOD_ENDS": 5,
             "WAITING_ENDS": 6, "SPECIFIED_WAITING_ENDS": 7, "CONTESTABILITY_ENDS": 8}


class DigestAction(Strict):
    type: str = Field(pattern=r"^(start_claim_plan|pay_premium_info|renew_info|appeal_info|none)$")
    label_en: str
    label_id: str
    prompt: Optional[str] = None


class DigestItem(Strict):
    date: date
    days_left: int
    policy_id: str
    product_name: str
    kind: str
    money_at_risk: Optional[Decimal] = None
    currency: str = "IDR"
    clause_id: Optional[str] = None
    claim_id: Optional[str] = None
    urgency: str = Field(pattern=r"^(overdue|this_week|soon|later)$")
    message_en: str = Field(max_length=400)
    message_id: str = Field(max_length=400)
    action: DigestAction


def _urgency(days_left: int) -> str:
    if days_left < 0:
        return "overdue"
    if days_left <= 7:
        return "this_week"
    if days_left <= 30:
        return "soon"
    return "later"


def premium_schedule(rows: list[dict[str, Any]], frequency: Optional[str], amount: Optional[int], as_of: date) -> dict[str, Any]:
    """{first unpaid due date, next due date, amount} from a policy's premium rows."""
    dues = sorted((date.fromisoformat(str(r["due_date"])), r.get("paid_date")) for r in rows if r.get("due_date"))
    unpaid = [d for d, paid in dues if paid is None and d <= as_of]
    step = {"monthly": 1, "quarterly": 3, "semiannual": 6, "annual": 12}.get(str(frequency or "").lower())
    nxt = None
    if dues and step:
        nxt = add_months(dues[-1][0], step)
        while nxt <= as_of:
            nxt = add_months(nxt, step)
    return {"unpaid_since": unpaid[0] if unpaid else None, "unpaid_count": len(unpaid), "next_due": nxt, "amount": amount}


def _money(v: Optional[Decimal], cur: str) -> str:
    return f"{cur} {int(Decimal(v)):,}" if v is not None else ""


def build_digest(policies: list[PolicyRecord], *, as_of: date, open_claims: Optional[list[OpenClaim]] = None,
                 premiums: Optional[dict[str, dict[str, Any]]] = None, horizon_days: int = HORIZON_DAYS) -> list[DigestItem]:
    premiums = premiums or {}
    by_id = {p.id: p for p in policies}
    premium_due = {pid: v["unpaid_since"] for pid, v in premiums.items() if v.get("unpaid_since")}
    events = build_timeline(policies, open_claims or [], as_of, premium_due=premium_due)
    items: list[DigestItem] = []
    for e in events:
        if e.days_left > horizon_days or e.days_left < -PAST_WINDOW_DAYS:
            continue
        p = by_id[e.policy_id]
        cur = p.currency
        risk = _money(e.money_at_risk, cur)
        when = e.date.isoformat()
        if e.kind == "FILING_DEADLINE":
            passed = e.days_left < 0
            msg_en = (f"{p.product_name} ({p.id}): filing deadline for claim {e.claim_id} " + (f"passed on {when}" if passed else f"is {when}, {e.days_left} days left")
                      + (f"; {risk} at stake" if risk else "") + ".")
            msg_id = (f"{p.product_name} ({p.id}): batas pengajuan klaim {e.claim_id} " + (f"sudah lewat pada {when}" if passed else f"tanggal {when}, tersisa {e.days_left} hari")
                      + (f"; {risk} dipertaruhkan" if risk else "") + ".")
            action = DigestAction(type="start_claim_plan", label_en="Start the claim plan", label_id="Mulai rencana klaim",
                                  prompt=f"Please handle my claim {e.claim_id}" if e.claim_id and not e.claim_id.startswith("CHAT") else "Please handle my claim")
        elif e.kind == "GRACE_ENDS":
            due = premiums.get(p.id, {}).get("unpaid_since")
            due_txt = due.isoformat() if due else "-"
            if e.days_left < 0:
                msg_en = f"{p.product_name} ({p.id}): premium due {due_txt} is unpaid and the grace period ended on {when}; the policy has lapsed" + (f" ({risk} of cover)" if risk else "") + ". Ask the insurer about reinstatement."
                msg_id = f"{p.product_name} ({p.id}): premi jatuh tempo {due_txt} belum dibayar dan masa tenggang berakhir {when}; polis sudah lapse" + (f" (pertanggungan {risk})" if risk else "") + ". Tanyakan pemulihan polis ke penanggung."
            else:
                msg_en = f"{p.product_name} ({p.id}): pay the premium due {due_txt} before the grace period ends on {when}, {e.days_left} days left" + (f"; {risk} of cover lapses otherwise" if risk else "") + "."
                msg_id = f"{p.product_name} ({p.id}): bayar premi jatuh tempo {due_txt} sebelum masa tenggang berakhir {when}, tersisa {e.days_left} hari" + (f"; jika tidak, pertanggungan {risk} berhenti" if risk else "") + "."
            action = DigestAction(type="pay_premium_info", label_en="How to pay (information only)", label_id="Cara membayar (informasi saja)")
        elif e.kind == "POLICY_EXPIRES":
            msg_en = f"{p.product_name} ({p.id}): policy period ends {when}, {e.days_left} days left; renew to keep cover" + (f" of {risk}" if risk else "") + "."
            msg_id = f"{p.product_name} ({p.id}): masa polis berakhir {when}, tersisa {e.days_left} hari; perpanjang agar pertanggungan" + (f" {risk}" if risk else "") + " tetap berlaku."
            action = DigestAction(type="renew_info", label_en="Renewal steps (information only)", label_id="Langkah perpanjangan (informasi saja)")
        elif e.kind == "SURVIVAL_PERIOD_ENDS":
            msg_en = f"{p.product_name} ({p.id}): survival period for claim {e.claim_id} ends {when}; the benefit becomes payable from that date" + (f" ({risk})" if risk else "") + "."
            msg_id = f"{p.product_name} ({p.id}): masa bertahan hidup untuk klaim {e.claim_id} berakhir {when}; manfaat dapat dibayar sejak tanggal itu" + (f" ({risk})" if risk else "") + "."
            action = DigestAction(type="none", label_en="", label_id="")
        else:
            label = {"WAITING_ENDS": ("general waiting period ends", "masa tunggu umum berakhir"),
                     "SPECIFIED_WAITING_ENDS": ("waiting period for the specified diseases ends", "masa tunggu penyakit tertentu berakhir"),
                     "CONTESTABILITY_ENDS": ("contestability period ends", "masa sanggah berakhir")}.get(e.kind, (e.kind.lower(), e.kind.lower()))
            msg_en = f"{p.product_name} ({p.id}): {label[0]} on {when}, {e.days_left} days from today."
            msg_id = f"{p.product_name} ({p.id}): {label[1]} pada {when}, {e.days_left} hari lagi."
            action = DigestAction(type="none", label_en="", label_id="")
        items.append(DigestItem(date=e.date, days_left=e.days_left, policy_id=p.id, product_name=p.product_name, kind=e.kind, money_at_risk=e.money_at_risk,
                                currency=cur, clause_id=e.clause_id, claim_id=e.claim_id, urgency=_urgency(e.days_left), message_en=msg_en[:400],
                                message_id=msg_id[:400], action=action))
    grace_policies = {i.policy_id for i in items if i.kind == "GRACE_ENDS"}
    for pid, info in premiums.items():
        p = by_id.get(pid)
        if p is None:
            continue
        amt = _money(Decimal(info["amount"]), p.currency) if info.get("amount") else ""
        since = info.get("unpaid_since")
        if since is not None and pid not in grace_policies:
            n = info.get("unpaid_count") or 1
            left = (since - as_of).days
            items.append(DigestItem(date=since, days_left=left, policy_id=pid, product_name=p.product_name, kind="PREMIUM_OVERDUE", currency=p.currency,
                                    money_at_risk=None, urgency="overdue",
                                    message_en=f"{p.product_name} ({pid}): {n} instalment(s) unpaid since {since.isoformat()}" + (f" ({amt} each)" if amt else "") + "; the cover is not active until they are settled.",
                                    message_id=f"{p.product_name} ({pid}): {n} tagihan belum dibayar sejak {since.isoformat()}" + (f" ({amt} per tagihan)" if amt else "") + "; perlindungan tidak aktif sampai dilunasi.",
                                    action=DigestAction(type="pay_premium_info", label_en="How to pay (information only)", label_id="Cara membayar (informasi saja)")))
        nxt = info.get("next_due")
        renewal = p.expiry_date is not None and nxt is not None and nxt > p.expiry_date
        if since is None and nxt is not None and not renewal and (nxt - as_of).days <= min(horizon_days, 45):
            left = (nxt - as_of).days
            items.append(DigestItem(date=nxt, days_left=left, policy_id=pid, product_name=p.product_name, kind="PREMIUM_DUE", currency=p.currency,
                                    money_at_risk=None, urgency=_urgency(left),
                                    message_en=f"{p.product_name} ({pid}): next premium" + (f" of {amt}" if amt else "") + f" is due {nxt.isoformat()}, {left} days from today.",
                                    message_id=f"{p.product_name} ({pid}): premi berikutnya" + (f" sebesar {amt}" if amt else "") + f" jatuh tempo {nxt.isoformat()}, {left} hari lagi.",
                                    action=DigestAction(type="pay_premium_info", label_en="How to pay (information only)", label_id="Cara membayar (informasi saja)")))
    items.sort(key=lambda i: (i.days_left >= 0, i.date, KIND_RANK.get(i.kind, 9), i.policy_id))
    return items


PAY_INFO_EN = ("Paying a premium is done through the insurer's own channels (its app, virtual account or bank transfer to the account printed on "
               "your policy schedule); I do not move money and I never ask for card or account details.")
PAY_INFO_ID = ("Pembayaran premi dilakukan melalui kanal resmi penanggung (aplikasi, virtual account, atau transfer ke rekening yang tertera di "
               "ikhtisar polis); saya tidak memindahkan uang dan tidak pernah meminta data kartu atau rekening.")


def render(items: list[DigestItem], lang: str, limit: int = 10) -> list[str]:
    if not items:
        return ["Nothing is due in the next 90 days on your policies and open claims." if lang != "id"
                else "Tidak ada yang jatuh tempo dalam 90 hari ke depan untuk polis dan klaim Anda."]
    head = "Coming up on your policies and open claims (most urgent first):" if lang != "id" else "Yang perlu diperhatikan pada polis dan klaim Anda (paling mendesak dulu):"
    out = [head]
    for i, it in enumerate(items[:limit], 1):
        msg = it.message_id if lang == "id" else it.message_en
        act = (it.action.label_id if lang == "id" else it.action.label_en) if it.action.type != "none" else ""
        out.append(f"{i}. {msg}" + (f" -> {act}" if act else ""))
    if any(it.action.type == "pay_premium_info" for it in items[:limit]):
        out.append(PAY_INFO_ID if lang == "id" else PAY_INFO_EN)
    if any(it.action.type == "start_claim_plan" for it in items[:limit]):
        out.append("Say 'handle my claim' and I will build the claim plan; each submission still needs your confirmation." if lang != "id"
                   else "Ketik 'tolong urus klaim saya' dan saya susun rencana klaimnya; setiap pengajuan tetap perlu konfirmasi Anda.")
    return out


def digest_for_user(user_id: str, persona: Optional[str], as_of: date, extra_claims: Optional[list[OpenClaim]] = None) -> list[DigestItem]:
    """Sandbox read model: the account's own policies, premium rows and unfiled claims."""
    from ..sandbox import tools as sb
    from ..sandbox.persona_policies import PERSONA_HOLDINGS

    recs = sb.user_records(user_id)
    order = {pid: i for i, (pid, _r, _s) in enumerate(PERSONA_HOLDINGS.get(persona or "", []))}
    recs = sorted(recs, key=lambda p: (order.get(p.id, 999), p.id))
    premiums: dict[str, dict[str, Any]] = {}
    for row in sb.owned_policy_rows(user_id):
        rows = sb._rows("SELECT due_date, paid_date, amount FROM payments WHERE policy_id=?", row["id"])
        if not rows or row.get("premium_frequency") in (None, "employer", "statutory", "platform"):
            continue
        premiums[row["id"]] = premium_schedule(rows, row.get("premium_frequency"), row.get("premium_idr"), as_of)
    ids = sb.household_ids(user_id)
    claims = sb._rows(f"SELECT * FROM claims WHERE customer_id IN ({','.join('?' * len(ids))}) AND status='draft' ORDER BY id", *ids)
    open_claims = []
    decided = sb._rows(f"SELECT * FROM claims WHERE customer_id IN ({','.join('?' * len(ids))}) AND status IN ('submitted','under_review','approved','rejected','paid') ORDER BY decided_at DESC, filed_date DESC", *ids)
    status_items = [_status_item(r, as_of) for r in decided[:5]]
    for r in claims:
        amount = r.get("claim_amount") or r.get("billed_amount")
        open_claims.append(OpenClaim(claim_id=r["id"], policy_id=r["policy_id"], event=r.get("event_type") or "HOSPITALIZATION",
                                     amount=Decimal(amount) if amount else None,
                                     event_date=date.fromisoformat(r["event_date"]) if r.get("event_date") else None,
                                     discharge_date=date.fromisoformat(r["discharge_date"]) if r.get("discharge_date") else None))
    return [i for i in status_items if i is not None] + build_digest(recs, as_of=as_of, open_claims=open_claims + list(extra_claims or []), premiums=premiums)


_STATUS_TEXT = {
    "submitted": ("received by the insurer, waiting for review", "diterima penanggung, menunggu peninjauan"),
    "under_review": ("under review by the insurer", "sedang ditinjau penanggung"),
    "approved": ("approved by the insurer", "disetujui penanggung"),
    "rejected": ("rejected by the insurer", "ditolak penanggung"),
    "paid": ("paid by the insurer", "sudah dibayar penanggung"),
}


def _status_item(row: dict[str, Any], as_of: date) -> Optional[DigestItem]:
    """One line per claim that has left the customer's hands: where it is now, and the next move."""
    status = str(row.get("status") or "")
    if status not in _STATUS_TEXT:
        return None
    when_s = (row.get("decided_at") or row.get("filed_date") or as_of.isoformat())[:10]
    try:
        when = date.fromisoformat(when_s)
    except ValueError:
        when = as_of
    amount = row.get("claim_amount")
    money = f"IDR {int(amount):,}" if amount else ""
    en, idn = _STATUS_TEXT[status]
    note = str(row.get("decision_note") or row.get("rejection_code") or "").rstrip(". ")
    msg_en = f"Claim {row['id']} ({row.get('policy_id')}): {en}" + (f" ({money})" if money else "") + (f". Insurer's note: {note}" if note else "") + "."
    msg_id = f"Klaim {row['id']} ({row.get('policy_id')}): {idn}" + (f" ({money})" if money else "") + (f". Catatan penanggung: {note}" if note else "") + "."
    if status == "rejected":
        action = DigestAction(type="appeal_info", label_en="Help me appeal", label_id="Bantu saya banding", prompt=f"Please help me appeal claim {row['id']}")
        urgency = "this_week"
    else:
        action = DigestAction(type="none", label_en="", label_id="")
        urgency = "soon" if status in ("submitted", "under_review") else "later"
    return DigestItem(date=when, days_left=(when - as_of).days, policy_id=str(row.get("policy_id") or ""), product_name=str(row.get("policy_id") or ""),
                      kind="CLAIM_STATUS", money_at_risk=Decimal(int(amount)) if amount else None, currency="IDR", claim_id=row["id"], urgency=urgency,
                      message_en=msg_en[:400], message_id=msg_id[:400], action=action)
