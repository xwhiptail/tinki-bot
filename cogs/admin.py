import asyncio
import io
import subprocess
from datetime import datetime
from pathlib import Path

import discord
from discord.ext import commands

from config import GITHUB_REPO_URL
from utils.openai_helpers import fetch_openai_balance
from utils.selftests import run_url_selftests, run_calculate_selftests, run_letter_count_selftests


class Admin(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def run_startup_tests(self):
        await self.bot.wait_until_ready()
        test_channel = discord.utils.get(self.bot.get_all_channels(), name="bot-test")
        if not test_channel:
            print("No #bot-test channel found; skipping startup tests.")
            return

        cmd_results = await self._run_command_selftests(ctx=None)
        url_results = run_url_selftests()
        calc_results = run_calculate_selftests()
        letter_results = run_letter_count_selftests()
        openai_balance = await fetch_openai_balance()

        def _counts(results):
            return sum(1 for _, ok, _ in results if ok), len(results)

        cmd_p, cmd_t = _counts(cmd_results)
        url_p, url_t = _counts(url_results)
        calc_p, calc_t = _counts(calc_results)
        let_p, let_t = _counts(letter_results)

        all_results = cmd_results + url_results + calc_results + letter_results
        failures = [f"{name}: {reason}" for name, ok, reason in all_results if not ok]

        summary = (
            "🤖 **Bot restarted — running startup diagnostics…**\n"
            "```ini\n[BOOT SEQUENCE COMPLETED]\n```\n"
            f"🧪 **Command grid:** {cmd_p}/{cmd_t} tests passed\n"
            f"🌐 **URL filter matrix:** {url_p}/{url_t} tests passed\n"
            f"🔢 **Calculator gnome:** {calc_p}/{calc_t} tests passed\n"
            f"🔤 **Letter gnome:** {let_p}/{let_t} tests passed\n"
            f"💸 **OpenAI:** {openai_balance}\n"
        )
        if failures:
            summary += "\n⚠️ **Anomalies detected:**\n" + "".join(f"• {f}\n" for f in failures)
        else:
            summary += "\n✨ **All systems fully operational.**"

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        lines = [f"Startup Diagnostic Results — {timestamp}\n", "=" * 60 + "\n"]
        for section, results in [
            ("Command Tests", cmd_results),
            ("URL Tests", url_results),
            ("Calculator Tests", calc_results),
            ("Letter Count Tests", letter_results),
        ]:
            p, t = _counts(results)
            lines.append(f"\n{section}: {p}/{t} passed\n")
            for name, ok, reason in results:
                tag = "[PASS]" if ok else f"[FAIL] — {reason}"
                lines.append(f"  {tag} {name}\n")

        buf = io.BytesIO("".join(lines).encode("utf-8"))
        await test_channel.send(content=summary, file=discord.File(buf, filename="startup_test_results.txt"))

    async def _run_command_selftests(self, ctx=None):
        tests = [
            "pb", "avg", "median", "all", "bowlinggraph", "bowlingdistgraph",
            "gif", "random", "github", "allemotes", "roulette", "cat", "dog", "dogbark",
            "remindme", "listpersonas", "currentpersona",
            "sussy", "sussygraph", "explode", "explodegraph", "grindcount", "grindgraph",
            "minecraftstatus", "minecraftserver", "uptime", "skyfactorystatus", "skyfactoryserver",
        ]
        results = []
        for name in tests:
            cmd = self.bot.get_command(name)
            if cmd is None:
                results.append((name, False, "command not found"))
                if ctx:
                    await ctx.send(f"{name}: ❌ command not found")
                continue
            try:
                if ctx:
                    await ctx.invoke(cmd)
                    await ctx.send(f"{name}: ✅ passed")
                results.append((name, True, None))
            except Exception as e:
                results.append((name, False, f"{type(e).__name__}: {e}"))
                if ctx:
                    await ctx.send(f"{name}: ❌ {type(e).__name__}: {e}")
        return results

    @commands.command(name='restart')
    @commands.has_permissions(administrator=True)
    async def restart_bot(self, ctx):
        await ctx.send("Restarting… brb 👾")
        await asyncio.sleep(1)
        subprocess.Popen(['sudo', 'systemctl', 'restart', 'tinki-bot'])

    @commands.command(name='deploy')
    @commands.has_permissions(administrator=True)
    async def deploy_latest(self, ctx):
        raw_url = GITHUB_REPO_URL.replace('github.com', 'raw.githubusercontent.com') + '/main/tinki-bot.py'
        await ctx.send("Pulling latest from GitHub…")
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.get(raw_url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                    resp.raise_for_status()
                    content = await resp.read()
            if len(content) < 500:
                await ctx.send(f"Deploy aborted: download looks truncated ({len(content)} bytes).")
                return
            target = Path(__file__).resolve().parent.parent / 'tinki-bot.py'
            tmp = target.with_suffix('.py.tmp')
            tmp.write_bytes(content)
            tmp.replace(target)
            await ctx.send("Updated. Restarting… brb 👾")
            await asyncio.sleep(1)
            subprocess.Popen(['sudo', 'systemctl', 'restart', 'tinki-bot'])
        except Exception as e:
            await ctx.send(f"Deploy failed: {e}")

    @commands.command(name="runtests")
    @commands.has_permissions(administrator=True)
    async def runtests(self, ctx):
        await ctx.send("Starting command self-tests…")
        results = await self._run_command_selftests(ctx)
        passed = sum(1 for _, ok, _ in results if ok)
        await ctx.send(f"Command tests complete: {passed}/{len(results)} passed.")

    @commands.command(name="testurls")
    @commands.has_permissions(administrator=True)
    async def testurls(self, ctx):
        await ctx.send("Starting URL rewrite tests…")
        results = run_url_selftests()
        for name, ok, reason in results:
            await ctx.send(f"{name}: {'✅ passed' if ok else f'❌ {reason}'}")
        passed = sum(1 for _, ok, _ in results if ok)
        await ctx.send(f"URL tests complete: {passed}/{len(results)} passed.")


async def setup(bot):
    await bot.add_cog(Admin(bot))
