from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, List


def monthly_public_ipv4_cost(hours: int = 730, hourly_rate: str = "0.005") -> str:
    monthly = (Decimal(hourly_rate) * Decimal(hours)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return format(monthly, "f")


def parse_meminfo_used_percent(meminfo_text: str) -> float:
    values: Dict[str, int] = {}
    for line in meminfo_text.splitlines():
        if ":" not in line:
            continue
        key, raw_value = line.split(":", 1)
        parts = raw_value.strip().split()
        if not parts:
            continue
        try:
            values[key] = int(parts[0])
        except ValueError:
            continue

    total = values.get("MemTotal")
    available = values.get("MemAvailable", values.get("MemFree"))
    if not total or available is None:
        raise ValueError("meminfo is missing MemTotal or MemAvailable")

    used_ratio = 1 - (available / total)
    return round(used_ratio * 100, 2)


def build_host_metric_data(instance_id: str, memory_used_percent: float, disk_used_percent: float) -> List[Dict[str, object]]:
    dimensions = [{"Name": "InstanceId", "Value": instance_id}]
    return [
        {
            "MetricName": "MemoryUsedPercent",
            "Dimensions": dimensions,
            "Unit": "Percent",
            "Value": float(memory_used_percent),
        },
        {
            "MetricName": "DiskUsedPercent",
            "Dimensions": dimensions,
            "Unit": "Percent",
            "Value": float(disk_used_percent),
        },
    ]


def build_low_cost_alarm_definitions(
    instance_id: str,
    topic_arn: str,
    *,
    namespace: str = "TinkiBot/Host",
    alarm_prefix: str = "tinki-bot",
    cpu_credit_threshold: float = 10.0,
    memory_threshold: float = 90.0,
    disk_threshold: float = 85.0,
) -> List[Dict[str, object]]:
    instance_dimension = [{"Name": "InstanceId", "Value": instance_id}]
    common_actions = [topic_arn]

    return [
        {
            "AlarmName": f"{alarm_prefix}-status-check-failed",
            "AlarmDescription": "Alerts when the EC2 system status check fails.",
            "Namespace": "AWS/EC2",
            "MetricName": "StatusCheckFailed_System",
            "Dimensions": instance_dimension,
            "Statistic": "Maximum",
            "Period": 300,
            "EvaluationPeriods": 2,
            "Threshold": 1.0,
            "ComparisonOperator": "GreaterThanOrEqualToThreshold",
            "TreatMissingData": "notBreaching",
            "AlarmActions": common_actions,
        },
        {
            "AlarmName": f"{alarm_prefix}-cpu-credit-low",
            "AlarmDescription": "Alerts when burst credits run low on the EC2 host.",
            "Namespace": "AWS/EC2",
            "MetricName": "CPUCreditBalance",
            "Dimensions": instance_dimension,
            "Statistic": "Minimum",
            "Period": 300,
            "EvaluationPeriods": 3,
            "Threshold": float(cpu_credit_threshold),
            "ComparisonOperator": "LessThanOrEqualToThreshold",
            "TreatMissingData": "notBreaching",
            "AlarmActions": common_actions,
        },
        {
            "AlarmName": f"{alarm_prefix}-memory-high",
            "AlarmDescription": "Alerts when host memory usage stays high.",
            "Namespace": namespace,
            "MetricName": "MemoryUsedPercent",
            "Dimensions": instance_dimension,
            "Statistic": "Average",
            "Period": 300,
            "EvaluationPeriods": 3,
            "Threshold": float(memory_threshold),
            "ComparisonOperator": "GreaterThanOrEqualToThreshold",
            "TreatMissingData": "notBreaching",
            "AlarmActions": common_actions,
        },
        {
            "AlarmName": f"{alarm_prefix}-disk-high",
            "AlarmDescription": "Alerts when root disk usage stays high.",
            "Namespace": namespace,
            "MetricName": "DiskUsedPercent",
            "Dimensions": instance_dimension,
            "Statistic": "Average",
            "Period": 300,
            "EvaluationPeriods": 3,
            "Threshold": float(disk_threshold),
            "ComparisonOperator": "GreaterThanOrEqualToThreshold",
            "TreatMissingData": "notBreaching",
            "AlarmActions": common_actions,
        },
    ]


def build_budget_notification_requests(
    topic_arn: str,
    *,
    actual_threshold: float = 80.0,
    forecast_threshold: float = 100.0,
) -> List[Dict[str, object]]:
    def _request(notification_type: str, threshold: float) -> Dict[str, object]:
        return {
            "Notification": {
                "NotificationType": notification_type,
                "ComparisonOperator": "GREATER_THAN",
                "Threshold": float(threshold),
                "ThresholdType": "PERCENTAGE",
            },
            "Subscribers": [
                {
                    "SubscriptionType": "SNS",
                    "Address": topic_arn,
                }
            ],
        }

    return [
        _request("ACTUAL", actual_threshold),
        _request("FORECASTED", forecast_threshold),
    ]


def summarize_cost_posture(
    *,
    instance_type: str,
    root_volume_type: str,
    root_volume_size_gib: int,
    has_public_ipv4: bool,
) -> List[str]:
    notes: List[str] = []

    if has_public_ipv4:
        notes.append(
            "A public IPv4 address is attached; expect about $"
            f"{monthly_public_ipv4_cost()}/month for that address alone."
        )

    if root_volume_type.lower() == "gp2":
        notes.append(
            f"The {root_volume_size_gib} GiB root volume is still gp2; moving it to gp3 is usually the cheapest safe win."
        )

    if instance_type.startswith(("t3", "t3a")):
        notes.append(
            "The host is still on a T3-family instance; a future T4g check could lower compute cost if the native wheels validate cleanly."
        )

    if not notes:
        notes.append("Current EC2 posture already avoids the obvious low-cost regressions covered by this helper.")

    return notes
