import logging
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.ai.openai_costs import (
    OrganizationCostsProvider,
    get_organization_costs_provider,
)
from app.api.dependencies import CurrentUser, DatabaseSession
from app.models.enums import UserRole
from app.schemas.usage import (
    ProviderCostComparison,
    UsageDailyItem,
    UsageModelItem,
    UsageReportResponse,
    UsageTotals,
    UsageUserItem,
)
from app.services.usage_service import UsageBucket, get_local_usage_report

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/usage", tags=["usage"])
CostsProvider = Annotated[
    OrganizationCostsProvider | None, Depends(get_organization_costs_provider)
]


def _totals(bucket: UsageBucket) -> UsageTotals:
    return UsageTotals(
        request_count=bucket.request_count,
        input_tokens=bucket.input_tokens,
        output_tokens=bucket.output_tokens,
        total_tokens=bucket.input_tokens + bucket.output_tokens,
        estimated_cost_usd=float(bucket.estimated_cost),
    )


@router.get("/report", response_model=UsageReportResponse)
async def usage_report(
    session: DatabaseSession,
    current_user: CurrentUser,
    costs_provider: CostsProvider,
    start_date: Annotated[date | None, Query()] = None,
    end_date: Annotated[date | None, Query()] = None,
) -> UsageReportResponse:
    resolved_end = end_date or datetime.now(UTC).date()
    resolved_start = start_date or (resolved_end - timedelta(days=29))
    if resolved_start > resolved_end:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="start_date must be on or before end_date",
        )
    if (resolved_end - resolved_start).days > 179:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Usage reports are limited to 180 days",
        )

    local = await get_local_usage_report(
        session,
        current_user=current_user,
        start_date=resolved_start,
        end_date=resolved_end,
    )
    scope = "organization" if current_user.role == UserRole.ADMIN else "personal"
    provider_daily: dict[date, Decimal] = {}
    if current_user.role != UserRole.ADMIN:
        provider = ProviderCostComparison(
            status="personal_scope",
            note=(
                "OpenAI billed costs are organization-wide and are visible only to administrators."
            ),
        )
    elif costs_provider is None:
        provider = ProviderCostComparison(
            status="not_configured",
            note="Set OPENAI_ADMIN_KEY to compare local estimates with OpenAI billed costs.",
        )
    else:
        try:
            actual = await costs_provider.get_costs(
                start_date=resolved_start,
                end_date=resolved_end,
            )
            provider_daily = actual.daily_costs
            provider = ProviderCostComparison(
                status="available",
                billed_cost_usd=float(actual.total_cost),
                difference_usd=float(actual.total_cost - local.totals.estimated_cost),
                currency=actual.currency,
                note=(
                    "OpenAI Costs data is authoritative. Differences can include other requests "
                    "made by the same project or organization."
                ),
            )
        except Exception as exc:
            logger.warning("OpenAI costs report failed error_type=%s", type(exc).__name__)
            provider = ProviderCostComparison(
                status="unavailable",
                note="OpenAI billed costs could not be loaded. Local usage remains available.",
            )

    all_dates = sorted(set(local.daily) | set(provider_daily))
    daily = [
        UsageDailyItem(
            date=item_date,
            **_totals(local.daily.get(item_date, UsageBucket())).model_dump(),
            provider_cost_usd=(
                float(provider_daily[item_date]) if item_date in provider_daily else None
            ),
        )
        for item_date in all_dates
    ]
    by_model = [
        UsageModelItem(model=model, **_totals(bucket).model_dump())
        for model, bucket in sorted(local.by_model.items())
    ]
    by_user = (
        [
            UsageUserItem(
                user_id=str(identity.user_id),
                email=identity.email,
                first_name=identity.first_name,
                **_totals(bucket).model_dump(),
            )
            for identity, bucket in sorted(
                local.by_user.items(), key=lambda item: item[1].estimated_cost, reverse=True
            )
        ]
        if current_user.role == UserRole.ADMIN
        else []
    )
    return UsageReportResponse(
        period_start=resolved_start,
        period_end=resolved_end,
        scope=scope,
        totals=_totals(local.totals),
        daily=daily,
        by_model=by_model,
        by_user=by_user,
        provider=provider,
    )
