"""The single fact-derivation step for dates and day counts.

Stay length is an inclusive calendar-day count: admitted on D for n days means discharged on
D + n - 1, and a stay from D1 to D2 is (D2 - D1) + 1 days. A filing deadline is its anchor date
plus the clause's day count. Every consumer (agent loop, readiness, timeline, sandbox
entitlement view) calls these helpers so a date is derived one way only.

`derive_event_dates` completes the typed event dates the user stated with the ones that follow
from them, and records how each was obtained. Derived dates are never stored back as if the
user had stated them, so a later correction (a new day count, a new admission date) recomputes
them instead of leaving stale values behind.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Mapping, Optional

from ..schema import PeriodKind, PolicyRecord, Relation, ScenarioFacts, Slot, TimeUnit


def stay_days(admission: date, discharge: date) -> int:
    return max((discharge - admission).days + 1, 1)


def discharge_on(admission: date, days: int) -> date:
    return admission + timedelta(days=max(int(days), 1) - 1)


def admission_on(discharge: date, days: int) -> date:
    return discharge - timedelta(days=max(int(days), 1) - 1)


def filing_deadline(anchor: date, days: int) -> date:
    return anchor + timedelta(days=int(days))


def survival_end(diagnosis: date, days: int) -> date:
    return diagnosis + timedelta(days=int(days))


@dataclass(frozen=True)
class Derived:
    key: str
    value: date
    anchor_key: str
    anchor: date
    days: int

    def sentence(self, lang: str = "en") -> str:
        a = self.anchor.isoformat()
        if lang == "id":
            noun = {"discharge": "Tanggal pulang", "admission": "Tanggal masuk"}.get(self.key, self.key)
            src = {"admission": "tanggal masuk", "discharge": "tanggal pulang"}.get(self.anchor_key, self.anchor_key)
            return f"{noun} {self.value.isoformat()}: dihitung dari {src} Anda {a} dan {self.days} hari rawat inap."
        noun = {"discharge": "Discharge date", "admission": "Admission date"}.get(self.key, self.key)
        return f"{noun} {self.value.isoformat()}: calculated from your {self.anchor_key} date {a} and {self.days} day{'s' if self.days != 1 else ''} in hospital."


def derive_event_dates(stated: Mapping[str, date], facts: ScenarioFacts) -> tuple[dict[str, date], dict[str, Derived]]:
    """(stated + derived dates, how each derived date was obtained)."""
    dates = dict(stated)
    derived: dict[str, Derived] = {}
    days: Optional[int] = None
    if facts.has(Slot.DAYS_HOSPITALIZED):
        try:
            days = int(facts.get(Slot.DAYS_HOSPITALIZED))
        except (TypeError, ValueError):
            days = None
    if days is not None and days >= 1:
        if "admission" in dates and "discharge" not in dates:
            d = discharge_on(dates["admission"], days)
            dates["discharge"] = d
            derived["discharge"] = Derived("discharge", d, "admission", dates["admission"], days)
        elif "discharge" in dates and "admission" not in dates:
            d = admission_on(dates["discharge"], days)
            dates["admission"] = d
            derived["admission"] = Derived("admission", d, "discharge", dates["discharge"], days)
    if "discharge" in dates and "treatment_end" not in dates:
        dates["treatment_end"] = dates["discharge"]
    return dates, derived


def survival_period(policy: PolicyRecord) -> tuple[Optional[int], Optional[str]]:
    """(days, tuple id) of the survival period when it is stated in days."""
    for t in policy.tuples_by(Relation.HAS_PERIOD):
        q = t.qualifiers
        if (q.period_kind == PeriodKind.SURVIVAL or t.object == PeriodKind.SURVIVAL.value) and q.window_len is not None and q.window_unit in (None, TimeUnit.DAYS):
            return int(q.window_len), t.id
    return None, None
