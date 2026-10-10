"""Deploy only OpenAI configuration, its adapter, and standalone model tests via SSM."""
import argparse
import ast
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time


MODEL_FILES = ("config.py", "utils/openai_helpers.py", "tests/test_openai_models.py")
MODEL_KEYS = ("OPENAI_MODEL", "OPENAI_FAST_MODEL")


def replace_model_settings(contents, models):
    """Preserve every other environment setting and comment, without logging secrets."""
    lines = []
    seen = set()
    for line in contents.splitlines(keepends=True):
        match = re.match(r"^(?:export\s+)?(OPENAI_MODEL|OPENAI_FAST_MODEL)\s*=", line)
        if match:
            key = match.group(1)
            if key not in seen:
                lines.append(f"{key}={models[key]}\n")
                seen.add(key)
        else:
            lines.append(line)
    if lines and not lines[-1].endswith("\n"):
        lines[-1] += "\n"
    lines.extend(f"{key}={models[key]}\n" for key in MODEL_KEYS if key not in seen)
    return "".join(lines)


def atomic_write(path, content, metadata):
    fd, temporary = tempfile.mkstemp(prefix=".model-update-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, metadata.st_mode & 0o777)
        os.chown(temporary, metadata.st_uid, metadata.st_gid)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def apply_payload(payload):
    repo = Path(payload["repo"])
    env_file = Path(payload["env_file"])
    assert set(payload["files"]) == set(MODEL_FILES), "Unexpected deployment files"
    for name, expected in payload["expected_hashes"].items():
        actual = hashlib.sha256((repo / name).read_bytes()).hexdigest()
        assert actual == expected, f"Live {name} differs from the expected committed version"
    # The entrypoint, every feature module, and the full-deploy marker stay intact.
    protected = [repo / "tinki-bot.py", repo / ".deploy-commit", *sorted((repo / "cogs").glob("*.py"))]
    protected_before = {path: path.read_bytes() for path in protected}
    targets = [repo / name for name in MODEL_FILES] + [env_file, repo / ".deploy-model-commit"]
    originals = {path: (path.read_bytes(), path.stat()) if path.exists() else None for path in targets}
    backup_root = repo.parent / "backup"
    backup_root.mkdir(exist_ok=True)
    backup = Path(tempfile.mkdtemp(prefix="openai_models_", dir=backup_root))
    backup.chmod(0o700)
    for path, original in originals.items():
        if original is not None:
            name = "tinki-bot.env" if path == env_file else str(path.relative_to(repo))
            destination = backup / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, destination)
    shutil.copy2(repo / "tinki-bot.py", backup / "tinki-bot.py")
    (backup / "added-files.json").write_text(json.dumps([
        str(path.relative_to(repo)) for path, original in originals.items()
        if original is None and path != env_file
    ]))
    print(f"Rollback snapshot: {backup}", flush=True)
    restarted = False
    try:
        fallback_metadata = (repo / "config.py").stat()
        for name, encoded in payload["files"].items():
            path = repo / name
            metadata = originals[path][1] if originals[path] else fallback_metadata
            atomic_write(path, base64.b64decode(encoded), metadata)
        with tempfile.TemporaryDirectory(prefix="tinki-model-tests-") as test_data:
            test_env = dict(os.environ, TINKI_DATA_DIR=test_data,
                            MPLBACKEND="Agg", PYTHONDONTWRITEBYTECODE="1")
            result = subprocess.run(
                [str(repo.parent / "myenv/bin/python"), "-m", "pytest", "-q"],
                cwd=repo, env=test_env, capture_output=True, text=True, timeout=90,
            )
            print(result.stdout[-4000:], flush=True)
            if result.returncode:
                raise RuntimeError("Production pytest failed; restoring the previous files")
        atomic_write(env_file, replace_model_settings(
            originals[env_file][0].decode("utf-8"), payload["models"],
        ).encode("utf-8"), originals[env_file][1])
        marker = repo / ".deploy-model-commit"
        atomic_write(marker, (payload["commit"] + "\n").encode(), fallback_metadata)
        assert all(path.read_bytes() == data for path, data in protected_before.items())
        restarted = True
        subprocess.run(["systemctl", "restart", "tinki-bot"], check=True, timeout=30)
        pid = subprocess.check_output([
            "systemctl", "show", "tinki-bot.service", "--property=MainPID", "--value",
        ], text=True).strip()
        running_env = dict(item.split("=", 1) for item in
                           Path(f"/proc/{pid}/environ").read_text().split("\0") if "=" in item)
        assert all(running_env.get(key) == value for key, value in payload["models"].items())
        print("Model settings verified in the running service; feature files unchanged.", flush=True)
        for old in sorted(backup_root.glob("openai_models_*"), key=lambda p: p.stat().st_mtime, reverse=True)[3:]:
            shutil.rmtree(old)
    except BaseException:
        for path, original in originals.items():
            if original is None:
                path.unlink(missing_ok=True)
            else:
                atomic_write(path, original[0], original[1])
        if restarted:
            subprocess.run(["systemctl", "restart", "tinki-bot"], check=True, timeout=30)
        raise


def build_payload(root, commit, base, repo):
    def read_at(ref, name):
        return subprocess.check_output(["git", "show", f"{ref}:{name}"], cwd=root)

    files = {name: read_at(commit, name) for name in MODEL_FILES}
    models = {}
    for node in ast.parse(files["config.py"]).body:
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
            key = node.targets[0].id
            if key in MODEL_KEYS:
                models[key] = ast.literal_eval(node.value.args[1])
    assert set(models) == set(MODEL_KEYS)
    return dict(
        repo=repo, env_file="/etc/tinki-bot.env", commit=commit, models=models,
        files={name: base64.b64encode(data).decode() for name, data in files.items()},
        expected_hashes={name: hashlib.sha256(read_at(base, name)).hexdigest() for name in MODEL_FILES[:2]},
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--base", required=True)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--instance-id", required=True)
    parser.add_argument("--region", default="us-east-1")
    args = parser.parse_args()
    root = Path(__file__).resolve().parent.parent
    payload = build_payload(root, args.commit, args.base, args.repo)
    source = Path(__file__).read_text().rsplit('\nif __name__ == "__main__":', 1)[0]
    command = "python3 - <<'TINKI_MODELS'\n" + source + "\napply_payload(" + repr(payload) + ")\nTINKI_MODELS"
    with tempfile.TemporaryDirectory(prefix="tinki-model-deploy-") as temp_dir:
        parameters = Path(temp_dir) / "parameters.json"
        parameters.write_text(json.dumps({"commands": [command]}))
        command_id = subprocess.check_output([
            "aws", "ssm", "send-command", "--region", args.region,
            "--instance-ids", args.instance_id, "--document-name", "AWS-RunShellScript",
            "--parameters", f"file://{parameters}", "--query", "Command.CommandId", "--output", "text",
        ], text=True).strip()
        print(f"SSM model deployment: {command_id}", flush=True)
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            result = subprocess.run([
                "aws", "ssm", "get-command-invocation", "--region", args.region,
                "--command-id", command_id, "--instance-id", args.instance_id, "--output", "json",
            ], capture_output=True, text=True)
            if result.returncode == 0:
                invocation = json.loads(result.stdout)
                if invocation["Status"] not in ("Pending", "InProgress", "Delayed"):
                    print(invocation.get("StandardOutputContent", ""))
                    if invocation["Status"] != "Success":
                        raise RuntimeError("Model deployment failed; inspect SSM invocation " + command_id)
                    return
            time.sleep(2)
        raise TimeoutError("Deployment outcome unverified; inspect SSM invocation " + command_id)


if __name__ == "__main__":
    main()
