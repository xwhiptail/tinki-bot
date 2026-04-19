import argparse
import json
import urllib.request
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import boto3
from botocore.exceptions import ClientError

from utils.infra_monitoring import (
    build_budget_notification_requests,
    build_low_cost_alarm_definitions,
    summarize_cost_posture,
)

IMDS_BASE = "http://169.254.169.254/latest"


def _fetch_imds_token():
    request = urllib.request.Request(
        f"{IMDS_BASE}/api/token",
        method="PUT",
        headers={"X-aws-ec2-metadata-token-ttl-seconds": "21600"},
    )
    try:
        with urllib.request.urlopen(request, timeout=2) as response:
            return response.read().decode("utf-8")
    except Exception:
        return None


def _fetch_metadata(path: str, token: str = None) -> str:
    request = urllib.request.Request(f"{IMDS_BASE}/{path}")
    if token:
        request.add_header("X-aws-ec2-metadata-token", token)
    with urllib.request.urlopen(request, timeout=2) as response:
        return response.read().decode("utf-8")


def _detect_instance_identity(instance_id: str = None, region: str = None):
    token = _fetch_imds_token()

    if not region:
        try:
            document = json.loads(_fetch_metadata("dynamic/instance-identity/document", token))
            region = document.get("region")
        except Exception:
            region = None

    if not instance_id:
        try:
            instance_id = _fetch_metadata("meta-data/instance-id", token).strip()
        except Exception:
            instance_id = None

    return instance_id, region


def _describe_instance(ec2, instance_id: str):
    reservations = ec2.describe_instances(InstanceIds=[instance_id]).get("Reservations", [])
    for reservation in reservations:
        for instance in reservation.get("Instances", []):
            return instance
    raise RuntimeError(f"Unable to find EC2 instance '{instance_id}'.")


def _root_volume(instance: dict):
    root_device = instance.get("RootDeviceName")
    for mapping in instance.get("BlockDeviceMappings", []):
        if mapping.get("DeviceName") == root_device:
            return mapping.get("Ebs", {}).get("VolumeId")
    return None


def _print_posture(instance: dict, volume: dict):
    volume_type = volume.get("VolumeType", "unknown")
    volume_size = volume.get("Size", 0)
    public_ipv4 = bool(instance.get("PublicIpAddress"))
    notes = summarize_cost_posture(
        instance_type=instance.get("InstanceType", "unknown"),
        root_volume_type=volume_type,
        root_volume_size_gib=volume_size,
        has_public_ipv4=public_ipv4,
    )

    print(f"Instance type: {instance.get('InstanceType', 'unknown')}")
    print(f"Public IPv4:   {'yes' if public_ipv4 else 'no'}")
    print(f"Root volume:   {volume_type} {volume_size} GiB")
    for note in notes:
        print(f"- {note}")


def _ensure_topic(sns, topic_name: str) -> str:
    return sns.create_topic(Name=topic_name)["TopicArn"]


def _subscription_exists(sns, topic_arn: str, email: str) -> bool:
    response = sns.list_subscriptions_by_topic(TopicArn=topic_arn)
    while True:
        for subscription in response.get("Subscriptions", []):
            if subscription.get("Protocol") == "email" and subscription.get("Endpoint") == email:
                return True
        token = response.get("NextToken")
        if not token:
            return False
        response = sns.list_subscriptions_by_topic(TopicArn=topic_arn, NextToken=token)


def _ensure_email_subscription(sns, topic_arn: str, email: str):
    if _subscription_exists(sns, topic_arn, email):
        print(f"SNS email subscription already exists for {email}.")
        return
    sns.subscribe(TopicArn=topic_arn, Protocol="email", Endpoint=email, ReturnSubscriptionArn=True)
    print(f"SNS subscription requested for {email}. Check that inbox and confirm it once.")


def _ensure_budget(budgets, account_id: str, budget_name: str, monthly_limit: float):
    budget = {
        "BudgetName": budget_name,
        "BudgetLimit": {"Amount": f"{monthly_limit:.2f}", "Unit": "USD"},
        "TimeUnit": "MONTHLY",
        "BudgetType": "COST",
    }

    try:
        budgets.describe_budget(AccountId=account_id, BudgetName=budget_name)
        budgets.update_budget(AccountId=account_id, NewBudget=budget)
        print(f"Updated budget '{budget_name}' to ${monthly_limit:.2f}/month.")
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        if code != "NotFoundException":
            raise
        budgets.create_budget(AccountId=account_id, Budget=budget)
        print(f"Created budget '{budget_name}' at ${monthly_limit:.2f}/month.")


def _ensure_budget_notifications(budgets, account_id: str, budget_name: str, topic_arn: str, actual_threshold: float, forecast_threshold: float):
    for request in build_budget_notification_requests(
        topic_arn,
        actual_threshold=actual_threshold,
        forecast_threshold=forecast_threshold,
    ):
        try:
            budgets.create_notification(
                AccountId=account_id,
                BudgetName=budget_name,
                Notification=request["Notification"],
                Subscribers=request["Subscribers"],
            )
            label = request["Notification"]["NotificationType"].lower()
            print(f"Created {label} budget notification at {request['Notification']['Threshold']}%.")
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "")
            if code != "DuplicateRecordException":
                raise


def _ensure_alarms(cloudwatch, instance_id: str, topic_arn: str, alarm_prefix: str, cpu_credit_threshold: float, memory_threshold: float, disk_threshold: float):
    for alarm in build_low_cost_alarm_definitions(
        instance_id,
        topic_arn,
        alarm_prefix=alarm_prefix,
        cpu_credit_threshold=cpu_credit_threshold,
        memory_threshold=memory_threshold,
        disk_threshold=disk_threshold,
    ):
        cloudwatch.put_metric_alarm(**alarm)
        print(f"Upserted alarm '{alarm['AlarmName']}'.")


def main():
    parser = argparse.ArgumentParser(description="Set up low-cost AWS alerts for the tinki-bot host.")
    parser.add_argument("--alert-email", required=True, help="Email address to subscribe to the SNS topic.")
    parser.add_argument("--instance-id", help="EC2 instance ID. Auto-detected on the host when omitted.")
    parser.add_argument("--region", help="AWS region. Auto-detected on the host when omitted.")
    parser.add_argument("--monthly-budget", type=float, default=15.0, help="Monthly AWS budget in USD.")
    parser.add_argument("--actual-threshold", type=float, default=80.0, help="Actual budget alert threshold percent.")
    parser.add_argument("--forecast-threshold", type=float, default=100.0, help="Forecasted budget alert threshold percent.")
    parser.add_argument("--cpu-credit-threshold", type=float, default=10.0, help="Low CPU credit threshold.")
    parser.add_argument("--memory-threshold", type=float, default=90.0, help="High memory usage threshold.")
    parser.add_argument("--disk-threshold", type=float, default=85.0, help="High disk usage threshold.")
    parser.add_argument("--topic-name", default="tinki-bot-alerts", help="SNS topic name for alarms and budgets.")
    parser.add_argument("--alarm-prefix", default="tinki-bot", help="CloudWatch alarm name prefix.")
    args = parser.parse_args()

    instance_id, region = _detect_instance_identity(args.instance_id, args.region)
    if not instance_id:
        raise SystemExit("Unable to determine instance ID. Pass --instance-id when running off-host.")
    if not region:
        region = boto3.session.Session().region_name
    if not region:
        raise SystemExit("Unable to determine AWS region. Pass --region when running off-host.")

    ec2 = boto3.client("ec2", region_name=region)
    sns = boto3.client("sns", region_name=region)
    cloudwatch = boto3.client("cloudwatch", region_name=region)
    sts = boto3.client("sts", region_name=region)
    budgets = boto3.client("budgets", region_name="us-east-1")

    instance = _describe_instance(ec2, instance_id)
    volume_id = _root_volume(instance)
    if not volume_id:
        raise RuntimeError(f"Unable to determine the root volume for instance '{instance_id}'.")
    volume = ec2.describe_volumes(VolumeIds=[volume_id])["Volumes"][0]

    print(f"Configuring low-cost monitoring for {instance_id} in {region}")
    _print_posture(instance, volume)

    topic_arn = _ensure_topic(sns, args.topic_name)
    print(f"SNS topic:      {topic_arn}")
    _ensure_email_subscription(sns, topic_arn, args.alert_email)

    _ensure_alarms(
        cloudwatch,
        instance_id,
        topic_arn,
        args.alarm_prefix,
        args.cpu_credit_threshold,
        args.memory_threshold,
        args.disk_threshold,
    )

    account_id = sts.get_caller_identity()["Account"]
    _ensure_budget(budgets, account_id, "tinki-bot-monthly", args.monthly_budget)
    _ensure_budget_notifications(
        budgets,
        account_id,
        "tinki-bot-monthly",
        topic_arn,
        args.actual_threshold,
        args.forecast_threshold,
    )

    print("Monitoring setup finished.")
    print("Reminder: confirm the SNS email subscription before relying on alerts.")


if __name__ == "__main__":
    main()
