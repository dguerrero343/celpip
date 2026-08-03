from datetime import date
from typing import Literal

from pydantic import BaseModel


class UsageTotals(BaseModel):
    request_count: int
    input_tokens: int
    output_tokens: int
    total_tokens: int
    estimated_cost_usd: float


class UsageDailyItem(UsageTotals):
    date: date
    provider_cost_usd: float | None = None


class UsageModelItem(UsageTotals):
    model: str


class UsageUserItem(UsageTotals):
    user_id: str
    email: str
    first_name: str


class ProviderCostComparison(BaseModel):
    status: Literal["available", "not_configured", "personal_scope", "unavailable"]
    billed_cost_usd: float | None = None
    difference_usd: float | None = None
    currency: str = "usd"
    note: str


class UsageReportResponse(BaseModel):
    period_start: date
    period_end: date
    scope: Literal["personal", "organization"]
    totals: UsageTotals
    daily: list[UsageDailyItem]
    by_model: list[UsageModelItem]
    by_user: list[UsageUserItem]
    provider: ProviderCostComparison
