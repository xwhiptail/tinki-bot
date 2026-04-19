import importlib.util
import logging
import os
import stat
import subprocess
import sys
import sysconfig
from pathlib import Path
from typing import Optional

from utils.warning_filters import suppress_fuzzywuzzy_sequence_matcher_warning

try:
    import fcntl
except ImportError:  # pragma: no cover - non-POSIX fallback
    fcntl = None


log = logging.getLogger(__name__)

OPTIONAL_SPEEDUP_PACKAGE = "python-Levenshtein"
OPTIONAL_SPEEDUP_MODULE = "Levenshtein"
OPTIONAL_SPEEDUP_INSTALL_TIMEOUT_SECONDS = 180

_BOOTSTRAP_COMPLETED = False


def venv_root_from_executable(executable: str = sys.executable) -> Path:
    return Path(executable).absolute().parent.parent


def read_requirement_spec(requirements_path: Path, package_name: str = OPTIONAL_SPEEDUP_PACKAGE) -> Optional[str]:
    for raw_line in requirements_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        normalized = line.split(";", 1)[0].strip()
        if normalized.lower().startswith(package_name.lower()):
            return normalized
    return None


def optional_speedup_installed(module_name: str = OPTIONAL_SPEEDUP_MODULE) -> bool:
    return importlib.util.find_spec(module_name) is not None


def normalize_group_write_permissions(root: Path) -> int:
    changed = 0

    def _normalize(path: Path, *, is_dir: bool) -> None:
        nonlocal changed
        if path.is_symlink():
            return
        current_mode = path.stat().st_mode
        new_mode = current_mode | stat.S_IRGRP | stat.S_IWGRP
        if is_dir:
            new_mode |= stat.S_IXGRP | stat.S_ISGID
        elif current_mode & stat.S_IXUSR:
            new_mode |= stat.S_IXGRP
        if new_mode != current_mode:
            os.chmod(path, new_mode)
            changed += 1

    _normalize(root, is_dir=True)
    for current_root, dir_names, file_names in os.walk(root):
        current_path = Path(current_root)
        _normalize(current_path, is_dir=True)
        for dir_name in dir_names:
            _normalize(current_path / dir_name, is_dir=True)
        for file_name in file_names:
            _normalize(current_path / file_name, is_dir=False)

    return changed


def ensure_group_writable_venv(venv_root: Path, site_packages_dir: Path) -> int:
    if not venv_root.exists():
        return 0
    return normalize_group_write_permissions(venv_root)


def install_optional_speedup(
    package_spec: str,
    *,
    repo_root: Path,
    timeout: int = OPTIONAL_SPEEDUP_INSTALL_TIMEOUT_SECONDS,
) -> tuple[bool, str]:
    proc = subprocess.run(
        [sys.executable, "-m", "pip", "install", package_spec],
        cwd=str(repo_root),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=timeout,
        check=False,
    )
    combined_output = "\n".join(part.strip() for part in (proc.stdout, proc.stderr) if part.strip())
    if proc.returncode == 0:
        return True, combined_output
    detail = combined_output.splitlines()[-1] if combined_output else f"exit code {proc.returncode}"
    return False, detail


def prepare_fuzzywuzzy_runtime(
    *,
    requirements_path: Optional[Path] = None,
    venv_root: Optional[Path] = None,
    site_packages_dir: Optional[Path] = None,
    timeout: int = OPTIONAL_SPEEDUP_INSTALL_TIMEOUT_SECONDS,
) -> None:
    global _BOOTSTRAP_COMPLETED

    suppress_fuzzywuzzy_sequence_matcher_warning()
    if _BOOTSTRAP_COMPLETED:
        return

    repo_root = Path(__file__).resolve().parent.parent
    requirements_path = requirements_path or (repo_root / "requirements.txt")
    venv_root = venv_root or venv_root_from_executable()
    site_packages_dir = site_packages_dir or Path(sysconfig.get_path("purelib"))
    lock_path = venv_root / ".runtime-bootstrap.lock"

    try:
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        with open(lock_path, "a+", encoding="utf-8") as lock_file:
            if fcntl is not None:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)

            changed = ensure_group_writable_venv(venv_root, site_packages_dir)
            if changed:
                log.info("runtime bootstrap: normalized group-write permissions on %s paths under %s", changed, venv_root)

            if optional_speedup_installed():
                _BOOTSTRAP_COMPLETED = True
                return

            package_spec = read_requirement_spec(requirements_path) or OPTIONAL_SPEEDUP_PACKAGE
            ok, detail = install_optional_speedup(package_spec, repo_root=repo_root, timeout=timeout)
            if ok:
                normalize_group_write_permissions(venv_root)
                log.info("runtime bootstrap: installed optional fuzzywuzzy speedup package %s", package_spec)
            else:
                log.warning("runtime bootstrap: failed to install %s: %s", package_spec, detail)
    except Exception as exc:
        log.warning("runtime bootstrap: unable to prepare fuzzywuzzy runtime: %s: %s", type(exc).__name__, exc)
    finally:
        _BOOTSTRAP_COMPLETED = True
