import asyncio
import os
import re
import shlex
import shutil
import signal
import time
from pathlib import Path
from typing import Optional, Callable, Dict, Any, Tuple
from config import (
    AGY_BINARY, 
    AGY_SPAWN_TERMINAL, 
    AGY_TERMINAL_EMULATOR, 
    DATA_DIR, 
    LOG_DIR
)
from core.memory import MemoryManager
from core.logger import get_logger

logger = get_logger("agy")

class AntigravityRunner:
    _has_previous_session = False
    _last_workspace = None
    _active_process: Optional[Any] = None
    _active_pid: Optional[int] = None
    _active_task_info: Optional[Dict[str, Any]] = None
    _last_execution: Optional[Dict[str, Any]] = None

    @classmethod
    def can_spawn_terminal(cls) -> Tuple[bool, Optional[str]]:
        """Checks if a graphical terminal emulator can be spawned on screen."""
        if not AGY_SPAWN_TERMINAL:
            return False, None
        
        has_display = bool(os.getenv("DISPLAY") or os.getenv("WAYLAND_DISPLAY"))
        if not has_display:
            return False, None

        for term in [AGY_TERMINAL_EMULATOR, "gnome-terminal", "x-terminal-emulator", "xterm"]:
            path = shutil.which(term)
            if path:
                return True, path

        return False, None

    @classmethod
    def get_status(cls) -> Dict[str, Any]:
        """Returns the current state and metrics of Antigravity CLI."""
        is_running = cls._active_process is not None
        if hasattr(cls._active_process, "returncode"):
            is_running = cls._active_process.returncode is None
        elapsed = 0.0
        if is_running and cls._active_task_info:
            elapsed = time.time() - cls._active_task_info.get("start_time", time.time())

        return {
            "is_running": is_running,
            "pid": cls._active_pid,
            "elapsed_seconds": round(elapsed, 1) if is_running else 0,
            "active_task": cls._active_task_info if is_running else None,
            "last_execution": cls._last_execution,
            "has_previous_session": cls._has_previous_session,
            "last_workspace": cls._last_workspace,
        }

    @classmethod
    def kill_active(cls) -> Tuple[bool, str]:
        """Kills any active Antigravity CLI process."""
        killed = False
        pid = cls._active_pid
        if cls._active_pid:
            try:
                os.kill(cls._active_pid, signal.SIGTERM)
                killed = True
            except Exception:
                pass

        if cls._active_process:
            try:
                if hasattr(cls._active_process, "kill"):
                    cls._active_process.kill()
                killed = True
            except Exception:
                pass

        if killed:
            logger.warning(f"Killed active Antigravity process (PID {pid})")
            cls._active_process = None
            cls._active_pid = None
            cls._active_task_info = None
            return True, f"Killed active Antigravity process (PID {pid})."

        return False, "No Antigravity task is currently executing."

    @classmethod
    async def run_prompt(
        cls, 
        prompt: str, 
        workspace_dir: Optional[str] = None,
        timeout: int = 300,
        continue_session: bool = False,
        status_callback: Optional[Callable[[str], None]] = None
    ) -> str:
        """
        Executes a prompt through Antigravity CLI.
        If a desktop display is available and configured, spawns a visible terminal
        window on screen so the user can watch the CLI execute in real time.
        Otherwise falls back to headless subprocess execution.
        """
        cwd = workspace_dir or MemoryManager.get_active_workspace()
        if not Path(cwd).exists():
            cwd = str(Path.home() / "projects")

        # Smart continuation detection: only continue if explicitly requested or prompt asks to continue
        is_continuation = continue_session or bool(
            re.match(r"^(?:continue|resume|keep\s+going|go\s+on)\b", prompt.strip(), re.IGNORECASE)
        )

        cmd = [
            AGY_BINARY,
            "--dangerously-skip-permissions"
        ]

        if is_continuation and cls._has_previous_session and cls._last_workspace == cwd:
            cmd.append("--continue")

        cmd.extend(["--print", prompt])

        can_gui, term_bin = cls.can_spawn_terminal()
        if can_gui and term_bin:
            return await cls._run_visible_terminal(
                cmd=cmd,
                prompt=prompt,
                cwd=cwd,
                term_bin=term_bin,
                timeout=timeout,
                status_callback=status_callback
            )
        else:
            return await cls._run_headless(
                cmd=cmd,
                prompt=prompt,
                cwd=cwd,
                timeout=timeout,
                status_callback=status_callback
            )

    @classmethod
    async def _run_visible_terminal(
        cls,
        cmd: list,
        prompt: str,
        cwd: str,
        term_bin: str,
        timeout: int,
        status_callback: Optional[Callable[[str], None]] = None
    ) -> str:
        run_id = f"agy_{int(time.time() * 1000)}"
        run_dir = LOG_DIR / "runs"
        run_dir.mkdir(parents=True, exist_ok=True)

        script_path = run_dir / f"{run_id}.sh"
        log_path = run_dir / f"{run_id}.log"
        done_path = run_dir / f"{run_id}.done"
        pid_path = run_dir / f"{run_id}.pid"

        if status_callback:
            status_callback(f"🖥️ Spawning Antigravity terminal for `{Path(cwd).name}` on screen...")

        # Quote command for shell execution
        cmd_str = " ".join(shlex.quote(c) for c in cmd)
        prompt_preview = (prompt[:120] + "...") if len(prompt) > 120 else prompt
        prompt_preview_clean = prompt_preview.replace('"', '\\"').replace('$', '\\$')
        cwd_clean = cwd.replace('"', '\\"')

        script_content = f"""#!/usr/bin/env bash
# Auto-generated by Chai for Antigravity live session
set -o pipefail

echo $$ > {shlex.quote(str(pid_path))}

cleanup() {{
    code=$?
    if [ ! -f {shlex.quote(str(done_path))} ]; then
        echo $code > {shlex.quote(str(done_path))}
    fi
}}
trap cleanup EXIT INT TERM

echo -e "\\033[1;36m═══════════════════════════════════════════════════════════════\\033[0m"
echo -e "\\033[1;32m🤖 CHAI ANTIGRAVITY AGENT DISPATCHED\\033[0m"
echo -e "\\033[1;34m📁 Workspace:\\033[0m {cwd_clean}"
echo -e "\\033[1;34m📋 Task:\\033[0m      {prompt_preview_clean}"
echo -e "\\033[1;36m═══════════════════════════════════════════════════════════════\\033[0m"
echo ""

cd {shlex.quote(cwd)}
{cmd_str} 2>&1 | tee {shlex.quote(str(log_path))}
EXIT_CODE=${{PIPESTATUS[0]}}
echo $EXIT_CODE > {shlex.quote(str(done_path))}

echo ""
echo -e "\\033[1;36m═══════════════════════════════════════════════════════════════\\033[0m"
if [ $EXIT_CODE -eq 0 ]; then
    echo -e "\\033[1;32m✅ Antigravity completed successfully (Exit code: 0).\\033[0m"
else
    echo -e "\\033[1;31m⚠️ Antigravity exited with code: $EXIT_CODE.\\033[0m"
fi
echo -e "\\033[0;33mWindow will auto-close in 15 seconds (or press any key to close now)...\\033[0m"
read -t 15 -n 1 -s
"""
        script_path.write_text(script_content, encoding="utf-8")
        script_path.chmod(0o755)

        env = os.environ.copy()
        if "DISPLAY" not in env:
            env["DISPLAY"] = ":0"
        if "WAYLAND_DISPLAY" not in env and Path("/run/user/1000/wayland-0").exists():
            env["WAYLAND_DISPLAY"] = "wayland-0"

        win_title = f"Chai - Antigravity ({Path(cwd).name})"
        
        if "gnome-terminal" in term_bin:
            term_cmd = [term_bin, f"--title={win_title}", "--", "bash", str(script_path)]
        elif "x-terminal-emulator" in term_bin:
            term_cmd = [term_bin, "-T", win_title, "-e", f"bash {shlex.quote(str(script_path))}"]
        else:
            term_cmd = [term_bin, "-e", f"bash {shlex.quote(str(script_path))}"]

        logger.info(f"Spawning visible terminal for agy in {cwd}: '{prompt[:80]}...'")
        start_time = time.time()

        proc = await asyncio.create_subprocess_exec(
            *term_cmd,
            env=env,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL
        )
        cls._active_process = proc
        cls._active_task_info = {
            "prompt": prompt,
            "workspace": cwd,
            "start_time": start_time,
            "terminal": True
        }

        # Check for pid file
        for _ in range(10):
            if pid_path.exists():
                try:
                    cls._active_pid = int(pid_path.read_text().strip())
                except Exception:
                    pass
                break
            await asyncio.sleep(0.1)

        last_pos = 0
        last_status_time = time.time()
        exit_code = 0

        try:
            while True:
                if done_path.exists():
                    try:
                        content = done_path.read_text().strip()
                        exit_code = int(content) if (content.isdigit() or (content.startswith('-') and content[1:].isdigit())) else 0
                    except Exception:
                        exit_code = 0
                    break

                if time.time() - start_time > timeout:
                    cls.kill_active()
                    return f"⏱️ Antigravity timed out after {timeout} seconds."

                # Stream status updates from log_path to Telegram
                if log_path.exists():
                    try:
                        with open(log_path, "r", encoding="utf-8", errors="replace") as f:
                            f.seek(last_pos)
                            new_text = f.read()
                            last_pos = f.tell()
                            if new_text and status_callback:
                                now = time.time()
                                for line in new_text.splitlines():
                                    clean = line.strip()
                                    if clean and (now - last_status_time > 2.5):
                                        if len(clean) > 4 and not clean.startswith(("{", "}", "[", "]")):
                                            status_callback(f"⚙️ `{clean[:70]}`")
                                            last_status_time = now
                    except Exception:
                        pass

                await asyncio.sleep(0.5)

            # Read full output from session log
            out_str = ""
            if log_path.exists():
                out_str = log_path.read_text(encoding="utf-8", errors="replace").strip()

            duration = round(time.time() - start_time, 2)
            cls._last_execution = {
                "prompt": prompt[:100],
                "workspace": cwd,
                "duration_seconds": duration,
                "returncode": exit_code,
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
            }

            if exit_code != 0:
                logger.warning(f"Antigravity exited with code {exit_code}")
                return f"⚠️ Antigravity exited with code {exit_code}:\n{out_str}"

            cls._has_previous_session = True
            cls._last_workspace = cwd
            logger.info(f"Antigravity task completed in {duration}s")

            if not out_str:
                return "✅ Antigravity completed the task successfully (no text output)."

            # Truncate if ridiculously long (> 3500 chars for Telegram message limits)
            if len(out_str) > 3500:
                truncated = out_str[:3400]
                num_backticks = truncated.count("```")
                if num_backticks % 2 != 0:
                    truncated += "\n```"
                out_str = truncated + "\n\n... [output truncated for Telegram]"

            return out_str

        finally:
            cls._active_process = None
            cls._active_pid = None
            cls._active_task_info = None
            try:
                if script_path.exists():
                    script_path.unlink()
                if pid_path.exists():
                    pid_path.unlink()
                if done_path.exists():
                    done_path.unlink()
            except Exception:
                pass

    @classmethod
    async def _run_headless(
        cls,
        cmd: list,
        prompt: str,
        cwd: str,
        timeout: int,
        status_callback: Optional[Callable[[str], None]] = None
    ) -> str:
        if status_callback:
            status_callback(f"🚀 Invoking Antigravity in `{Path(cwd).name}`...")

        logger.info(f"Invoking agy headless in {cwd}: '{prompt[:80]}...'")
        start_time = time.time()

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=cwd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            cls._active_process = process
            cls._active_pid = process.pid
            cls._active_task_info = {
                "pid": process.pid,
                "prompt": prompt,
                "workspace": cwd,
                "start_time": start_time,
                "terminal": False
            }

            stdout_chunks = []
            last_status_time = time.time()

            async def read_stream():
                nonlocal last_status_time
                while True:
                    line = await process.stdout.readline()
                    if not line:
                        break
                    decoded = line.decode("utf-8", errors="replace")
                    stdout_chunks.append(decoded)

                    now = time.time()
                    clean = decoded.strip()
                    if status_callback and clean and (now - last_status_time > 2.5):
                        if len(clean) > 4 and not clean.startswith(("{", "}", "[", "]")):
                            status_callback(f"⚙️ `{clean[:70]}`")
                            last_status_time = now

            stderr_chunks = []
            async def read_stderr():
                while True:
                    line = await process.stderr.readline()
                    if not line:
                        break
                    stderr_chunks.append(line.decode("utf-8", errors="replace"))

            await asyncio.wait_for(
                asyncio.gather(read_stream(), read_stderr(), process.wait()),
                timeout=timeout
            )

            out_str = "".join(stdout_chunks).strip()
            err_str = "".join(stderr_chunks).strip()

            duration = round(time.time() - start_time, 2)
            cls._last_execution = {
                "prompt": prompt[:100],
                "workspace": cwd,
                "duration_seconds": duration,
                "returncode": process.returncode,
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
            }

            if process.returncode != 0:
                logger.warning(f"Antigravity exited with code {process.returncode}: {err_str[:200]}")
                return f"⚠️ Antigravity exited with code {process.returncode}:\n{err_str or out_str}"

            cls._has_previous_session = True
            cls._last_workspace = cwd
            logger.info(f"Antigravity task completed in {duration}s")

            if not out_str:
                return "✅ Antigravity completed the task successfully (no text output)."

            if len(out_str) > 3500:
                truncated = out_str[:3400]
                num_backticks = truncated.count("```")
                if num_backticks % 2 != 0:
                    truncated += "\n```"
                out_str = truncated + "\n\n... [output truncated for Telegram]"

            return out_str

        except asyncio.TimeoutError:
            cls.kill_active()
            logger.error(f"Antigravity timed out after {timeout}s")
            return f"⏱️ Antigravity timed out after {timeout} seconds."
        except Exception as e:
            logger.error(f"Failed to run Antigravity CLI: {e}")
            return f"❌ Failed to run Antigravity CLI: {str(e)}"
        finally:
            cls._active_process = None
            cls._active_pid = None
            cls._active_task_info = None
