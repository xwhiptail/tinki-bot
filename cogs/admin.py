import asyncio
import io
import logging
import shutil
import subprocess
import sys
import tempfile
import zipfile
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


class Admin(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def _status_emoji(self, passed: int, total: int) -> str:
        return TEST_PASS_EMOJI if total and passed == total else TEST_FAIL_EMOJI

    def _summary_line(self, label: str, passed: int, total: int, suffix: str = "tests passed") -> str:
        return f"{self._status_emoji(passed, total)} {label}: {passed}/{total} {suffix}\n"

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

        def _counts(results):
            return sum(1 for _, ok, _ in results if ok), len(results)

        cmd_p, cmd_t = _counts(cmd_results)
        url_p, url_t = _counts(url_results)
        calc_p, calc_t = _counts(calc_results)
        let_p, let_t = _counts(letter_results)
        ins_p, ins_t = _counts(insight_results)
        py_p, py_t = _counts(pytest_results)

        all_results = cmd_results + url_results + calc_results + letter_results + insight_results + pytest_results
        failures = [f"{name}: {reason}" for name, ok, reason in all_results if not ok]

        summary = (
            "Bot restarted - running startup diagnostics...\n"
            "```ini\n[BOOT SEQUENCE COMPLETED]\n```\n"
            f"{self._summary_line('Command grid', cmd_p, cmd_t)}"
            f"{self._summary_line('URL filter matrix', url_p, url_t)}"
            f"{self._summary_line('Calculator gnome', calc_p, calc_t)}"
            f"{self._summary_line('Letter gnome', let_p, let_t)}"
            f"{self._summary_line('Bot insight gnome', ins_p, ins_t)}"
            f"{self._summary_line('Pytest suite', py_p, py_t, 'passed')}"
            f"OpenAI: {openai_balance}\n"
        )
        if failures:
            summary += "\nAnomalies detected:\n" + "".join(f"- {TEST_FAIL_EMOJI} {failure}\n" for failure in failures)
        else:
            summary += "\nAll systems fully operational."

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        lines = [f"Startup Diagnostic Results - {timestamp}\n", "=" * 60 + "\n"]
        for section, results in [
            ("Command Tests", cmd_results),
            ("URL Tests", url_results),
            ("Calculator Tests", calc_results),
            ("Letter Count Tests", letter_results),
            ("Bot Insight Tests", insight_results),
            ("Pytest", pytest_results),
        ]:
            passed, total = _counts(results)
            lines.append(f"\n{self._summary_line(section, passed, total, 'passed')}")
            for name, ok, reason in results:
                if ok:
                    lines.append(f"  {TEST_PASS_EMOJI} {name}\n")
                else:
                    lines.append(f"  {TEST_FAIL_EMOJI} {name} - {reason}\n")

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
            "remindme", "listpersonas",
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
        return ["assets", "cogs", "utils", "tests", "scripts"]

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
        await ctx.send("Restarting... brb")
        await asyncio.sleep(1)
        subprocess.Popen(["sudo", "systemctl", "restart", "tinki-bot"])

    @commands.command(name="deploy")
    @commands.has_permissions(administrator=True)
    async def deploy_latest(self, ctx):
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
                        shutil.copy2(source, target)

                for dir_name in self._deploy_dirs():
                    source_dir = extracted_root / dir_name
                    target_dir = repo_root / dir_name
                    if source_dir.exists():
                        shutil.copytree(source_dir, target_dir, dirs_exist_ok=True)

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
