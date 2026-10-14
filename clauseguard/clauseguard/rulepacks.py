"""Coordination-of-benefits rule packs as data.

A rule pack fixes *who is asked to pay first*; the allocation optimizer (`allocation.py`)
then decides *how much* each payer in a layer pays. The pack is pure data (no code paths per
jurisdiction) so that a new jurisdiction is a new `RulePack` value, not a new branch.

Formulation
-----------
Let B be the eligible bill and let the payer layers be L_1, ..., L_m. Layer L_k receives the
unpaid remainder

    R_k = B - sum_{j < k} P_j

where P_j is the total paid by the policies of layer j. The layer order is:

1. statutory layers, in the order the pack lists them (each layer is one statutory scheme
   with a gate: the conditions under which it is the first payer);
2. commercial indemnity policies, grouped by class (employer group before individual when
   `group_before_individual` is set) and within a class by other-insurance kind
   primary (NONE / unstated) -> PRO_RATA -> EXCESS;
3. fixed-benefit policies are outside the sequence: they pay their stated amount whatever
   R is (`fixed_benefit_stacks`).

Two or more EXCESS policies in the same layer are circular (each is excess over the other);
the pack says how to resolve that (`circular_excess` = PRO_RATA by capacity).

Packs
-----
* `ID` (Indonesia): Jasa Raharja first for traffic accidents involving two or more vehicles
  (UU 33/34 1964, PMK 15-16/2017); BPJS Ketenagakerjaan JKK for work accidents of members;
  BPJS Kesehatan when the membership is active and the admission is at a partner facility
  (referral) or an emergency (Perpres 82/2018); employer group plans before individual plans;
  fixed benefits stack. Statutory amounts in the sandbox are modelled, so every statutory
  step carries a "verify" note.
* `GENERIC`: no statutory layer, no class rule; primary / PRO_RATA / EXCESS only.
"""
from __future__ import annotations

from typing import Optional

from pydantic import Field

from .schema import Condition, Op, Slot, Strict

PRIMARY_KINDS = {"NONE", "STACKABLE", None}
KIND_RANK: dict[Optional[str], int] = {"NONE": 0, "STACKABLE": 0, None: 0, "PRO_RATA": 1, "EXCESS": 2}


class StatutoryRule(Strict):
    """One statutory first-payer layer.

    `gate`: all conditions must hold for the scheme to be considered at all; an unbound gate
    slot means the scheme is silently not in play unless the slot is listed in
    `uncertain_on_unbound`, in which case the scheme is reported as uncertain on that slot.
    `any_of`: the scheme pays if at least one group of conditions holds; if no group holds and
    some group touched an unbound slot listed in `uncertain_on_unbound`, the scheme is
    uncertain on that slot; if no group holds otherwise, the scheme is excluded with `fail_code`.
    """

    rule_id: str = Field(max_length=80)
    product_type: str = Field(max_length=40)
    order: int
    gate: list[Condition] = Field(default_factory=list)
    any_of: list[list[Condition]] = Field(default_factory=list)
    uncertain_on_unbound: list[Slot] = Field(default_factory=list)
    fail_code: str = Field(max_length=60)
    not_applicable_code: Optional[str] = Field(default=None, max_length=60)
    payer_note: Optional[str] = Field(default=None, max_length=300)
    uncertain_note: Optional[str] = Field(default=None, max_length=300)
    excluded_notes: dict[str, str] = Field(default_factory=dict)
    legal_basis: Optional[str] = Field(default=None, max_length=200)


class RulePack(Strict):
    code: str = Field(max_length=16)
    name: str = Field(max_length=120)
    description: str = Field(max_length=600)
    statutory: list[StatutoryRule] = Field(default_factory=list)
    group_before_individual: bool = True
    fixed_benefit_stacks: bool = True
    default_other_insurance: str = Field(default="NONE", pattern=r"^(NONE|EXCESS|PRO_RATA)$")
    circular_excess: str = Field(default="PRO_RATA", pattern=r"^(PRO_RATA)$")
    legal_basis: list[str] = Field(default_factory=list)

    def statutory_rule(self, product_type: str) -> Optional[StatutoryRule]:
        for r in self.statutory:
            if r.product_type == product_type:
                return r
        return None

    def kind_rank(self, kind: Optional[str]) -> int:
        """0 primary, 1 pro-rata, 2 excess; an unstated kind takes the pack default."""
        k = kind if kind in KIND_RANK else None
        if k is None:
            k = self.default_other_insurance
        return KIND_RANK.get(k, 0)


ID_PACK = RulePack(
    code="ID",
    name="Indonesia (statutory schemes first, employer group before individual)",
    description=(
        "Jasa Raharja is the first payer for traffic accidents involving two or more vehicles; "
        "BPJS Ketenagakerjaan JKK for work accidents of members; BPJS Kesehatan at a partner "
        "facility or in an emergency while the membership is active; then employer group plans, "
        "then individual plans (primary, pro-rata, excess); fixed benefits stack."
    ),
    statutory=[
        StatutoryRule(
            rule_id="ID:JASA_RAHARJA_MULTI_VEHICLE", product_type="jasa_raharja", order=1,
            gate=[Condition(slot=Slot.IS_ACCIDENT, op=Op.IS_TRUE, note="accident")],
            any_of=[[Condition(slot=Slot.VEHICLES_INVOLVED, op=Op.GE, value=2, note="two or more vehicles")]],
            uncertain_on_unbound=[Slot.VEHICLES_INVOLVED],
            fail_code="SINGLE_VEHICLE_OR_NOT_TRAFFIC", not_applicable_code="SINGLE_VEHICLE_OR_NOT_TRAFFIC",
            payer_note="statutory first payer for multi-vehicle traffic accidents; sandbox cap, verify with Jasa Raharja",
            uncertain_note="applies only to traffic accidents involving another vehicle",
            excluded_notes={"SINGLE_VEHICLE_OR_NOT_TRAFFIC": "single-vehicle or non-traffic accidents are not covered by Jasa Raharja (sandbox rule, verify)"},
            legal_basis="UU 33/1964 and UU 34/1964; PMK 15/PMK.010/2017 and 16/PMK.010/2017 (modelled)",
        ),
        StatutoryRule(
            rule_id="ID:BPJS_TK_JKK", product_type="social_bpjs_tk", order=2,
            gate=[Condition(slot=Slot.IS_ACCIDENT, op=Op.IS_TRUE, note="accident")],
            any_of=[[Condition(slot=Slot.WORK_RELATED, op=Op.IS_TRUE, note="work accident")]],
            uncertain_on_unbound=[Slot.WORK_RELATED],
            fail_code="NOT_WORK_RELATED",
            payer_note="work accident: JKK pays medical as needed; BPJS Kesehatan excludes JKK-covered care",
            uncertain_note="JKK applies only if the accident happened at work or on the way to work",
            legal_basis="PP 44/2015 (JKK, modelled)",
        ),
        StatutoryRule(
            rule_id="ID:BPJS_KES", product_type="social_bpjs_kes", order=3,
            gate=[],
            any_of=[[Condition(slot=Slot.FACILITY_BPJS_PARTNER, op=Op.IS_TRUE, note="partner facility")],
                    [Condition(slot=Slot.IS_EMERGENCY, op=Op.IS_TRUE, note="emergency")]],
            uncertain_on_unbound=[Slot.FACILITY_BPJS_PARTNER],
            fail_code="NON_PARTNER_FACILITY",
            payer_note="first guarantor at a partner facility (INA-CBG tariff, sandbox mock); class-upgrade difference is out of pocket unless a COB agreement exists",
            uncertain_note="BPJS Kesehatan can be used only at a partner facility (with referral) or in an emergency",
            excluded_notes={
                "LAPSED": "BPJS Kesehatan inactive: settle arrears first (reactivation rules apply)",
                "NON_PARTNER_FACILITY": "non-partner facility and not an emergency: BPJS cannot be used for this admission",
            },
            legal_basis="Perpres 82/2018 (JKN benefits and coordination, modelled)",
        ),
    ],
    group_before_individual=True,
    fixed_benefit_stacks=True,
    default_other_insurance="NONE",
    legal_basis=["UU 33/1964, UU 34/1964 (Jasa Raharja)", "Perpres 82/2018 (JKN)", "PP 44/2015 (JKK)", "POJK 69/2016 (insurance business conduct)"],
)

GENERIC_PACK = RulePack(
    code="GENERIC",
    name="Generic (primary, pro-rata, excess)",
    description="No statutory layer and no class rule: policies pay in other-insurance order primary -> PRO_RATA -> EXCESS; fixed benefits stack.",
    statutory=[],
    group_before_individual=False,
    fixed_benefit_stacks=True,
    default_other_insurance="NONE",
)

RULE_PACKS: dict[str, RulePack] = {ID_PACK.code: ID_PACK, GENERIC_PACK.code: GENERIC_PACK}


def get_rule_pack(code: str) -> RulePack:
    """Rule pack by code (`ID`, `GENERIC`); unknown codes raise KeyError."""
    try:
        return RULE_PACKS[code.upper()]
    except KeyError as e:
        raise KeyError(f"unknown rule pack {code!r}; known: {sorted(RULE_PACKS)}") from e
