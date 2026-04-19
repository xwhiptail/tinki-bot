import argparse
import json
import shutil
import urllib.request
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import boto3

from utils.infra_monitoring import build_host_metric_data, parse_meminfo_used_percent

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


def _memory_used_percent() -> float:
    with open("/proc/meminfo", "r", encoding="utf-8") as handle:
        return parse_meminfo_used_percent(handle.read())


def _disk_used_percent(path: str) -> float:
    usage = shutil.disk_usage(path)
    used_ratio = usage.used / usage.total if usage.total else 0.0
    return round(used_ratio * 100, 2)


def main():
    parser = argparse.ArgumentParser(description="Publish cheap host memory/disk metrics to CloudWatch.")
    parser.add_argument("--instance-id", help="EC2 instance ID. Auto-detected on the host when omitted.")
    parser.add_argument("--region", help="AWS region. Auto-detected on the host when omitted.")
    parser.add_argument("--namespace", default="TinkiBot/Host", help="CloudWatch namespace for custom metrics.")
    parser.add_argument("--disk-path", default="/", help="Filesystem path to monitor for disk usage.")
    parser.add_argument("--dry-run", action="store_true", help="Print metric payload without publishing it.")
    args = parser.parse_args()

    instance_id, region = _detect_instance_identity(args.instance_id, args.region)
    if not instance_id:
        raise SystemExit("Unable to determine instance ID. Pass --instance-id when running off-host.")
    if not region:
        session_region = boto3.session.Session().region_name
        region = session_region
    if not region:
        raise SystemExit("Unable to determine AWS region. Pass --region when running off-host.")

    memory_used = _memory_used_percent()
    disk_used = _disk_used_percent(args.disk_path)
    metric_data = build_host_metric_data(instance_id, memory_used, disk_used)

    print(
        f"Host metrics for {instance_id} in {region}: "
        f"memory={memory_used:.2f}% disk({args.disk_path})={disk_used:.2f}%"
    )
    if args.dry_run:
        print(json.dumps(metric_data, indent=2))
        return

    client = boto3.client("cloudwatch", region_name=region)
    client.put_metric_data(Namespace=args.namespace, MetricData=metric_data)


if __name__ == "__main__":
    main()
