import asyncio
import io
import logging
import os
import platform
import signal
import shutil
import sys
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import aiohttp
import discord
from discord.ext import commands

from config import CHANNEL_BOT_TEST, GITHUB_REPO_URL, USER_WHIPTAIL_ID, user_matches
from utils.aws_costs import fetch_aws_cost_summary
from utils.infra_monitoring import parse_meminfo_used_percent
from utils.openai_helpers import fetch_openai_balance
from utils.selftests import (
    run_bot_insight_selftests,
    run_calculate_selftests,
    run_letter_count_selftests,
    run_url_selftests,
)

log = logging.getLogger("discord.cogs.admin")

TEST_PASS_EMOJI = "\u2705"
TEST_FAIL_EMOJI = "\U0001f6a8"
DIAGNOSTICS_BUSY_MESSAGE = "Diagnostics already running. Try again in a minute."
DIAGNOSTIC_STEP_TIMEOUT_SECONDS = 10
PYTEST_TIMEOUT_SECONDS = 35


@dataclass(frozen=True)
class StartupCheckSection:
    summary_label: str
    report_label: str
    suffix: str
    description: str
    results: list


class Admin(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._diagnostics_lock = asyncio.Lock()
        self._started_at = datetime.now()

    def _request_service_restart(self) -> None:
        # Let systemd restart the bot without requiring sudo from the service user.
        os.kill(os.getpid(), signal.SIGTERM)

    async def _run_async_diagnostic_check(self, name: str, awaitable, timeout: int = DIAGNOSTIC_STEP_TIMEOUT_SECONDS):
        try:
            return await asyncio.wait_for(awaitable, timeout=timeout)
        except asyncio.TimeoutError:
            return [(name, False, f"timed out after {timeout}s")]
        except Exception as e:
            return [(name, False, f"{type(e).__name__}: {e}")]

    async def _run_sync_diagnostic_check(self, name: str, func, timeout: int = DIAGNOSTIC_STEP_TIMEOUT_SECONDS):
        try:
            return await asyncio.wait_for(asyncio.to_thread(func), timeout=timeout)
        except asyncio.TimeoutError:
            return [(name, False, f"timed out after {timeout}s")]
        except Exception as e:
            return [(name, False, f"{type(e).__name__}: {e}")]

    async def _run_status_check_with_timeout(self, label: str, awaitable, timeout: int = DIAGNOSTIC_STEP_TIMEOUT_SECONDS):
        try:
            return await asyncio.wait_for(awaitable, timeout=timeout)
        except asyncio.TimeoutError:
            return f"{label} check timed out after {timeout}s."
        except Exception as e:
            return f"{label} check failed: {type(e).__name__}: {e}"

    def _copy_deploy_file(self, source: Path, target: Path) -> None:
        shutil.copyfile(source, target)

    def _copy_deploy_dir(self, source: Path, target: Path) -> None:
        shutil.copytree(source, target, dirs_exist_ok=True, copy_function=shutil.copyfile)

    def _host_admin_allowed(self, author) -> bool:
        return user_matches(author, USER_WHIPTAIL_ID, 'whiptail')

    def _format_check_result(self, name: str, ok: bool, reason: str = None) -> str:
        emoji = TEST_PASS_EMOJI if ok else TEST_FAIL_EMOJI
        if reason:
            return f"{emoji} {name} - {reason}"
        return f"{emoji} {name}"

    def _format_duration(self, total_seconds) -> str:
        if total_seconds is None:
            return "unavailable"
        remaining = max(int(total_seconds), 0)
        days, remaining = divmod(remaining, 86400)
        hours, remaining = divmod(remaining, 3600)
        minutes, seconds = divmod(remaining, 60)
        parts = []
        if days:
            parts.append(f"{days}d")
        if hours:
            parts.append(f"{hours}h")
        if minutes and len(parts) < 2:
            parts.append(f"{minutes}m")
        if not parts:
            parts.append(f"{seconds}s")
        return " ".join(parts[:2])

    def _read_meminfo_snapshot(self):
        meminfo_path = Path("/proc/meminfo")
        if not meminfo_path.exists():
            return {
                "memory_used_percent": None,
                "swap_used_percent": None,
                "swap_used_mib": None,
                "swap_total_mib": None,
            }

        values = {}
        meminfo_text = meminfo_path.read_text(encoding="utf-8")
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

        swap_total = values.get("SwapTotal")
        swap_free = values.get("SwapFree")
        if swap_total is None or swap_free is None or swap_total <= 0:
            swap_used_percent = 0.0 if swap_total == 0 else None
            swap_used_mib = 0.0 if swap_total == 0 else None
            swap_total_mib = round(swap_total / 1024, 1) if swap_total is not None else None
        else:
            swap_used_kib = max(swap_total - swap_free, 0)
            swap_used_percent = round((swap_used_kib / swap_total) * 100, 1)
            swap_used_mib = round(swap_used_kib / 1024, 1)
            swap_total_mib = round(swap_total / 1024, 1)

        try:
            memory_used_percent = round(parse_meminfo_used_percent(meminfo_text), 1)
        except Exception:
            memory_used_percent = None

        return {
            "memory_used_percent": memory_used_percent,
            "swap_used_percent": swap_used_percent,
            "swap_used_mib": swap_used_mib,
            "swap_total_mib": swap_total_mib,
        }

    def _read_host_uptime_seconds(self):
        uptime_path = Path("/proc/uptime")
        if not uptime_path.exists():
            return None
        try:
            first_field = uptime_path.read_text(encoding="utf-8").split()[0]
            return float(first_field)
        except (IndexError, ValueError, OSError):
            return None

    async def _fetch_imds_token(self, session):
        async with session.put(
            "http://169.254.169.254/latest/api/token",
            headers={"X-aws-ec2-metadata-token-ttl-seconds": "60"},
            timeout=aiohttp.ClientTimeout(total=1),
        ) as resp:
            resp.raise_for_status()
            return await resp.text()

    async def _fetch_imds_value(self, session, token: str, path: str):
        async with session.get(
            f"http://169.254.169.254/latest/meta-data/{path}",
            headers={"X-aws-ec2-metadata-token": token},
            timeout=aiohttp.ClientTimeout(total=1),
        ) as resp:
            resp.raise_for_status()
            return await resp.text()

    async def _fetch_ec2_metadata(self):
        try:
            async with aiohttp.ClientSession() as session:
                token = await self._fetch_imds_token(session)
                instance_id, instance_type, availability_zone, local_ipv4, public_ipv4 = await asyncio.gather(
                    self._fetch_imds_value(session, token, "instance-id"),
                    self._fetch_imds_value(session, token, "instance-type"),
                    self._fetch_imds_value(session, token, "placement/availability-zone"),
                    self._fetch_imds_value(session, token, "local-ipv4"),
                    self._fetch_imds_value(session, token, "public-ipv4"),
                    return_exceptions=True,
                )
        except Exception:
            return {}

        def _value_or_none(value):
            return None if isinstance(value, Exception) else value

        return {
            "instance_id": _value_or_none(instance_id),
            "instance_type": _value_or_none(instance_type),
            "availability_zone": _value_or_none(availability_zone),
            "local_ipv4": _value_or_none(local_ipv4),
            "public_ipv4": _value_or_none(public_ipv4),
        }

    async def _collect_status_snapshot(self):
        repo_root = Path(__file__).resolve().parent.parent
        app_root = repo_root.parent
        snapshot = {
            "hostname": platform.node() or os.uname().nodename,
            "deploy_commit": self._read_deployed_commit(repo_root),
            "python_version": platform.python_version(),
            "python_executable": sys.executable,
            "diagnostics_busy": self._diagnostics_lock.locked(),
            "pytest_timeout_seconds": PYTEST_TIMEOUT_SECONDS,
            "disk_path": str(app_root),
            "app_uptime": self._format_duration((datetime.now() - self._started_at).total_seconds()),
            "host_uptime": self._format_duration(self._read_host_uptime_seconds()),
        }

        try:
            load_average = os.getloadavg()
        except (AttributeError, OSError):
            load_average = None
        snapshot["load_average"] = load_average

        try:
            total, used, _ = shutil.disk_usage(app_root)
            snapshot["disk_used_percent"] = round((used / total) * 100, 1) if total else None
        except OSError:
            snapshot["disk_used_percent"] = None

        snapshot.update(self._read_meminfo_snapshot())
        snapshot.update(await self._fetch_ec2_metadata())
        return snapshot

    def _build_status_report(self, snapshot, aws_cost_summary: str):
        diagnostics_state = "busy" if snapshot.get("diagnostics_busy") else "idle"
        deploy_commit = self._short_commit(snapshot.get("deploy_commit", ""))
        load_average = snapshot.get("load_average")
        if load_average:
            load_text = f"`{load_average[0]:.2f} {load_average[1]:.2f} {load_average[2]:.2f}`"
        else:
            load_text = "`unavailable`"

        memory_used_percent = snapshot.get("memory_used_percent")
        if memory_used_percent is None:
            memory_text = "Memory: `unavailable`"
        else:
            memory_text = f"Memory: `{memory_used_percent:.1f}%` used"
            swap_used_percent = snapshot.get("swap_used_percent")
            swap_used_mib = snapshot.get("swap_used_mib")
            swap_total_mib = snapshot.get("swap_total_mib")
            if swap_used_percent is not None and swap_used_mib is not None and swap_total_mib is not None:
                memory_text += (
                    f", swap `{swap_used_percent:.1f}%` "
                    f"(`{swap_used_mib:.0f}/{swap_total_mib:.0f} MiB`)"
                )

        disk_used_percent = snapshot.get("disk_used_percent")
        if disk_used_percent is None:
            disk_text = "Disk: `unavailable`"
        else:
            disk_text = f"Disk: `{disk_used_percent:.1f}%` used on `{snapshot.get('disk_path', 'unknown')}`"

        if snapshot.get("instance_id") and snapshot.get("instance_type") and snapshot.get("availability_zone"):
            ec2_text = (
                f"EC2: `{snapshot['instance_id']}` "
                f"(`{snapshot['instance_type']}`, `{snapshot['availability_zone']}`)"
            )
        else:
            ec2_text = "EC2: metadata unavailable"

        summary_lines = [
            f"Status report for `{snapshot.get('hostname', 'unknown')}`",
            ec2_text,
            (
                f"Deploy: `{deploy_commit}`, Python `{snapshot.get('python_version', 'unknown')}`, "
                f"diagnostics `{diagnostics_state}`, "
                f"pytest timeout `{snapshot.get('pytest_timeout_seconds', PYTEST_TIMEOUT_SECONDS)}s`"
            ),
            f"Load: {load_text}",
            memory_text,
            disk_text,
            f"Uptime: app `{snapshot.get('app_uptime', 'unavailable')}`, host `{snapshot.get('host_uptime', 'unavailable')}`",
            aws_cost_summary,
        ]

        detail_lines = [
            f"Status Report - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "=" * 60,
            f"Hostname: {snapshot.get('hostname', 'unknown')}",
            f"Deploy commit: {snapshot.get('deploy_commit') or 'unknown'}",
            f"Python version: {snapshot.get('python_version', 'unknown')}",
            f"Python executable: {snapshot.get('python_executable', 'unknown')}",
            f"Diagnostics lock: {diagnostics_state}",
            f"Pytest timeout: {snapshot.get('pytest_timeout_seconds', PYTEST_TIMEOUT_SECONDS)}s",
            f"Load average: {load_average[0]:.2f} {load_average[1]:.2f} {load_average[2]:.2f}" if load_average else "Load average: unavailable",
            f"Memory used: {memory_used_percent:.1f}%" if memory_used_percent is not None else "Memory used: unavailable",
            (
                f"Swap used: {snapshot['swap_used_percent']:.1f}% "
                f"({snapshot['swap_used_mib']:.0f}/{snapshot['swap_total_mib']:.0f} MiB)"
            )
            if snapshot.get("swap_used_percent") is not None and snapshot.get("swap_used_mib") is not None and snapshot.get("swap_total_mib") is not None
            else "Swap used: unavailable",
            (
                f"Disk used: {disk_used_percent:.1f}% on {snapshot.get('disk_path', 'unknown')}"
                if disk_used_percent is not None
                else "Disk used: unavailable"
            ),
            f"App uptime: {snapshot.get('app_uptime', 'unavailable')}",
            f"Host uptime: {snapshot.get('host_uptime', 'unavailable')}",
            f"Instance ID: {snapshot.get('instance_id') or 'unavailable'}",
            f"Instance type: {snapshot.get('instance_type') or 'unavailable'}",
            f"Availability zone: {snapshot.get('availability_zone') or 'unavailable'}",
            f"Local IPv4: {snapshot.get('local_ipv4') or 'unavailable'}",
            f"Public IPv4: {snapshot.get('public_ipv4') or 'unavailable'}",
            f"AWS cost: {aws_cost_summary}",
        ]

        return "\n".join(summary_lines), "\n".join(detail_lines) + "\n"

    def _status_emoji(self, passed: int, total: int) -> str:
        return TEST_PASS_EMOJI if total and passed == total else TEST_FAIL_EMOJI

    def _summary_line(self, label: str, passed: int, total: int, suffix: str = "tests passed") -> str:
        return f"{self._status_emoji(passed, total)} {label}: {passed}/{total} {suffix}\n"

    def _startup_check_sections(
        self,
        cmd_results,
        url_results,
        calc_results,
        letter_results,
        insight_results,
        pytest_results,
    ):
        return [
            StartupCheckSection(
                summary_label="Command availability",
                report_label="Command Availability",
                suffix="commands available",
                description="commands loaded only; startup does not execute them",
                results=cmd_results,
            ),
            StartupCheckSection(
                summary_label="URL filter matrix",
                report_label="URL Tests",
                suffix="tests passed",
                description="URL rewrite self-tests",
                results=url_results,
            ),
            StartupCheckSection(
                summary_label="Calculator gnome",
                report_label="Calculator Tests",
                suffix="tests passed",
                description="Calculator handler self-tests",
                results=calc_results,
            ),
            StartupCheckSection(
                summary_label="Letter gnome",
                report_label="Letter Count Tests",
                suffix="tests passed",
                description="Letter counter self-tests",
                results=letter_results,
            ),
            StartupCheckSection(
                summary_label="Bot insight gnome",
                report_label="Bot Insight Tests",
                suffix="tests passed",
                description="Bot insight self-tests",
                results=insight_results,
            ),
            StartupCheckSection(
                summary_label="Pytest suite",
                report_label="Pytest",
                suffix="passed",
                description="Local pytest suite",
                results=pytest_results,
            ),
        ]

    async def run_startup_tests(self):
        if self._diagnostics_lock.locked():
            log.warning("[startup tests] skipped; diagnostics already running")
            return
        log.warning("[startup tests] task started")
        async with self._diagnostics_lock:
            try:
                await self._run_startup_tests_inner()
            except Exception as e:
                log.error("[startup tests] unhandled exception: %s: %s", type(e).__name__, e)

    async def _run_startup_tests_inner(self):
        await self.bot.wait_until_ready()
        all_channels = list(self.bot.get_all_channels())
        log.info("[startup tests] bot sees %d channels: %s", len(all_channels), [c.name for c in all_channels])
        test_channel = discord.utils.get(all_channels, name=CHANNEL_BOT_TEST)
        if not test_channel:
            log.warning("[startup tests] No #%s channel found; skipping.", CHANNEL_BOT_TEST)
            return
        log.info("[startup tests] found #%s, running tests...", CHANNEL_BOT_TEST)

        cmd_results = await self._run_async_diagnostic_check("command availability", self._run_command_selftests(ctx=None))
        url_results = await self._run_sync_diagnostic_check("url selftests", run_url_selftests)
        calc_results = await self._run_sync_diagnostic_check("calculator selftests", run_calculate_selftests)
        letter_results = await self._run_sync_diagnostic_check("letter selftests", run_letter_count_selftests)
        insight_results = await self._run_sync_diagnostic_check("bot insight selftests", run_bot_insight_selftests)
        pytest_results = await self._run_pytest_suite()
        openai_balance = await self._run_status_check_with_timeout("OpenAI", fetch_openai_balance())
        aws_cost_summary = await self._run_status_check_with_timeout("AWS cost", fetch_aws_cost_summary())

        def _counts(results):
            return sum(1 for _, ok, _ in results if ok), len(results)

        sections = self._startup_check_sections(
            cmd_results,
            url_results,
            calc_results,
            letter_results,
            insight_results,
            pytest_results,
        )

        all_results = cmd_results + url_results + calc_results + letter_results + insight_results + pytest_results
        failures = [f"{name}: {reason}" for name, ok, reason in all_results if not ok]

        summary_lines = [
            "Bot restarted - running startup diagnostics...",
            "```ini\n[BOOT SEQUENCE COMPLETED]\n```",
            "Startup checks:",
        ]
        for section in sections:
            passed, total = _counts(section.results)
            summary_lines.append(self._summary_line(section.summary_label, passed, total, section.suffix).rstrip())
        summary_lines.append(f"{TEST_PASS_EMOJI} OpenAI: {openai_balance}")
        summary_lines.append(f"{TEST_PASS_EMOJI} AWS cost: {aws_cost_summary}")
        summary = "\n".join(summary_lines) + "\n"
        if failures:
            summary += "\n" + "".join(f"{TEST_FAIL_EMOJI} {failure}\n" for failure in failures)
        else:
            summary += "\nAll systems fully operational."

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        lines = [f"Startup Diagnostic Results - {timestamp}\n", "=" * 60 + "\n"]
        for section in sections:
            passed, total = _counts(section.results)
            lines.append(f"\n{self._summary_line(section.report_label, passed, total, section.suffix)}")
            lines.append(f"  Checks: {section.description}\n")
            for name, ok, reason in section.results:
                lines.append(f"  {self._format_check_result(name, ok, reason)}\n")
        lines.append(f"\nOpenAI: {openai_balance}\n")
        lines.append(f"AWS cost: {aws_cost_summary}\n")

        buf = io.BytesIO("".join(lines).encode("utf-8"))
        try:
            await test_channel.send(content=summary, file=discord.File(buf, filename="startup_test_results.txt"))
            log.info("[startup tests] posted startup diagnostics to #%s", CHANNEL_BOT_TEST)
        except discord.Forbidden:
            await test_channel.send(content=summary)
            log.info("[startup tests] posted startup diagnostics without attachment to #%s", CHANNEL_BOT_TEST)
        except discord.HTTPException as e:
            log.error("[startup tests] failed to post startup diagnostics: %s: %s", type(e).__name__, e)

    async def _run_pytest_suite(self):
        repo_root = Path(__file__).resolve().parent.parent
        try:
            proc = await asyncio.create_subprocess_exec(
                sys.executable,
                "-m",
                "pytest",
                "-q",
                cwd=str(repo_root),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except Exception as e:
            return [("pytest", False, f"unable to start: {type(e).__name__}: {e}")]

        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=PYTEST_TIMEOUT_SECONDS)
        except asyncio.TimeoutError:
            proc.kill()
            try:
                await proc.communicate()
            except Exception:
                pass
            return [("pytest", False, f"timed out after {PYTEST_TIMEOUT_SECONDS}s")]
        output = "\n".join(
            part.strip()
            for part in (
                stdout.decode("utf-8", errors="replace"),
                stderr.decode("utf-8", errors="replace"),
            )
            if part.strip()
        )

        if proc.returncode == 0:
            summary = output.splitlines()[-1] if output else "passed"
            return [("pytest", True, summary)]

        failure = output.splitlines()[-1] if output else f"exit code {proc.returncode}"
        return [("pytest", False, failure)]

    async def _run_command_selftests(self, ctx=None):
        tests = [
            "pb", "avg", "median", "all", "bowlinggraph", "bowlingdistgraph",
            "gif", "random", "github", "allemotes", "roulette", "cat", "dog", "dogbark",
            "remindme",
            "sussy", "sussygraph", "explode", "explodegraph", "grindcount", "grindgraph",
        ]
        results = []
        for name in tests:
            cmd = self.bot.get_command(name)
            if cmd is None:
                results.append((name, False, "command not found"))
                if ctx:
                    await ctx.send(f"{TEST_FAIL_EMOJI} {name}: command not found")
                continue
            try:
                if ctx:
                    await ctx.invoke(cmd)
                    await ctx.send(f"{TEST_PASS_EMOJI} {name}: passed")
                results.append((name, True, None))
            except Exception as e:
                results.append((name, False, f"{type(e).__name__}: {e}"))
                if ctx:
                    await ctx.send(f"{TEST_FAIL_EMOJI} {name}: {type(e).__name__}: {e}")
        return results

    def _deploy_files(self):
        return [
            "tinki-bot.py",
            "config.py",
            "README.md",
            "INSTALL.md",
            "CLAUDE.md",
            "AGENTS.md",
            "requirements.txt",
            "pytest.ini",
            ".env.example",
            ".gitignore",
        ]

    def _deploy_dirs(self):
        return ["cogs", "utils", "tests", "scripts"]

    def _deploy_commit_file(self, repo_root: Path) -> Path:
        return repo_root / ".deploy-commit"

    def _read_deployed_commit(self, repo_root: Path) -> str:
        commit_file = self._deploy_commit_file(repo_root)
        if not commit_file.exists():
            return ""
        return commit_file.read_text(encoding="utf-8").strip()

    def _write_deployed_commit(self, repo_root: Path, commit: str) -> None:
        self._deploy_commit_file(repo_root).write_text(commit.strip() + "\n", encoding="utf-8")

    def _short_commit(self, commit: str) -> str:
        return commit[:7] if commit else "unknown"

    def _github_commit_api_url(self) -> str:
        return GITHUB_REPO_URL.replace("https://github.com/", "https://api.github.com/repos/") + "/commits/main"

    async def _fetch_json_with_retries(self, session, url: str, *, attempts: int = 3):
        last_error = None
        for attempt in range(1, attempts + 1):
            try:
                async with session.get(
                    url,
                    timeout=aiohttp.ClientTimeout(total=30),
                    headers={"Accept": "application/vnd.github+json", "User-Agent": "tinki-bot"},
                ) as resp:
                    resp.raise_for_status()
                    return await resp.json()
            except Exception as exc:
                last_error = exc
                if attempt < attempts:
                    await asyncio.sleep(attempt)
        raise last_error

    async def _fetch_bytes_with_retries(self, session, url: str, *, attempts: int = 3):
        last_error = None
        for attempt in range(1, attempts + 1):
            try:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=60)) as resp:
                    resp.raise_for_status()
                    return await resp.read()
            except Exception as exc:
                last_error = exc
                if attempt < attempts:
                    await asyncio.sleep(attempt)
        raise last_error

    def _format_deploy_error(self, exc: Exception) -> str:
        detail = str(exc).strip() or type(exc).__name__
        lowered = detail.lower()
        if "503" in detail or "service unavailable" in lowered or "upstream connect error" in lowered:
            return "GitHub download is temporarily unavailable. Try `!deploy` again in a minute."
        return detail

    @commands.command(name="restart")
    @commands.has_permissions(administrator=True)
    async def restart_bot(self, ctx):
        if not self._host_admin_allowed(ctx.author):
            await ctx.send("You do not have permission to use this command.")
            return
        await ctx.send("Restarting... brb")
        await asyncio.sleep(1)
        self._request_service_restart()

    @commands.command(name="deploy")
    @commands.has_permissions(administrator=True)
    async def deploy_latest(self, ctx):
        if not self._host_admin_allowed(ctx.author):
            await ctx.send("You do not have permission to use this command.")
            return
        archive_url = GITHUB_REPO_URL.replace("https://github.com/", "https://codeload.github.com/") + "/zip/refs/heads/main"
        try:
            import aiohttp

            repo_root = Path(__file__).resolve().parent.parent
            current_commit = self._read_deployed_commit(repo_root)
            async with aiohttp.ClientSession() as session:
                commit_data = await self._fetch_json_with_retries(session, self._github_commit_api_url())
                github_commit = commit_data["sha"]
                commit_message = commit_data.get("commit", {}).get("message", "").splitlines()[0]

                await ctx.send(
                    f"Deploy check: current `{self._short_commit(current_commit)}` vs GitHub main `{self._short_commit(github_commit)}`"
                )

                if current_commit == github_commit:
                    await ctx.send("Already at GitHub main. No deploy needed.")
                    return

                await ctx.send("Pulling latest repo snapshot from GitHub...")
                content = await self._fetch_bytes_with_retries(session, archive_url)
            if len(content) < 5000:
                await ctx.send(f"Deploy aborted: download looks truncated ({len(content)} bytes).")
                return

            with tempfile.TemporaryDirectory() as tmpdir:
                archive_path = Path(tmpdir) / "repo.zip"
                archive_path.write_bytes(content)
                with zipfile.ZipFile(archive_path) as zf:
                    zf.extractall(tmpdir)

                extracted_roots = [path for path in Path(tmpdir).iterdir() if path.is_dir()]
                if not extracted_roots:
                    await ctx.send("Deploy failed: extracted archive was empty.")
                    return
                extracted_root = extracted_roots[0]

                for file_name in self._deploy_files():
                    source = extracted_root / file_name
                    target = repo_root / file_name
                    if source.exists():
                        self._copy_deploy_file(source, target)

                for dir_name in self._deploy_dirs():
                    source_dir = extracted_root / dir_name
                    target_dir = repo_root / dir_name
                    if source_dir.exists():
                        self._copy_deploy_dir(source_dir, target_dir)

            self._write_deployed_commit(repo_root, github_commit)

            install = await asyncio.create_subprocess_exec(
                sys.executable,
                "-m",
                "pip",
                "install",
                "-r",
                str(repo_root / "requirements.txt"),
                cwd=str(repo_root),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, install_stderr = await install.communicate()
            if install.returncode != 0:
                error_text = install_stderr.decode("utf-8", errors="replace").strip().splitlines()
                detail = error_text[-1] if error_text else f"exit code {install.returncode}"
                await ctx.send(f"Deploy failed during dependency install: {detail}")
                return

            await ctx.send(f"Deployed `{self._short_commit(github_commit)}` — {commit_message}. Restarting... brb 👾")
            await asyncio.sleep(1)
            self._request_service_restart()
        except Exception as e:
            await ctx.send(f"Deploy failed: {self._format_deploy_error(e)}")

    @commands.command(name="awscost")
    @commands.has_permissions(administrator=True)
    async def aws_cost(self, ctx):
        if not user_matches(ctx.author, USER_WHIPTAIL_ID, 'whiptail'):
            await ctx.send("You do not have permission to use this command.")
            return
        await ctx.send(await fetch_aws_cost_summary())

    @commands.command(name="statusreport")
    @commands.has_permissions(administrator=True)
    async def statusreport(self, ctx):
        if not self._host_admin_allowed(ctx.author):
            await ctx.send("You do not have permission to use this command.")
            return

        snapshot = await self._collect_status_snapshot()
        aws_cost_summary = await self._run_status_check_with_timeout("AWS cost", fetch_aws_cost_summary())
        summary, details = self._build_status_report(snapshot, aws_cost_summary)
        report_file = discord.File(io.BytesIO(details.encode("utf-8")), filename="status_report.txt")
        await ctx.send(content=summary, file=report_file)

    @commands.command(name="runtests")
    @commands.has_permissions(administrator=True)
    async def runtests(self, ctx):
        if self._diagnostics_lock.locked():
            await ctx.send(DIAGNOSTICS_BUSY_MESSAGE)
            return
        await ctx.send("Starting command self-tests...")
        async with self._diagnostics_lock:
            results = await self._run_async_diagnostic_check("command selftests", self._run_command_selftests(ctx))
            passed = sum(1 for _, ok, _ in results if ok)
            await ctx.send(self._summary_line("Command tests complete", passed, len(results), "passed").strip())

    @commands.command(name="testurls")
    @commands.has_permissions(administrator=True)
    async def testurls(self, ctx):
        if self._diagnostics_lock.locked():
            await ctx.send(DIAGNOSTICS_BUSY_MESSAGE)
            return
        await ctx.send("Starting URL rewrite tests...")
        async with self._diagnostics_lock:
            results = await self._run_sync_diagnostic_check("url rewrite tests", run_url_selftests)
            for name, ok, reason in results:
                status = TEST_PASS_EMOJI if ok else TEST_FAIL_EMOJI
                detail = "passed" if ok else reason
                await ctx.send(f"{status} {name}: {detail}")
            passed = sum(1 for _, ok, _ in results if ok)
            await ctx.send(self._summary_line("URL tests complete", passed, len(results), "passed").strip())


async def setup(bot):
    await bot.add_cog(Admin(bot))
