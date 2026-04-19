import asyncio
import io
import logging
import shutil
import subprocess
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
        log.warning("[startup tests] task started")
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

        cmd_results = await self._run_command_selftests(ctx=None)
        url_results = run_url_selftests()
        calc_results = run_calculate_selftests()
        letter_results = run_letter_count_selftests()
        insight_results = run_bot_insight_selftests()
        pytest_results = await self._run_pytest_suite()
        openai_balance = await fetch_openai_balance()
        aws_cost_summary = await fetch_aws_cost_summary()

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
        except discord.Forbidden:
            await test_channel.send(content=summary)

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

        stdout, stderr = await proc.communicate()
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
        subprocess.Popen(["sudo", "systemctl", "restart", "tinki-bot"])

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
            subprocess.Popen(["sudo", "systemctl", "restart", "tinki-bot"])
        except Exception as e:
            await ctx.send(f"Deploy failed: {self._format_deploy_error(e)}")

    @commands.command(name="awscost")
    @commands.has_permissions(administrator=True)
    async def aws_cost(self, ctx):
        if not user_matches(ctx.author, USER_WHIPTAIL_ID, 'whiptail'):
            await ctx.send("You do not have permission to use this command.")
            return
        await ctx.send(await fetch_aws_cost_summary())

    @commands.command(name="runtests")
    @commands.has_permissions(administrator=True)
    async def runtests(self, ctx):
        await ctx.send("Starting command self-tests...")
        results = await self._run_command_selftests(ctx)
        passed = sum(1 for _, ok, _ in results if ok)
        await ctx.send(self._summary_line("Command tests complete", passed, len(results), "passed").strip())

    @commands.command(name="testurls")
    @commands.has_permissions(administrator=True)
    async def testurls(self, ctx):
        await ctx.send("Starting URL rewrite tests...")
        results = run_url_selftests()
        for name, ok, reason in results:
            status = TEST_PASS_EMOJI if ok else TEST_FAIL_EMOJI
            detail = "passed" if ok else reason
            await ctx.send(f"{status} {name}: {detail}")
        passed = sum(1 for _, ok, _ in results if ok)
        await ctx.send(self._summary_line("URL tests complete", passed, len(results), "passed").strip())


async def setup(bot):
    await bot.add_cog(Admin(bot))
