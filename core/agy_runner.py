import asyncio
import os
import time
from pathlib import Path
from typing import Optional, Callable, Dict, Any, Tuple
from config import AGY_BINARY
from core.memory import MemoryManager
from core.logger import get_logger

logger = get_logger("agy")

class AntigravityRunner:
    _has_previous_session = False
    _last_workspace = None
    _active_process: Optional[asyncio.subprocess.Process] = None
    _active_task_info: Optional[Dict[str, Any]] = None
    _last_execution: Optional[Dict[str, Any]] = None

    @classmethod
    def get_status(cls) -> Dict[str, Any]:
        """Returns the current state and metrics of Antigravity CLI."""
        is_running = cls._active_process is not None and cls._active_process.returncode is None
        elapsed = 0.0
        if is_running and cls._active_task_info:
            elapsed = time.time() - cls._active_task_info.get("start_time", time.time())

        return {
            "is_running": is_running,
            "pid": cls._active_process.pid if is_running else None,
            "elapsed_seconds": round(elapsed, 1) if is_running else 0,
            "active_task": cls._active_task_info if is_running else None,
            "last_execution": cls._last_execution,
            "has_previous_session": cls._has_previous_session,
            "last_workspace": cls._last_workspace,
        }

    @classmethod
    def kill_active(cls) -> Tuple[bool, str]:
        """Kills any active Antigravity CLI process."""
        if cls._active_process and cls._active_process.returncode is None:
            pid = cls._active_process.pid
            try:
                cls._active_process.kill()
                logger.warning(f"Killed active Antigravity process (PID {pid})")
                cls._active_process = None
                cls._active_task_info = None
                return True, f"Killed active Antigravity process (PID {pid})."
            except Exception as e:
                logger.error(f"Failed to kill Antigravity process {pid}: {e}")
                return False, f"Failed to kill process {pid}: {str(e)}"
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
        Executes a prompt through Antigravity CLI non-interactively with permissions bypassed.
        Runs in the specified workspace directory (or active workspace).
        """
        cwd = workspace_dir or MemoryManager.get_active_workspace()
        if not Path(cwd).exists():
            cwd = str(Path.home() / "projects")

        if status_callback:
            status_callback(f"🚀 Invoking Antigravity in `{Path(cwd).name}`...")

        cmd = [
            AGY_BINARY,
            "--dangerously-skip-permissions"
        ]

        if (continue_session or cls._has_previous_session) and cls._last_workspace == cwd:
            cmd.append("--continue")

        cmd.extend(["--print", prompt])

        logger.info(f"Invoking agy in {cwd}: '{prompt[:80]}...'")
        start_time = time.time()

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=cwd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            cls._active_process = process
            cls._active_task_info = {
                "pid": process.pid,
                "prompt": prompt,
                "workspace": cwd,
                "start_time": start_time
            }

            # Read stdout asynchronously line by line for live status updates
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

                    # Throttled progress ping to user every 2.5s for meaningful activity
                    now = time.time()
                    clean = decoded.strip()
                    if status_callback and clean and (now - last_status_time > 2.5):
                        # Filter out raw escape sequences or noisy lines
                        if len(clean) > 4 and not clean.startswith(("{", "}", "[", "]")):
                            status_callback(f"⚙️ `{clean[:70]}`")
                            last_status_time = now

            # Concurrently read stderr and wait for exit
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

            # Truncate if ridiculously long (> 3500 chars)
            if len(out_str) > 3500:
                truncated = out_str[:3400]
                num_backticks = truncated.count("```")
                if num_backticks % 2 != 0:
                    truncated += "\n```"
                out_str = truncated + "\n\n... [output truncated for Telegram]"

            return out_str

        except asyncio.TimeoutError:
            if cls._active_process:
                try:
                    cls._active_process.kill()
                except Exception:
                    pass
            logger.error(f"Antigravity timed out after {timeout}s")
            return f"⏱️ Antigravity timed out after {timeout} seconds."
        except Exception as e:
            logger.error(f"Failed to run Antigravity CLI: {e}")
            return f"❌ Failed to run Antigravity CLI: {str(e)}"
        finally:
            cls._active_process = None
            cls._active_task_info = None
