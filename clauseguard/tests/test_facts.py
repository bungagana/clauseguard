"""bind_facts: LLM mocked; derived slots computed in code; merge with prior; never invent."""
from datetime import date

from clauseguard.agent.facts import FactSheet, bind_facts, derive_slots
from clauseguard.schema import EventCode, PolicyRecord, ScenarioFacts, Slot


def policy(**kw) -> PolicyRecord:
    base = dict(id="P1", doc_id="D1", insurer="X", product_name="Term", product_type="term_life",
                issue_date=date(2024, 1, 15), effective_date=date(2024, 1, 15), grace_days=31)
    base.update(kw)
    return PolicyRecord(**base)


def mock(sheet: FactSheet):
    return lambda text, as_of, model: sheet


def test_relative_durations_become_derived_slots():
    sheet = FactSheet(event=EventCode.DEATH, subject="INSURED", cause="SUICIDE", months_since_issue=13)
    f = bind_facts("suicide 13 months after issue", policies=[policy()], as_of=date(2026, 10, 11), _fill=mock(sheet))
    assert f.get(Slot.EVENT) == "DEATH"
    assert f.get(Slot.CAUSE) == "SUICIDE"
    assert f.get(Slot.MONTHS_SINCE_ISSUE) == 13
    assert f.get(Slot.POLICY_YEAR) == 2
    assert f.get(Slot.DAYS_SINCE_EFFECTIVE) == int(13 * 30.4)
    assert f.get(Slot.PARTIES_BOTH_DEAD) is False
    # nothing invented
    assert not f.has(Slot.AGE) and not f.has(Slot.PREMIUM_STATUS) and not f.has(Slot.MISREPRESENTATION)


def test_dates_from_policy_record_anchor_derived_slots():
    sheet = FactSheet(event=EventCode.HOSPITALIZATION, cause="ILLNESS", admission_date=date(2024, 2, 28),
                      discharge_date=date(2024, 3, 3), premium_due_date=date(2024, 2, 15))
    f = bind_facts("...", policies=[policy()], as_of=date(2024, 3, 10), _fill=mock(sheet))
    assert f.get(Slot.DAYS_SINCE_EFFECTIVE) == (date(2024, 2, 28) - date(2024, 1, 15)).days
    assert f.get(Slot.MONTHS_SINCE_ISSUE) == 1
    assert f.get(Slot.DAYS_HOSPITALIZED) == 5  # inclusive calendar days (28 Feb..3 Mar 2024)
    assert f.get(Slot.DAYS_SINCE_DISCHARGE) == 7
    assert f.get(Slot.DAYS_OVERDUE) == 13
    assert f.get(Slot.PREMIUM_STATUS) == "OVERDUE"


def test_composed_events_and_life_expectancy():
    v = derive_slots(FactSheet(event=EventCode.DEATH, subject="CHILD", age=10), None, date(2026, 1, 1))
    assert v[Slot.EVENT] == "CHILD_DEATH" and v[Slot.AGE] == 10
    v = derive_slots(FactSheet(event=EventCode.DEATH, subject="BOTH_INSUREDS", cause="ACCIDENT"), None, date(2026, 1, 1))
    assert v[Slot.EVENT] == "JOINT_DEATH" and v[Slot.PARTIES_BOTH_DEAD] is True and v[Slot.IS_ACCIDENT] is True
    v = derive_slots(FactSheet(event=EventCode.TERMINAL_ILLNESS, life_expectancy_months=10), None, date(2026, 1, 1))
    assert v[Slot.SURVIVAL_DAYS] == 304


def test_prior_merge_later_turn_wins():
    prior = ScenarioFacts(values={Slot.EVENT: "DEATH", Slot.MONTHS_SINCE_ISSUE: 10, Slot.AGE: 40})
    sheet = FactSheet(months_since_issue=13)
    f = bind_facts("sorry, it was 13 months", policies=[policy()], as_of=date(2026, 1, 1), prior=prior, _fill=mock(sheet))
    assert f.get(Slot.MONTHS_SINCE_ISSUE) == 13
    assert f.get(Slot.EVENT) == "DEATH" and f.get(Slot.AGE) == 40  # untouched prior slots survive


def test_empty_sheet_binds_nothing():
    f = bind_facts("hello", policies=[policy()], as_of=date(2026, 1, 1), _fill=mock(FactSheet()))
    assert f.values == {}
