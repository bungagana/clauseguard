"""ABox (ground-truth ontology instances) -> oracle PolicyRecord per contract.

Reads data/benchmark/ontologies/life_insurance_abox.ttl with rdflib and emits one
PolicyRecord per contract (C1..C10) whose tuples carry source_tier POLICY_DOC_VERIFIED.
This is the "B4-oracle" condition: it separates extraction error from solver error.

Mapping summary (see bench/README.md for the full table and the unmapped classes):
  SuicideExclusion            -> HAS_PERIOD SUICIDE (window months from ISSUE, benefit_type)
  *GracePeriod (with days)    -> HAS_PERIOD GRACE (window days from PREMIUM_DUE)
  IncontestabilityProvision   -> HAS_PERIOD CONTESTABILITY (window years from ISSUE)
  FreeLookProvision           -> PERMITS FREE_LOOK (applies_if days_since_effective <= N)
  WarExclusion                -> EXCLUDES WAR (window months if time-bounded)
  AviationExclusion           -> EXCLUDES AVIATION + EXCEPTS (pilot_role == PASSENGER)
  *DeathBenefit               -> COVERS DEATH (amount / graded / salary formula)
  SurvivorshipDeathBenefit    -> COVERS JOINT_DEATH, COVERS JOINT_FIRST_DEATH (no benefit, continues),
                                 EXCLUDES DEATH applies_if parties_both_dead == False
  Riders                      -> RiderRecord + rider-scoped COVERS/EXCLUDES/TERMINATES_IF
  PolicyLoan / PartialWithdrawal / Cash surrender / Conversion / Reinstatement -> PERMITS (+ CONDITIONED_ON)
  CoverageTerminationTrigger  -> TERMINATES_IF (employment_active == False) + COVERS GROUP_TERMINATION
  Automatic non-forfeiture    -> COVERS LAPSE
  ReturnOfPremiumBenefit      -> COVERS RETURN_OF_PREMIUM
  Other provisions            -> DEFINES (display only)
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any, Optional

from rdflib import Graph, Literal, Namespace, RDF, URIRef

from clauseguard import config
from clauseguard.schema import (
    Basis,
    ClauseTuple,
    Condition,
    Evidence,
    Op,
    PeriodKind,
    PolicyRecord,
    Qualifiers,
    Relation,
    RiderRecord,
    Slot,
    SourceTier,
    TimeUnit,
    WindowFrom,
)

LI = Namespace("http://www.lifeinsurance.org/ontology#")
ABOX = Namespace("http://www.lifeinsurance.org/ontology/abox#")

ABOX_PATH = config.DATA_DIR / "benchmark" / "ontologies" / "life_insurance_abox.ttl"
ORACLE_DIR = config.DATA_DIR / "benchmark" / "oracle"
DAYS_PER_MONTH = 30.4

PRODUCT_TYPE = {
    "LevelTermPolicy": "term_life", "TermWithRidersPolicy": "term_life", "ReturnOfPremiumTermPolicy": "term_life_rop",
    "ParticipatingWholeLifePolicy": "whole_life", "FinalExpensePolicy": "final_expense", "JointSurvivorshipPolicy": "joint_survivorship",
    "UniversalLifePolicy": "universal_life", "VariableUniversalLifePolicy": "variable_universal_life",
    "IndexedUniversalLifePolicy": "indexed_universal_life", "GroupLifeCertificate": "group_term",
}
SUICIDE_BENEFIT = {
    "ReturnPremiumsPaid": "RETURN_PREMIUMS", "ReturnPremiumsMinusWithdrawals": "RETURN_PREMIUMS",
    "ReturnPremiumsMinusWithdrawalsAndCharges": "RETURN_PREMIUMS", "ReturnAccountValue": "REDUCED", "NoBenefit": "NONE",
}
RIDER_CLASSES = {
    "WaiverOfPremiumRider", "AccidentalDeathBenefitRider", "ChildrenTermRider", "GuaranteedInsurabilityRider",
    "TerminalIllnessADBRider", "ChronicIllnessADBRider", "NoLapseGuaranteeRider", "AviationExclusionWaiver",
}
# Classes with no solver semantics: recorded as DEFINES tuples (display/citation only).
DEFINES_CLASSES = {
    "MisstatementOfAgeProvision", "AssignmentProvision", "BeneficiaryChangeProvision", "SettlementOptionProvision",
    "PortabilityProvision", "SplitOption", "SimultaneousDeathEvent", "GuaranteedRenewabilityProvision",
    "DeathBenefitChangeOption", "LateEntrantProvision", "EstateTaxLiquidityProvision", "ThreeYearLookbackRule",
    "CrummeyPower", "ReducedPaidUpOption", "ExtendedTermOption", "CashSurrenderOption",
}
# Classes deliberately not mapped (financial mechanics; outside the solver's vocabulary).
UNMAPPED_CLASSES = {
    "Insured", "FirstInsured", "SecondInsured", "PolicyOwner", "PrimaryBeneficiary", "ContingentBeneficiary", "Insurer",
    "Employee", "Employer", "IrrevocableTrust", "MasterGroupPolicy", "LevelPremium", "FlexiblePremium",
    "EmployerPaidPremium", "EmployeePaidPremium", "PremiumLoad", "GuaranteedCashValue", "AccountValue",
    "CostOfInsurance", "AdministrativeCharge", "MortalityAndExpenseCharge", "FixedInterestCrediting",
    "VariableSubAccountCrediting", "IndexedCrediting", "DividendCrediting", "SubAccount", "IndexAccount", "CapRate",
    "FloorRate", "ParticipationRate", "PaidUpAdditionsDividendOption",
}


def _local(u: Any) -> str:
    s = str(u)
    return s.split("#")[-1] if "#" in s else s.rsplit("/", 1)[-1]


def _py(lit: Any) -> Any:
    if isinstance(lit, Literal):
        v = lit.toPython()
        return v
    return _local(lit)


class Entity:
    def __init__(self, g: Graph, uri: URIRef):
        self.uri = uri
        self.id = _local(uri)
        self.cls = next((_local(o) for o in g.objects(uri, RDF.type)), "")
        self.props: dict[str, list[Any]] = defaultdict(list)
        for p, o in g.predicate_objects(uri):
            if p == RDF.type:
                continue
            self.props[_local(p)].append(_py(o))

    def one(self, name: str, default: Any = None) -> Any:
        vals = self.props.get(name)
        return vals[0] if vals else default

    def many(self, name: str) -> list[Any]:
        return list(self.props.get(name, []))

    @property
    def section(self) -> Optional[str]:
        s = self.one("sourceContractSection")
        return str(s)[:80] if s else None

    @property
    def text(self) -> Optional[str]:
        t = self.one("coverageSourceText")
        return str(t) if t else None


class Builder:
    def __init__(self, g: Graph, policy_uri: URIRef):
        self.g = g
        self.pol = Entity(g, policy_uri)
        self.cid = str(self.pol.one("sourceContractID"))
        self.tuples: list[ClauseTuple] = []
        self.riders: list[RiderRecord] = []
        self.unmapped: list[tuple[str, str]] = []
        self.seen: set[str] = set()
        self.linked: dict[str, Entity] = {}

    # ---------------------------------------------------------------- helpers
    def ev(self, e: Entity, fallback: str) -> Evidence:
        text = e.text or fallback
        return Evidence(doc_id=self.cid, section=e.section, text=text[:1200])

    def add(self, e: Entity, relation: Relation, obj: str, *, head: Optional[str] = None, q: Optional[Qualifiers] = None,
            suffix: str = "", fallback: Optional[str] = None) -> ClauseTuple:
        tid = f"{e.id}{suffix}"
        t = ClauseTuple(
            id=tid, policy_id=self.cid, head=head or self.cid, relation=relation, object=obj,
            qualifiers=q or Qualifiers(), evidence=self.ev(e, fallback or f"{e.cls} ({e.section or 'section not given'})"),
            source_tier=SourceTier.POLICY_DOC_VERIFIED, extractor_version="abox-oracle-1.0",
        )
        self.tuples.append(t)
        return t

    def entity(self, uri: URIRef) -> Entity:
        e = Entity(self.g, uri)
        self.linked[e.id] = e
        return e

    # ---------------------------------------------------------------- dispatch
    def build(self) -> PolicyRecord:
        p = self.pol
        link_props = ["hasDeathBenefit", "hasGracePeriod", "hasExclusion", "hasProvision", "hasRider", "hasLivingBenefit",
                      "hasPolicyLoan", "hasPartialWithdrawal", "hasSurrenderCharge", "hasNonForfeitureOption", "hasCashValue",
                      "hasPremium", "hasCharge", "hasCreditingMechanism", "hasSubAccount", "hasIndexAccount",
                      "hasDividendOption", "hasEstatePlanningProvision", "hasInsured", "hasFirstInsured", "hasSecondInsured",
                      "hasOwner", "issuedBy", "hasPrimaryBeneficiary", "hasContingentBeneficiary", "hasEmployee",
                      "heldByEmployer", "governedByMasterPolicy", "heldInTrust"]
        ents: list[Entity] = []
        for prop in link_props:
            for o in self.g.objects(p.uri, LI[prop]):
                ents.append(self.entity(o))
        is_group = p.cls == "GroupLifeCertificate"
        has_surrender = False
        for e in ents:
            c = e.cls
            if c.endswith("DeathBenefit") or c in ("BasicGroupCoverage", "VoluntarySupplementalCoverage"):
                self.death_benefit(e)
            elif c in ("PremiumNonpaymentGracePeriod", "AccountValueDepletionGracePeriod"):
                self.grace(e)
            elif c == "SuicideExclusion":
                self.suicide(e)
            elif c == "WarExclusion":
                self.war(e)
            elif c == "AviationExclusion":
                self.aviation(e)
            elif c in ("DrugAlcoholExclusion", "PreExistingConditionExclusion", "MaterialMisrepresentation"):
                obj = {"DrugAlcoholExclusion": "INTOXICATION", "PreExistingConditionExclusion": "PRE_EXISTING_CONDITION",
                       "MaterialMisrepresentation": "MISREPRESENTATION"}[c]
                self.add(e, Relation.EXCLUDES, obj)
            elif c == "IncontestabilityProvision":
                yrs = int(e.one("contestabilityPeriodYears", 2))
                self.add(e, Relation.HAS_PERIOD, "CONTESTABILITY", q=Qualifiers(
                    period_kind=PeriodKind.CONTESTABILITY, window_len=yrs, window_unit=TimeUnit.YEARS, window_from=WindowFrom.ISSUE),
                    fallback=f"Incontestability: the policy may be contested for material misrepresentation within {yrs} years of issue.")
            elif c == "FreeLookProvision":
                days = int(e.one("freeLookDays", 0))
                self.add(e, Relation.PERMITS, "FREE_LOOK", q=Qualifiers(
                    window_len=days, window_unit=TimeUnit.DAYS, window_from=WindowFrom.EFFECTIVE,
                    applies_if=[Condition(slot=Slot.DAYS_SINCE_EFFECTIVE, op=Op.LE, value=days)]),
                    fallback=f"Free look: the owner may cancel within {days} days of receipt for a full refund of premiums paid.")
            elif c == "ConversionPrivilege":
                q = Qualifiers(age_max=_int_or_none(e.one("conversionMaxAge")), deadline_days=_int_or_none(e.one("conversionDeadlineDays")),
                               formula=_fmt_conv(e))
                if is_group:
                    q.from_event = WindowFrom.EVENT
                self.add(e, Relation.PERMITS, "CONVERSION", q=q, fallback="Conversion to an individual permanent policy without evidence of insurability. " + (q.formula or ""))
            elif c == "ReinstatementProvision":
                yrs = int(e.one("reinstatementPeriodYears", 0))
                q = Qualifiers(window_len=yrs, window_unit=TimeUnit.YEARS, window_from=WindowFrom.EVENT,
                               applies_if=[Condition(slot=Slot.DAYS_SINCE_EVENT, op=Op.LE, value=int(yrs * 365), note="years since lapse")],
                               resets_on_reinstatement=bool(e.one("reinstatementNewSuicidePeriod", False)) or None,
                               formula=f"reinstate within {yrs} years of lapse; overdue premiums + {e.one('reinstatementInterestRate', '?')}% interest; evidence of insurability")
                self.add(e, Relation.PERMITS, "REINSTATEMENT", q=q, fallback="Reinstatement: " + (q.formula or ""))
            elif c == "PolicyLoan":
                self.policy_loan(e)
            elif c == "PartialWithdrawal":
                q = Qualifiers(formula=f"minimum ${_num(e.one('withdrawalMinimumAmount'))}; fee ${_num(e.one('withdrawalFeePerTransaction'))} per withdrawal")
                self.add(e, Relation.PERMITS, "PARTIAL_WITHDRAWAL", q=q, fallback="Partial withdrawal from account value permitted. " + q.formula)
            elif c == "SurrenderCharge":
                if not has_surrender:
                    has_surrender = True
                    q = Qualifiers(period_kind=PeriodKind.SURRENDER_CHARGE, window_len=_int_or_none(e.one("surrenderChargePeriodYears")),
                                   window_unit=TimeUnit.YEARS, window_from=WindowFrom.ISSUE, formula=(e.text or "")[:200] or None)
                    self.add(e, Relation.PERMITS, "SURRENDER", q=q, fallback="Full surrender permitted; surrender charge schedule applies.")
            elif c == "CashSurrenderOption":
                if not has_surrender:
                    has_surrender = True
                    self.add(e, Relation.PERMITS, "SURRENDER", fallback="Cash surrender: receive the cash surrender value and terminate the policy.")
                else:
                    self.add(e, Relation.DEFINES, c)
            elif c in ("ReducedPaidUpOption", "ExtendedTermOption"):
                auto = c == "ExtendedTermOption" or "automatic" in (e.text or "").lower()
                if auto:
                    self.add(e, Relation.COVERS, "LAPSE", q=Qualifiers(benefit_type="REDUCED", formula=f"automatic non-forfeiture: {c}"),
                             fallback=f"{c}: applies automatically if no election is made after lapse.")
                else:
                    self.add(e, Relation.DEFINES, c)
            elif c in ("GuaranteedCashValue",):
                self.unmapped.append((e.id, c))
            elif c == "WaiverOfPremiumProvision":
                self.waiver(e, head=None)
            elif c == "TerminalIllnessADB":
                self.terminal_illness(e, head=None)
            elif c == "ReturnOfPremiumBenefit":
                q = Qualifiers(pct_of_sum_assured=None, formula=f"{_num(e.one('ropPercentAtEndOfTerm'))}% of premiums at end of term; -{_num(e.one('ropLatePremiumPenaltyPercentage'))}% per late premium; forfeited on lapse")
                self.add(e, Relation.COVERS, "RETURN_OF_PREMIUM", q=q)
            elif c == "CoverageTerminationTrigger":
                self.add(e, Relation.TERMINATES_IF, "GROUP_TERMINATION", q=Qualifiers(
                    applies_if=[Condition(slot=Slot.EMPLOYMENT_ACTIVE, op=Op.IS_FALSE, note="cease active full-time employment")]))
                self.add(e, Relation.COVERS, "GROUP_TERMINATION", suffix="#continuation", q=Qualifiers(
                    formula="coverage ends; conversion / portability must be applied for within 31 days"),
                    fallback="Coverage terminates on cessation of employment; conversion and portability rights follow.")
            elif c in RIDER_CLASSES:
                self.rider(e)
            elif c in DEFINES_CLASSES:
                self.add(e, Relation.DEFINES, c)
            elif c in UNMAPPED_CLASSES or c.endswith("Premium") or c.endswith("Charge") or c.endswith("Crediting"):
                self.unmapped.append((e.id, c))
            else:
                self.unmapped.append((e.id, c))
        # cash value implies the contract can be surrendered for it (C8 has cash value but no explicit surrender entity)
        if not has_surrender:
            cv = next((e for e in ents if e.cls in ("GuaranteedCashValue", "AccountValue")), None)
            if cv is not None:
                self.add(cv, Relation.PERMITS, "SURRENDER", suffix="#surrender", fallback="Policy accumulates cash value; surrender for the cash value is available.")
        if self.pol.one("lapseAutoPaysSurrenderValue") and not any(t.relation == Relation.COVERS and t.object == "LAPSE" for t in self.tuples):
            fake = Entity(self.g, self.pol.uri)
            self.add(fake, Relation.COVERS, "LAPSE", suffix="#lapse_auto", q=Qualifiers(benefit_type="REDUCED", formula="on lapse the net surrender value is paid automatically"),
                     fallback="If the policy lapses, any net cash surrender value is paid automatically.")

        grace = next((t for t in self.tuples if t.relation == Relation.HAS_PERIOD and t.object == "GRACE"), None)
        issue = _date(self.pol.one("issueDate"))
        rec = PolicyRecord(
            id=self.cid, doc_id=self.cid, insurer=str(self.linked_insurer() or "unknown")[:80],
            product_name=str(self.pol.one("policyNumber", self.cid))[:120], product_type=PRODUCT_TYPE.get(self.pol.cls, "life"),
            basis=Basis.FIXED_BENEFIT, effective_date=_date(self.pol.one("effectiveDate")) or issue, issue_date=issue,
            expiry_date=_date(self.pol.one("expiryDate")), grace_days=grace.qualifiers.window_len if grace else None,
            sum_assured=_dec(self.pol.one("faceAmount")), currency="USD", riders=self.riders, tuples=self.tuples,
            verified=True, extraction_coverage=1.0,
        )
        return rec

    def linked_insurer(self) -> Optional[str]:
        for e in self.linked.values():
            if e.cls == "Insurer":
                return e.one("insurerName")
        return None

    # ---------------------------------------------------------------- mappers
    def death_benefit(self, e: Entity):
        amt = _dec(e.one("faceAmount"))
        if e.cls == "SurvivorshipDeathBenefit":
            self.add(e, Relation.COVERS, "JOINT_DEATH", q=Qualifiers(amount=amt, currency="USD", basis=Basis.FIXED_BENEFIT),
                     fallback="Death benefit payable upon the death of the second insured to die.")
            self.add(e, Relation.COVERS, "JOINT_FIRST_DEATH", suffix="#first_death", q=Qualifiers(benefit_type="NONE", formula="no benefit at first death; policy continues in force covering the survivor"),
                     fallback="If the first insured dies, no death benefit is paid and the policy continues in force covering the surviving insured.")
            self.add(e, Relation.EXCLUDES, "DEATH", suffix="#not_both_dead", q=Qualifiers(
                benefit_type="NONE", applies_if=[Condition(slot=Slot.PARTIES_BOTH_DEAD, op=Op.IS_FALSE, note="survivorship: payable only after both insureds die")]),
                fallback="The death benefit is payable only upon the death of the SECOND insured to die.")
            return
        q = Qualifiers(amount=amt, currency="USD", basis=Basis.FIXED_BENEFIT)
        if e.cls == "GradedDeathBenefit":
            q.benefit_type = "GRADED"
            q.formula = (f"Year 1: {_num(e.one('gradedBenefitYear1Percent'))}% + premiums; Year 2: {_num(e.one('gradedBenefitYear2Percent'))}% + premiums; "
                         f"Year {e.one('gradedBenefitFullYear')}+: 100%; accidental death: full benefit at any time")[:200]
        elif e.cls == "BasicGroupCoverage":
            q.formula = f"{_num(e.one('salaryMultiple'))} x annual base salary, rounded up to next $1,000"[:200]
        elif e.cls == "VoluntarySupplementalCoverage":
            q.plan = "VOLUNTARY"
            q.formula = f"increments of $10,000 up to 5 x salary; total max ${_num(e.one('salaryMaxTotalCoverage'))}"[:200]
        elif e.cls == "IncreasingDeathBenefit":
            q.formula = "face amount + account value (Option II)"
        fb = f"Death benefit of ${_num(amt)} payable if the insured dies while the policy is in force."
        self.add(e, Relation.COVERS, "DEATH", q=q, fallback=fb)

    def grace(self, e: Entity):
        days = _int_or_none(e.one("gracePeriodDays"))
        if days is None:  # C6: grace period entity without a day count -> cannot be a window; record as DEFINES
            self.add(e, Relation.DEFINES, "GracePeriod(no_days)")
            self.unmapped.append((e.id, f"{e.cls} without gracePeriodDays"))
            return
        q = Qualifiers(period_kind=PeriodKind.GRACE, window_len=days, window_unit=TimeUnit.DAYS, window_from=WindowFrom.PREMIUM_DUE)
        self.add(e, Relation.HAS_PERIOD, "GRACE", q=q, fallback=f"Grace period of {days} days after the premium due date; coverage continues during the grace period.")

    def suicide(self, e: Entity):
        months = int(e.one("suicideExclusionPeriodMonths", 24))
        bt = SUICIDE_BENEFIT.get(str(e.one("suicideBenefitType", "")), None)
        q = Qualifiers(period_kind=PeriodKind.SUICIDE, window_len=months, window_unit=TimeUnit.MONTHS, window_from=WindowFrom.ISSUE, benefit_type=bt)
        self.add(e, Relation.HAS_PERIOD, "SUICIDE", q=q, fallback=f"Suicide within {months} months of issue: liability limited ({bt}).")

    def war(self, e: Entity):
        q = Qualifiers()
        if e.one("exclusionIsTimeBounded") and e.one("exclusionPeriodMonths") is not None:
            q = Qualifiers(window_len=int(e.one("exclusionPeriodMonths")), window_unit=TimeUnit.MONTHS, window_from=WindowFrom.ISSUE)
        self.add(e, Relation.EXCLUDES, "WAR", q=q, fallback="Death while serving in a military conflict in a war zone is excluded.")

    def aviation(self, e: Entity):
        q = Qualifiers()
        if e.one("exclusionIsTimeBounded") and e.one("exclusionPeriodMonths") is not None:
            q = Qualifiers(window_len=int(e.one("exclusionPeriodMonths")), window_unit=TimeUnit.MONTHS, window_from=WindowFrom.ISSUE)
        x = self.add(e, Relation.EXCLUDES, "AVIATION", q=q, fallback="Death resulting from operating an aircraft as pilot or crew member is excluded.")
        self.add(e, Relation.EXCEPTS, x.id, suffix="#passenger", q=Qualifiers(
            applies_if=[Condition(slot=Slot.PILOT_ROLE, op=Op.EQ, value="PASSENGER", note="exclusion is limited to pilot/crew")]),
            fallback="The aviation exclusion applies to pilot or crew only; passengers are not excluded.")

    def policy_loan(self, e: Entity):
        q = Qualifiers(formula=f"max {_num(e.one('policyLoanMaxPercentOfCV'))}% of cash/surrender value; interest {e.one('policyLoanInterestRate', e.one('policyLoanInterestRateFormula', '?'))} ({e.one('policyLoanInterestRateType', '?')})"[:200])
        self.add(e, Relation.PERMITS, "POLICY_LOAN", q=q, fallback="Policy loans against the cash value are available. " + (q.formula or ""))
        yrs = _int_or_none(e.one("loanMinimumYearsInForce"))
        if yrs:
            self.add(e, Relation.CONDITIONED_ON, "POLICY_LOAN", suffix="#min_years", q=Qualifiers(
                applies_if=[Condition(slot=Slot.MONTHS_SINCE_ISSUE, op=Op.GE, value=yrs * 12, note=f"policy in force {yrs} year(s)")]),
                fallback=f"Loans are available only after the policy has been in force for {yrs} full year(s).")

    def waiver(self, e: Entity, head: Optional[str]):
        wait_m = _int_or_none(e.one("waiverDisabilityWaitingMonths"))
        max_age = _int_or_none(e.one("waiverMaxAgeAtDisability"))
        conds = []
        if max_age is not None:
            conds.append(Condition(slot=Slot.AGE, op=Op.LE, value=max_age, note="age at disability onset"))
        if wait_m:
            conds.append(Condition(slot=Slot.DAYS_SINCE_EVENT, op=Op.GE, value=int(wait_m * DAYS_PER_MONTH), note=f"disabled >= {wait_m} months"))
        q = Qualifiers(applies_if=conds, age_max=max_age, waiting_days=int(wait_m * DAYS_PER_MONTH) if wait_m else None,
                       formula=f"premiums waived after {wait_m} months of total disability; disability before age {max_age}; ends at {e.one('waiverTerminationAge', '?')}")
        self.add(e, Relation.COVERS, "PREMIUM_WAIVER", head=head, q=q, fallback="Waiver of premium: " + (q.formula or ""))

    def terminal_illness(self, e: Entity, head: Optional[str]):
        le = _int_or_none(e.one("terminalIllnessLifeExpectancyMonths"))
        q = Qualifiers(pct_of_sum_assured=_float_or_none(e.one("adbMaxPercentOfFaceAmount")), annual_cap=None,
                       per_case_limit=_dec(e.one("adbMaximumAmount")),
                       formula=f"advance up to {_num(e.one('adbMaxPercentOfFaceAmount'))}% of face (min ${_num(e.one('adbMinimumAmount'))}, max ${_num(e.one('adbMaximumAmount'))}); life expectancy <= {le} months"[:200])
        self.add(e, Relation.COVERS, "TERMINAL_ILLNESS", head=head, q=q, fallback="Accelerated death benefit for terminal illness. " + (q.formula or ""))
        if le:
            self.add(e, Relation.CONDITIONED_ON, "TERMINAL_ILLNESS", head=head, suffix="#life_expectancy", q=Qualifiers(
                applies_if=[Condition(slot=Slot.SURVIVAL_DAYS, op=Op.LE, value=int(round(le * DAYS_PER_MONTH)), note=f"certified life expectancy <= {le} months")]),
                fallback=f"Terminal illness means a life expectancy of {le} months or less as certified by a physician.")

    def rider(self, e: Entity):
        c = e.cls
        attached = str(e.one("coverageStatus", "covered")) != "not_selected"
        self.riders.append(RiderRecord(id=e.id, rider_type=c[:60], attached=attached, sum_assured=_dec(e.one("adbRiderAdditionalBenefitAmount") or e.one("childrenRiderCoverageAmount"))))
        if c == "WaiverOfPremiumRider":
            self.waiver(e, head=e.id)
        elif c == "TerminalIllnessADBRider":
            self.terminal_illness(e, head=e.id)
        elif c == "ChronicIllnessADBRider":
            q = Qualifiers(pct_of_sum_assured=_float_or_none(e.one("chronicIllnessMaxTotalPercentage")),
                           formula=f"unable to perform >= {e.one('adlMinimumUnableToPerform')} ADLs for {e.one('adlQualifyingPeriodDays')} days; {_num(e.one('chronicallyIllMonthlyAdvancePercentage'))}%/month up to {_num(e.one('chronicIllnessMaxTotalPercentage'))}%"[:200])
            self.add(e, Relation.COVERS, "CHRONIC_ILLNESS", head=e.id, q=q, fallback="Chronic illness accelerated benefit. " + (q.formula or ""))
        elif c == "ChildrenTermRider":
            max_age = int(e.one("childrenRiderMaxAge", 25))
            amt = _dec(e.one("childrenRiderCoverageAmount"))
            # coverage is unconditional; the age limit is a termination (so an over-age child is DENIED, not N/A)
            self.add(e, Relation.COVERS, "CHILD_DEATH", head=e.id, q=Qualifiers(amount=amt, currency="USD", age_max=max_age),
                fallback=f"Children's term rider: ${_num(amt)} on the death of a covered child, from birth to age {max_age}.")
            self.add(e, Relation.TERMINATES_IF, "CHILD_DEATH", head=e.id, suffix="#max_age", q=Qualifiers(
                applies_if=[Condition(slot=Slot.AGE, op=Op.GE, value=max_age, note="coverage ends at rider max age")]),
                fallback=f"A child's coverage under the rider ends at age {max_age}.")
        elif c == "AccidentalDeathBenefitRider":
            window = _int_or_none(e.one("adbRiderAccidentDeathWindowDays"))
            conds = [Condition(slot=Slot.DAYS_SINCE_EVENT, op=Op.LE, value=window, note="death within window after accident")] if window else []
            q = Qualifiers(amount=_dec(e.one("adbRiderAdditionalBenefitAmount")), currency="USD", basis=Basis.FIXED_BENEFIT, age_max=_int_or_none(e.one("adbRiderTerminationAge")),
                           window_len=window, window_unit=TimeUnit.DAYS, window_from=WindowFrom.ACCIDENT, applies_if=conds)
            self.add(e, Relation.COVERS, "ACCIDENTAL_DEATH", head=e.id, q=q, fallback=f"Accidental death benefit rider: additional ${_num(q.amount)} if death results from accidental injury within {window} days.")
        elif c == "GuaranteedInsurabilityRider":
            q = Qualifiers(age_max=_int_or_none(e.one("gioTerminationAge")), amount=_dec(e.one("gioMaxCoveragePerOption")), formula=str(e.one("gioOptionDates", ""))[:200])
            self.add(e, Relation.PERMITS, "GUARANTEED_INSURABILITY", head=e.id, q=q, fallback="Guaranteed insurability option: purchase additional coverage without evidence of insurability on option dates. " + (q.formula or ""))
        elif c == "NoLapseGuaranteeRider":
            self.add(e, Relation.DEFINES, c, head=e.id)
        elif c == "AviationExclusionWaiver":
            self.add(e, Relation.DEFINES, c, head=e.id)


def _fmt_conv(e: Entity) -> str:
    parts = []
    if e.one("conversionMaxAge") is not None:
        parts.append(f"before age {e.one('conversionMaxAge')}")
    if e.one("conversionDeadlineDays") is not None:
        parts.append(f"within {e.one('conversionDeadlineDays')} days of termination")
    if e.one("conversionMinAmount") is not None:
        parts.append(f"min ${_num(e.one('conversionMinAmount'))}")
    if e.one("conversionMaxAmount") is not None:
        parts.append(f"max ${_num(e.one('conversionMaxAmount'))}")
    return "; ".join(parts)[:200]


def _int_or_none(v: Any) -> Optional[int]:
    try:
        return int(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _float_or_none(v: Any) -> Optional[float]:
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _dec(v: Any) -> Optional[Decimal]:
    if v is None:
        return None
    try:
        return Decimal(str(v))
    except Exception:
        return None


def _num(v: Any) -> str:
    if v is None:
        return "?"
    try:
        f = float(v)
        return f"{f:,.0f}" if f == int(f) else f"{f:,.2f}"
    except (TypeError, ValueError):
        return str(v)


def _date(v: Any) -> Optional[date]:
    if v is None:
        return None
    if isinstance(v, date):
        return v
    try:
        return date.fromisoformat(str(v)[:10])
    except ValueError:
        return None


def load_graph(path: Path = ABOX_PATH) -> Graph:
    g = Graph()
    g.parse(str(path), format="turtle")
    return g


def build_all(path: Path = ABOX_PATH) -> tuple[dict[str, PolicyRecord], dict[str, list[tuple[str, str]]]]:
    g = load_graph(path)
    out: dict[str, PolicyRecord] = {}
    unmapped: dict[str, list[tuple[str, str]]] = {}
    for s in g.subjects(LI.sourceContractID, None):
        if _local(s) not in {f"Policy_C{i}" for i in range(1, 11)}:
            continue
        b = Builder(g, s)
        rec = b.build()
        out[rec.id] = rec
        unmapped[rec.id] = b.unmapped
    return out, unmapped


def main():
    ap = argparse.ArgumentParser(description="ABox -> oracle PolicyRecord JSON (data/benchmark/oracle/C*.json)")
    ap.add_argument("--abox", default=str(ABOX_PATH))
    ap.add_argument("--out", default=str(ORACLE_DIR))
    args = ap.parse_args()
    recs, unmapped = build_all(Path(args.abox))
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for cid in sorted(recs, key=lambda c: int(c[1:])):
        rec = recs[cid]
        (out / f"{cid}.json").write_text(rec.model_dump_json(indent=1), encoding="utf8")
        rel = defaultdict(int)
        for t in rec.tuples:
            rel[t.relation.value] += 1
        print(f"{cid}: {len(rec.tuples)} tuples, {len(rec.riders)} riders, grace={rec.grace_days}, face={rec.sum_assured} | " + ", ".join(f"{k}={v}" for k, v in sorted(rel.items())))
        if unmapped[cid]:
            print("   unmapped:", ", ".join(f"{i}({c})" for i, c in unmapped[cid]))
    (out / "unmapped.json").write_text(json.dumps(unmapped, indent=1), encoding="utf8")


if __name__ == "__main__":
    main()
