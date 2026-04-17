import asyncio
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from typing import Optional

from config import AWS_COST_REGION

try:
    import boto3
    from botocore.exceptions import BotoCoreError, ClientError, NoCredentialsError
except Exception:  # pragma: no cover - optional dependency
    boto3 = None

    class BotoCoreError(Exception):
        pass

    class ClientError(Exception):
        pass

    class NoCredentialsError(Exception):
        pass


@dataclass
class AWSCostSummary:
    month_to_date: str
    forecast_total: str
    currency: str
    period_label: str
    forecast_label: str

    def as_message(self) -> str:
        return (
            f"AWS cost ({self.period_label}): {self.currency}{self.month_to_date} month-to-date, "
            f"projected {self.currency}{self.forecast_total} by {self.forecast_label}."
        )


def _month_bounds(today: Optional[date] = None):
    today = today or date.today()
    start = today.replace(day=1)
    next_month = (start.replace(day=28) + timedelta(days=4)).replace(day=1)
    return start, today + timedelta(days=1), next_month


def _to_money(value: str) -> str:
    try:
        return format(Decimal(value).quantize(Decimal("0.01")), "f")
    except (InvalidOperation, TypeError, ValueError):
        return "0.00"


def _fetch_cost_summary_sync(today: Optional[date] = None) -> AWSCostSummary:
    if boto3 is None:
        raise RuntimeError("boto3 is not installed")

    period_start, period_end, forecast_end = _month_bounds(today)
    ce = boto3.client("ce", region_name=AWS_COST_REGION)

    usage = ce.get_cost_and_usage(
        TimePeriod={
            "Start": period_start.isoformat(),
            "End": period_end.isoformat(),
        },
        Granularity="MONTHLY",
        Metrics=["UnblendedCost"],
    )
    usage_amount = "0.00"
    currency = "USD"
    results = usage.get("ResultsByTime", [])
    if results:
        total = results[0].get("Total", {}).get("UnblendedCost", {})
        usage_amount = _to_money(total.get("Amount", "0.00"))
        currency = total.get("Unit", currency) or currency

    forecast = ce.get_cost_forecast(
        TimePeriod={
            "Start": period_end.isoformat(),
            "End": forecast_end.isoformat(),
        },
        Metric="UNBLENDED_COST",
        Granularity="MONTHLY",
    )
    forecast_total = forecast.get("Total", {})
    forecast_amount = _to_money(forecast_total.get("Amount", usage_amount))
    forecast_currency = forecast_total.get("Unit", currency) or currency

    return AWSCostSummary(
        month_to_date=usage_amount,
        forecast_total=forecast_amount,
        currency=forecast_currency,
        period_label=period_start.strftime("%b %Y"),
        forecast_label=(forecast_end - timedelta(days=1)).strftime("%b %d"),
    )


async def fetch_aws_cost_summary() -> str:
    try:
        loop = asyncio.get_running_loop()
        summary = await loop.run_in_executor(None, _fetch_cost_summary_sync)
    except RuntimeError as exc:
        return f"AWS cost unavailable: {exc}."
    except NoCredentialsError:
        return "AWS cost unavailable: no AWS credentials configured for Cost Explorer."
    except (BotoCoreError, ClientError) as exc:
        return f"AWS cost unavailable: {type(exc).__name__}."
    except Exception as exc:
        return f"AWS cost unavailable: {type(exc).__name__}: {exc}"
    return summary.as_message()
