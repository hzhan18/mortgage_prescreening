"""
Canadian mortgage qualification math (GDS / TDS), kept server-side so the
client can't tamper with the numbers before they reach the broker's summary.

GDS (Gross Debt Service)  <= 39% of gross monthly income
TDS (Total Debt Service)  <= 44% of gross monthly income
Qualifying ("stress test") rate = max(contract rate + 2%, 5.25%)

These are the commonly-used default limits; some lenders use tighter ones
(e.g. 35/42) for borrowers with weaker credit. Treat these as configurable
defaults, not a hard-coded regulatory constant.
"""

from dataclasses import dataclass, field
from typing import Optional


GDS_LIMIT = 0.39
TDS_LIMIT = 0.44


@dataclass
class QualificationInput:
    annual_income: float
    down_payment: float
    other_monthly_debts: float
    property_tax_monthly: float = 0.0
    heating_monthly: float = 100.0
    condo_fees_monthly: float = 0.0
    has_condo: bool = False
    contract_rate_pct: float = 5.09
    amortization_years: int = 25


@dataclass
class QualificationResult:
    qualifies: bool
    binding_ratio: str  # "GDS" or "TDS"
    max_pi_payment: float
    max_mortgage: float
    max_purchase_price: float
    down_payment_pct: float
    actual_gds_pct: float
    actual_tds_pct: float
    qualifying_rate_pct: float
    monthly_income: float
    housing_costs_excl_pi: float


def calculate_qualification(inp: QualificationInput) -> QualificationResult:
    monthly_income = inp.annual_income / 12
    condo_component = (inp.condo_fees_monthly * 0.5) if inp.has_condo else 0.0
    housing_excl_pi = inp.property_tax_monthly + inp.heating_monthly + condo_component

    max_pi_gds = monthly_income * GDS_LIMIT - housing_excl_pi
    max_pi_tds = monthly_income * TDS_LIMIT - housing_excl_pi - inp.other_monthly_debts
    max_pi = min(max_pi_gds, max_pi_tds)
    binding_ratio = "GDS" if max_pi_gds <= max_pi_tds else "TDS"

    qualifying_rate_pct = max(inp.contract_rate_pct + 2, 5.25)
    r = qualifying_rate_pct / 100 / 12
    n = inp.amortization_years * 12

    if max_pi > 0:
        max_mortgage = max_pi * (1 - (1 + r) ** (-n)) / r
    else:
        max_mortgage = 0.0

    max_purchase_price = max_mortgage + inp.down_payment
    down_pct = (inp.down_payment / max_purchase_price * 100) if max_purchase_price > 0 else 0.0

    effective_pi = max_pi if max_pi > 0 else 0.0
    actual_gds = (effective_pi + housing_excl_pi) / monthly_income * 100
    actual_tds = (effective_pi + housing_excl_pi + inp.other_monthly_debts) / monthly_income * 100

    return QualificationResult(
        qualifies=max_pi > 0,
        binding_ratio=binding_ratio,
        max_pi_payment=max_pi,
        max_mortgage=max_mortgage,
        max_purchase_price=max_purchase_price,
        down_payment_pct=down_pct,
        actual_gds_pct=actual_gds,
        actual_tds_pct=actual_tds,
        qualifying_rate_pct=qualifying_rate_pct,
        monthly_income=monthly_income,
        housing_costs_excl_pi=housing_excl_pi,
    )
