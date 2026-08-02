from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal, InvalidOperation
from typing import Protocol

import httpx

from app.core.config import settings


@dataclass(frozen=True)
class OpenAICostReport:
    total_cost: Decimal
    daily_costs: dict[date, Decimal]
    currency: str


class OrganizationCostsProvider(Protocol):
    async def get_costs(self, *, start_date: date, end_date: date) -> OpenAICostReport: ...


class OpenAIOrganizationCostsClient:
    def __init__(self, *, admin_key: str, project_id: str | None = None) -> None:
        self._admin_key = admin_key
        self._project_id = project_id

    async def get_costs(self, *, start_date: date, end_date: date) -> OpenAICostReport:
        start_time = int(datetime.combine(start_date, time.min, tzinfo=UTC).timestamp())
        end_time = int(
            datetime.combine(end_date + timedelta(days=1), time.min, tzinfo=UTC).timestamp()
        )
        params: list[tuple[str, str | int]] = [
            ("start_time", start_time),
            ("end_time", end_time),
            ("bucket_width", "1d"),
            ("limit", 180),
            ("group_by", "project_id"),
            ("group_by", "line_item"),
        ]
        if self._project_id:
            params.append(("project_ids", self._project_id))

        total = Decimal("0")
        daily: dict[date, Decimal] = {}
        currency = "usd"
        page: str | None = None
        async with httpx.AsyncClient(timeout=30.0) as client:
            while True:
                request_params = list(params)
                if page:
                    request_params.append(("page", page))
                response = await client.get(
                    "https://api.openai.com/v1/organization/costs",
                    params=request_params,
                    headers={
                        "Authorization": f"Bearer {self._admin_key}",
                        "Content-Type": "application/json",
                    },
                )
                response.raise_for_status()
                payload = response.json()
                for bucket in payload.get("data", []):
                    bucket_date = datetime.fromtimestamp(bucket["start_time"], tz=UTC).date()
                    bucket_total = Decimal("0")
                    for result in bucket.get("results", []):
                        amount = result.get("amount", {})
                        try:
                            value = Decimal(str(amount.get("value", "0")))
                        except (InvalidOperation, ValueError):
                            continue
                        currency = str(amount.get("currency") or currency).lower()
                        bucket_total += value
                    daily[bucket_date] = daily.get(bucket_date, Decimal("0")) + bucket_total
                    total += bucket_total
                if not payload.get("has_more"):
                    break
                page = payload.get("next_page")
                if not page:
                    break
        return OpenAICostReport(total_cost=total, daily_costs=daily, currency=currency)


def get_organization_costs_provider() -> OrganizationCostsProvider | None:
    admin_key = (
        settings.openai_admin_key.get_secret_value().strip()
        if settings.openai_admin_key is not None
        else ""
    )
    if not admin_key:
        return None
    return OpenAIOrganizationCostsClient(
        admin_key=admin_key,
        project_id=settings.openai_project_id.strip() if settings.openai_project_id else None,
    )
