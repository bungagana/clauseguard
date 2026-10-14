"""Thin compatibility layer. The hand-built duplicate policies that used to live here were removed:
`clauseguard.sandbox.persona_policies` (records, holdings, persona meta) is the single source of
truth for the UI, the API, the agent loop and the scripted tasks. These names only re-export it so
older imports keep working."""
from __future__ import annotations

from ..sandbox import persona_policies as _pp
from ..sandbox.persona_policies import PERSONA_BY_USER, PERSONA_META, holding_record
from ..schema import PolicyRecord

hcp_sompo = _pp.hcp_sompo_01
tl_astra = _pp.tl_astra_07
ci_chubb = _pp.ci_chubb_05
gh_nusa = _pp.gh_nusa_grp
gl_nusa = _pp.gl_nusa_grp
hcp_rider_b = _pp.hcp_rider_b
hi_indiv_s = _pp.hi_indiv_s
pa_chubb = _pp.pa_chubb_03
platform_acc = _pp.platform_acc


def jasa_raharja(pid: str = "JASA-RAHARJA") -> PolicyRecord:
    return holding_record(_pp.jasa_raharja(), pid, "active")


def bpjs_kes(pid: str, status: str) -> PolicyRecord:
    """A member's BPJS Kesehatan record (shared wording, member id and status)."""
    return holding_record(_pp.bpjs_kes(), pid, status)


def persona_policies(persona: str) -> list[PolicyRecord]:
    return _pp.policies_for_persona(persona)


__all__ = ["PERSONA_BY_USER", "PERSONA_META", "persona_policies", "hcp_sompo", "tl_astra", "ci_chubb", "gh_nusa", "gl_nusa", "hcp_rider_b",
           "hi_indiv_s", "pa_chubb", "platform_acc", "jasa_raharja", "bpjs_kes"]
