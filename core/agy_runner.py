import asyncio
import os
import subprocess
from pathlib import Path
from typing import Optional, Callable
from config import AGY_BINARY
from core.memory import MemoryManager

class AntigravityRunner:
    _has_previous_session = False
    _last_workspace = None

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

        # Use --continue if requested and we have run before in this same workspace
        if (continue_session or cls._has_previous_session) and cls._last_workspace == cwd:
            cmd.append("--continue")

        cmd.extend(["--print", prompt])

        print(f"[AGYRunner] Running agy in {cwd}: {prompt[:80]}...")

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=cwd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
            out_str = stdout.decode("utf-8", errors="replace").strip()
            err_str = stderr.decode("utf-8", errors="replace").strip()

            if process.returncode != 0:
                print(f"[AGYRunner] Failed (code {process.returncode}): {err_str}")
                return f"⚠️ Antigravity exited with code {process.returncode}:\n{err_str or out_str}"

            cls._has_previous_session = True
            cls._last_workspace = cwd

            if not out_str:
                return "✅ Antigravity completed the task successfully (no text output)."

            # Truncate if ridiculously long for a single WhatsApp message (> 3500 chars)
            if len(out_str) > 3500:
                # Check for unclosed code block
                truncated = out_str[:3400]
                num_backticks = truncated.count("```")
                if num_backticks % 2 != 0:
                    truncated += "\n```"
                out_str = truncated + "\n\n... [output truncated for WhatsApp]"

            return out_str

        except asyncio.TimeoutError:
            try:
                process.kill()
            except Exception:
                pass
            return f"⏱️ Antigravity timed out after {timeout} seconds."
        except Exception as e:
            return f"❌ Failed to run Antigravity CLI: {str(e)}"
