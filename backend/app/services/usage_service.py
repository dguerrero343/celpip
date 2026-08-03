import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_usage import AIUsage
from app.models.enums import UserRole
from app.models.user import User


@dataclass(frozen=True)
class UsageBucket:
    request_count: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    estimated_cost: Decimal = Decimal("0")

    def add(self, usage: AIUsage) -> "UsageBucket":
        return UsageBucket(
            request_count=self.request_count + 1,
            input_tokens=self.input_tokens + usage.input_tokens,
            output_tokens=self.output_tokens + usage.output_tokens,
            estimated_cost=self.estimated_cost + usage.estimated_cost,
        )


@dataclass(frozen=True)
class UsageUserIdentity:
    user_id: uuid.UUID
    email: str
    first_name: str


@dataclass(frozen=True)
class LocalUsageReport:
    totals: UsageBucket
    daily: dict[date, UsageBucket]
    by_model: dict[str, UsageBucket]
    by_user: dict[UsageUserIdentity, UsageBucket]


async def get_local_usage_report(
    session: AsyncSession,
    *,
    current_user: User,
    start_date: date,
    end_date: date,
) -> LocalUsageReport:
    period_start = datetime.combine(start_date, time.min, tzinfo=UTC)
    period_end = datetime.combine(end_date + timedelta(days=1), time.min, tzinfo=UTC)
    statement = (
        select(AIUsage, User.id, User.email, User.first_name)
        .join(User, User.id == AIUsage.user_id)
        .where(AIUsage.created_at >= period_start, AIUsage.created_at < period_end)
        .order_by(AIUsage.created_at.asc())
    )
    if current_user.role != UserRole.ADMIN:
        statement = statement.where(AIUsage.user_id == current_user.id)

    rows = (await session.execute(statement)).all()
    totals = UsageBucket()
    daily: dict[date, UsageBucket] = defaultdict(UsageBucket)
    by_model: dict[str, UsageBucket] = defaultdict(UsageBucket)
    by_user: dict[UsageUserIdentity, UsageBucket] = defaultdict(UsageBucket)
    for usage, user_id, email, first_name in rows:
        totals = totals.add(usage)
        usage_date = usage.created_at.date()
        daily[usage_date] = daily[usage_date].add(usage)
        by_model[usage.model] = by_model[usage.model].add(usage)
        identity = UsageUserIdentity(user_id=user_id, email=email, first_name=first_name)
        by_user[identity] = by_user[identity].add(usage)
    return LocalUsageReport(
        totals=totals,
        daily=dict(daily),
        by_model=dict(by_model),
        by_user=dict(by_user),
    )
