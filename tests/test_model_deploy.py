import base64
import hashlib
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest


SPEC = importlib.util.spec_from_file_location(
    "model_deploy", Path(__file__).resolve().parents[1] / "scripts/deploy_openai_models.py",
)
deploy = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(deploy)


def test_model_settings_preserve_secrets_comments_and_remove_duplicate_overrides():
    original = "# keep comment\nDISCORD=secret-value\nOPENAI_MODEL=old\nexport OPENAI_MODEL=duplicate\nGIPHY=other-value"
    result = deploy.replace_model_settings(original, {
        "OPENAI_MODEL": "gpt-6.1-sol", "OPENAI_FAST_MODEL": "gpt-6-luna",
    })
    assert result == (
        "# keep comment\nDISCORD=secret-value\nOPENAI_MODEL=gpt-6.1-sol\n"
        "GIPHY=other-value\nOPENAI_FAST_MODEL=gpt-6-luna\n"
    )


@pytest.fixture
def deployment(tmp_path):
    repo = tmp_path / "repo"
    for directory in (repo, repo / "utils", repo / "tests", repo / "cogs", tmp_path / "data"):
        directory.mkdir()
    for name in ("config.py", "utils/openai_helpers.py", "tinki-bot.py", "cogs/ai.py", ".deploy-commit"):
        (repo / name).write_text("original " + name)
    env_file = tmp_path / "tinki-bot.env"
    env_file.write_text("DISCORD=preserve-me\nOPENAI_MODEL=old\n")
    env_file.chmod(0o640)
    data = tmp_path / "data/state.json"
    data.write_text("preserve runtime data")
    payload = dict(
        repo=str(repo), env_file=str(env_file), commit="model-commit",
        models={"OPENAI_MODEL": "gpt-6.1-sol", "OPENAI_FAST_MODEL": "gpt-6-luna"},
        files={name: base64.b64encode(b"new model code").decode() for name in deploy.MODEL_FILES},
        expected_hashes={name: hashlib.sha256((repo / name).read_bytes()).hexdigest()
                         for name in deploy.MODEL_FILES[:2]},
    )
    return repo, env_file, data, payload


def test_failed_production_tests_restore_code_env_and_remove_added_files(deployment, monkeypatch):
    repo, env_file, data, payload = deployment
    before = {path: path.read_bytes() for path in repo.rglob("*") if path.is_file()}
    env_before = env_file.read_bytes()
    monkeypatch.setattr(deploy.subprocess, "run", lambda *a, **k: SimpleNamespace(stdout="test failure", returncode=1))
    with pytest.raises(RuntimeError, match="Production pytest failed"):
        deploy.apply_payload(payload)
    assert {path: path.read_bytes() for path in repo.rglob("*") if path.is_file()} == before
    assert env_file.read_bytes() == env_before
    assert env_file.stat().st_mode & 0o777 == 0o640
    assert data.read_text() == "preserve runtime data"
    backup = next((repo.parent / "backup").glob("openai_models_*"))
    assert backup.stat().st_mode & 0o777 == 0o700
    assert (backup / "tinki-bot.env").read_bytes() == env_before


def test_success_changes_only_model_files_and_separate_marker(deployment, monkeypatch):
    repo, env_file, data, payload = deployment
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        if "pytest" in command:
            assert kwargs["env"]["TINKI_DATA_DIR"] != str(data.parent)
        return SimpleNamespace(stdout="6 passed", returncode=0)

    monkeypatch.setattr(deploy.subprocess, "run", run)
    monkeypatch.setattr(deploy.subprocess, "check_output", lambda *a, **k: "999\n")
    read_text = Path.read_text
    monkeypatch.setattr(Path, "read_text", lambda path, *a, **k:
                        "OPENAI_MODEL=gpt-6.1-sol\0OPENAI_FAST_MODEL=gpt-6-luna\0"
                        if str(path) == "/proc/999/environ" else read_text(path, *a, **k))
    deploy.apply_payload(payload)
    assert (repo / ".deploy-commit").read_text() == "original .deploy-commit"
    assert (repo / ".deploy-model-commit").read_text() == "model-commit\n"
    assert (repo / "cogs/ai.py").read_text() == "original cogs/ai.py"
    assert (repo / "tinki-bot.py").read_text() == "original tinki-bot.py"
    assert "DISCORD=preserve-me\n" in env_file.read_text()
    assert env_file.stat().st_mode & 0o777 == 0o640
    assert data.read_text() == "preserve runtime data"
    assert calls[-1] == ["systemctl", "restart", "tinki-bot"]


def test_live_code_drift_stops_before_any_write(deployment):
    repo, env_file, _, payload = deployment
    (repo / "config.py").write_text("unexpected live edit")
    with pytest.raises(AssertionError, match="differs from the expected"):
        deploy.apply_payload(payload)
    assert (repo / "config.py").read_text() == "unexpected live edit"
    assert "OPENAI_MODEL=old" in env_file.read_text()
    assert not (repo.parent / "backup").exists()


def test_unverified_running_settings_restore_old_files_and_restart(deployment, monkeypatch):
    repo, env_file, _, payload = deployment
    before = (repo / "config.py").read_bytes(), env_file.read_bytes()
    restarts = []

    def run(command, **kwargs):
        if command[0] == "systemctl":
            restarts.append(command)
        return SimpleNamespace(stdout="6 passed", returncode=0)

    monkeypatch.setattr(deploy.subprocess, "run", run)
    monkeypatch.setattr(deploy.subprocess, "check_output", lambda *a, **k: "999\n")
    read_text = Path.read_text
    monkeypatch.setattr(Path, "read_text", lambda path, *a, **k:
                        "OPENAI_MODEL=old\0" if str(path) == "/proc/999/environ"
                        else read_text(path, *a, **k))
    with pytest.raises(AssertionError):
        deploy.apply_payload(payload)
    assert ((repo / "config.py").read_bytes(), env_file.read_bytes()) == before
    assert not (repo / ".deploy-model-commit").exists()
    assert len(restarts) == 2
