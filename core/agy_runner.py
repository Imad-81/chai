import asyncio
import os
import re
import shlex
import shutil
import signal
import time
import json
from pathlib import Path
from typing import Optional, Callable, Dict, Any, Tuple
from config import (
    AGY_BINARY, 
    AGY_SPAWN_TERMINAL, 
    AGY_TERMINAL_EMULATOR, 
    AGY_UI_MODE,
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
    def reset_session(cls):
        """Resets the Antigravity session continuation state."""
        cls._has_previous_session = False
        cls._last_workspace = None

    @classmethod
    async def run_prompt(
        cls, 
        prompt: str, 
        workspace_dir: Optional[str] = None,
        timeout: int = 300,
        continue_session: bool = False,
        conversation_id: Optional[str] = None,
        return_details: bool = False,
        status_callback: Optional[Callable[[str], None]] = None
    ) -> Any:
        """
        Executes a prompt through Antigravity CLI.
        Supports explicit session pinning via conversation_id.
        If a desktop display is available and configured:
          - In 'interactive' mode (default): launches the actual Antigravity CLI TUI
            directly in the terminal so the user sees the real CLI interface.
          - In 'print' mode: runs batch mode with a live execution banner and auto-close timer.
        Otherwise falls back to headless subprocess execution.
        """
        cwd = workspace_dir or MemoryManager.get_active_workspace()
        if not Path(cwd).exists():
            cwd = str(Path.home() / "projects")

        # Smart continuation detection (if conversation_id is provided, continuation is explicit)
        if conversation_id:
            is_continuation = False
        elif continue_session is not None:
            is_continuation = bool(continue_session)
        else:
            is_continuation = bool(
                re.match(r"^(?:continue|resume|keep\s+going|go\s+on)\b", prompt.strip(), re.IGNORECASE)
            )

        can_gui, term_bin = cls.can_spawn_terminal()
        if can_gui and term_bin:
            if AGY_UI_MODE == "interactive":
                return await cls._run_interactive_terminal(
                    prompt=prompt,
                    cwd=cwd,
                    term_bin=term_bin,
                    is_continuation=is_continuation,
                    conversation_id=conversation_id,
                    return_details=return_details,
                    timeout=timeout,
                    status_callback=status_callback
                )
            else:
                cmd = [
                    AGY_BINARY,
                    "--dangerously-skip-permissions"
                ]
                if conversation_id:
                    cmd.extend(["--conversation", conversation_id])
                elif is_continuation:
                    cmd.append("--continue")
                cmd.extend(["--print", prompt])

                res = await cls._run_visible_terminal(
                    cmd=cmd,
                    prompt=prompt,
                    cwd=cwd,
                    term_bin=term_bin,
                    timeout=timeout,
                    status_callback=status_callback
                )
                if return_details:
                    return {"text": res, "conversation_id": conversation_id, "duration": 0, "returncode": 0}
                return res
        else:
            cmd = [
                AGY_BINARY,
                "--dangerously-skip-permissions",
                "--output-format", "json"
            ]
            if conversation_id:
                cmd.extend(["--conversation", conversation_id])
            elif is_continuation:
                cmd.append("--continue")
            cmd.extend(["--print", prompt])

            return await cls._run_headless(
                cmd=cmd,
                prompt=prompt,
                cwd=cwd,
                timeout=timeout,
                return_details=return_details,
                status_callback=status_callback
            )

    @classmethod
    async def _run_interactive_terminal(
        cls,
        prompt: str,
        cwd: str,
        term_bin: str,
        is_continuation: bool,
        timeout: int,
        conversation_id: Optional[str] = None,
        return_details: bool = False,
        status_callback: Optional[Callable[[str], None]] = None
    ) -> Any:
        """
        Launches the actual full Antigravity CLI TUI directly in a visible terminal
        window on the user's screen using interactive mode (`agy -i <prompt>`).
        Monitors the session transcript live to provide real-time updates and capture
        the final turn result for Telegram.
        """
        if status_callback:
            status_callback(f"🖥️ Opening Antigravity interactive CLI on your screen...")

        start_time = time.time()
        brain_dir = Path.home() / ".gemini" / "antigravity-cli" / "brain"

        # Check initial max step index on existing transcript if continuing
        initial_step_count = 0
        if (is_continuation or conversation_id) and brain_dir.exists():
            try:
                candidates = sorted(
                    brain_dir.glob("*/.system_generated/logs/transcript.jsonl"),
                    key=lambda x: x.stat().st_mtime,
                    reverse=True
                )
                if candidates:
                    for line in candidates[0].read_text(encoding="utf-8", errors="replace").splitlines():
                        if line.strip():
                            try:
                                initial_step_count = max(initial_step_count, json.loads(line).get("step_index", 0) + 1)
                            except Exception:
                                pass
            except Exception:
                pass

        agy_args = [
            AGY_BINARY,
            "--dangerously-skip-permissions"
        ]
        if conversation_id:
            agy_args.extend(["--conversation", conversation_id])
        elif is_continuation:
            agy_args.append("--continue")
        agy_args.extend(["-i", prompt])

        win_title = f"Antigravity CLI - {Path(cwd).name}"
        if "gnome-terminal" in term_bin:
            term_cmd = [term_bin, f"--title={win_title}", "--working-directory", cwd, "--"] + agy_args
        elif "x-terminal-emulator" in term_bin:
            cmd_str = " ".join(shlex.quote(c) for c in agy_args)
            term_cmd = [term_bin, "-T", win_title, "-e", f"bash -c 'cd {shlex.quote(cwd)} && {cmd_str}'"]
        else:
            cmd_str = " ".join(shlex.quote(c) for c in agy_args)
            term_cmd = [term_bin, "-e", f"bash -c 'cd {shlex.quote(cwd)} && {cmd_str}'"]

        env = os.environ.copy()
        if "DISPLAY" not in env:
            env["DISPLAY"] = ":0"
        if "WAYLAND_DISPLAY" not in env and Path("/run/user/1000/wayland-0").exists():
            env["WAYLAND_DISPLAY"] = "wayland-0"

        logger.info(f"Spawning interactive agy TUI in {cwd}: '{prompt[:80]}...'")

        proc = await asyncio.create_subprocess_exec(
            *term_cmd,
            cwd=cwd,
            env=env,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL
        )
        cls._active_process = proc
        cls._active_task_info = {
            "prompt": prompt,
            "workspace": cwd,
            "start_time": start_time,
            "terminal": True,
            "mode": "interactive"
        }

        # Locate the transcript file created or updated for this session
        transcript_file = None
        for _ in range(30):
            try:
                if brain_dir.exists():
                    candidates = sorted(
                        brain_dir.glob("*/.system_generated/logs/transcript.jsonl"),
                        key=lambda x: x.stat().st_mtime,
                        reverse=True
                    )
                    if candidates and candidates[0].stat().st_mtime >= start_time - 3.0:
                        transcript_file = candidates[0]
                        break
            except Exception:
                pass
            await asyncio.sleep(0.5)

        logger.info(f"Interactive agy transcript located: {transcript_file}")

        # Monitor transcript for live status & final response
        response_content = None
        last_step_idx = initial_step_count - 1
        last_status_time = time.time()

        try:
            while True:
                if time.time() - start_time > timeout:
                    cls.kill_active()
                    return f"⏱️ Antigravity interactive session timed out after {timeout} seconds."

                if transcript_file and transcript_file.exists():
                    try:
                        lines = transcript_file.read_text(encoding="utf-8", errors="replace").splitlines()
                        for line in lines:
                            if not line.strip():
                                continue
                            data = json.loads(line)
                            step_idx = data.get("step_index", 0)
                            step_type = data.get("type")
                            status = data.get("status")
                            tool_calls = data.get("tool_calls", [])

                            if step_idx > last_step_idx:
                                if step_type == "PLANNER_RESPONSE" and status == "DONE" and not tool_calls:
                                    response_content = data.get("content", "").strip()
                                last_step_idx = step_idx

                        if response_content:
                            break
                    except Exception as e:
                        logger.debug(f"Error reading transcript: {e}")

                await asyncio.sleep(1.0)

            duration = round(time.time() - start_time, 2)
            cls._has_previous_session = True
            cls._last_workspace = cwd
            cls._last_execution = {
                "prompt": prompt[:100],
                "workspace": cwd,
                "duration_seconds": duration,
                "returncode": 0,
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
            }

            if not response_content:
                response_content = "✅ Antigravity completed the task successfully in your terminal."

            if len(response_content) > 3500:
                truncated = response_content[:3400]
                num_backticks = truncated.count("```")
                if num_backticks % 2 != 0:
                    truncated += "\n```"
                response_content = truncated + "\n\n... [output truncated for Telegram]"

            conv_id = conversation_id
            if not conv_id and transcript_file:
                try:
                    conv_id = transcript_file.parent.parent.name
                except Exception:
                    pass

            if return_details:
                return {
                    "text": response_content,
                    "conversation_id": conv_id,
                    "duration": duration,
                    "returncode": 0
                }

            return response_content

        finally:
            cls._active_process = None
            cls._active_pid = None
            cls._active_task_info = None

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

                await asyncio.sleep(0.5)

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
        return_details: bool = False,
        status_callback: Optional[Callable[[str], None]] = None
    ) -> Any:
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
                while True:
                    line = await process.stdout.readline()
                    if not line:
                        break
                    stdout_chunks.append(line.decode("utf-8", errors="replace"))

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
                err_msg = f"⚠️ Antigravity exited with code {process.returncode}:\n{err_str or out_str}"
                if return_details:
                    return {"text": err_msg, "conversation_id": None, "duration": duration, "returncode": process.returncode}
                return err_msg

            cls._has_previous_session = True
            cls._last_workspace = cwd
            logger.info(f"Antigravity task completed in {duration}s")

            extracted_conv_id = None
            clean_text = out_str
            if "{" in out_str and "}" in out_str:
                start_idx = out_str.find("{")
                end_idx = out_str.rfind("}")
                if start_idx != -1 and end_idx != -1:
                    try:
                        j_data = json.loads(out_str[start_idx:end_idx+1])
                        extracted_conv_id = j_data.get("conversation_id")
                        if "response" in j_data:
                            clean_text = j_data.get("response", "").strip()
                    except Exception:
                        pass

            if not clean_text:
                clean_text = "✅ Antigravity completed the task successfully (no text output)."

            if len(clean_text) > 3500 and not return_details:
                truncated = clean_text[:3400]
                num_backticks = truncated.count("```")
                if num_backticks % 2 != 0:
                    truncated += "\n```"
                clean_text = truncated + "\n\n... [output truncated for Telegram]"

            if return_details:
                return {
                    "text": clean_text,
                    "conversation_id": extracted_conv_id,
                    "duration": duration,
                    "returncode": 0
                }

            return clean_text

        except asyncio.TimeoutError:
            cls.kill_active()
            logger.error(f"Antigravity timed out after {timeout}s")
            msg = f"⏱️ Antigravity timed out after {timeout} seconds."
            if return_details:
                return {"text": msg, "conversation_id": None, "duration": timeout, "returncode": -1}
            return msg
        except Exception as e:
            logger.error(f"Failed to run Antigravity CLI: {e}")
            msg = f"❌ Failed to run Antigravity CLI: {str(e)}"
            if return_details:
                return {"text": msg, "conversation_id": None, "duration": 0, "returncode": -1}
            return msg
        finally:
            cls._active_process = None
            cls._active_pid = None
            cls._active_task_info = None
