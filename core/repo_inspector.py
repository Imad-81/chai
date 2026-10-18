import os
import re
import subprocess
import json
from pathlib import Path
from typing import Optional, Dict, Any, List
from config import PROJECTS_ROOT
from core.memory import MemoryManager
from core.logger import get_logger

logger = get_logger("repo_inspector")

class RepoInspector:
    """Zero-overhead, high-speed (< 10ms) local git and repository inspector."""

    @classmethod
    def resolve_target_repo(cls, text: str) -> Path:
        """
        Identifies which repository in PROJECTS_ROOT is mentioned in text,
        or defaults to the active workspace.
        """
        text_lower = text.lower()
        active_path = Path(MemoryManager.get_active_workspace())

        if not PROJECTS_ROOT.exists():
            return active_path

        # 1. Check if any repository name is explicitly mentioned
        for p in PROJECTS_ROOT.iterdir():
            if p.is_dir() and not p.name.startswith("."):
                name_clean = p.name.lower()
                name_variants = [
                    name_clean,
                    name_clean.replace("-", " "),
                    name_clean.replace("_", " "),
                    name_clean.replace("-", ""),
                    name_clean.replace("_", "")
                ]
                for v in name_variants:
                    if re.search(r"\b" + re.escape(v) + r"\b", text_lower):
                        return p

        # 2. Fall back to active workspace
        return active_path if active_path.exists() else PROJECTS_ROOT

    @classmethod
    def get_last_commit(cls, repo_path: Path) -> str:
        """Returns the latest commit details in formatted markdown."""
        if not (repo_path / ".git").exists():
            return f"⚠️ `{repo_path.name}` is not a git repository."

        try:
            branch = subprocess.check_output(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                cwd=str(repo_path), stderr=subprocess.DEVNULL, text=True
            ).strip()

            log = subprocess.check_output(
                ["git", "log", "-1", "--format=Commit:  %h (%H)%nAuthor:  %an <%ae>%nDate:    %cd (%cr)%nMessage: %s"],
                cwd=str(repo_path), stderr=subprocess.DEVNULL, text=True
            ).strip()

            remote_url = cls.get_remote_url(repo_path)
            remote_str = f"\n• *Remote:* `{remote_url}`" if remote_url else ""

            return (
                f"📌 *Latest Commit on `{repo_path.name}`* (`{branch}` branch):{remote_str}\n"
                f"```text\n{log}\n```"
            )
        except Exception as e:
            return f"❌ Error reading git log for `{repo_path.name}`: {e}"

    @classmethod
    def get_recent_commits(cls, repo_path: Path, count: int = 5) -> str:
        """Returns the last N commits in oneline format."""
        if not (repo_path / ".git").exists():
            return f"⚠️ `{repo_path.name}` is not a git repository."

        try:
            branch = subprocess.check_output(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                cwd=str(repo_path), stderr=subprocess.DEVNULL, text=True
            ).strip()

            log = subprocess.check_output(
                ["git", "log", f"-n{count}", "--format=• `%h` - %s _(%cr)_"],
                cwd=str(repo_path), stderr=subprocess.DEVNULL, text=True
            ).strip()

            return f"📜 *Recent Commits on `{repo_path.name}`* (`{branch}`):\n{log}"
        except Exception as e:
            return f"❌ Error reading commits for `{repo_path.name}`: {e}"

    @classmethod
    def get_git_status(cls, repo_path: Path) -> str:
        """Returns current branch, tracking status, and uncommitted modifications."""
        if not (repo_path / ".git").exists():
            return f"⚠️ `{repo_path.name}` is not a git repository."

        try:
            branch = subprocess.check_output(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                cwd=str(repo_path), stderr=subprocess.DEVNULL, text=True
            ).strip()

            status = subprocess.check_output(
                ["git", "status", "--short"],
                cwd=str(repo_path), stderr=subprocess.DEVNULL, text=True
            ).strip()

            status_str = f"```\n{status}\n```" if status else "✅ _Working tree clean, no uncommitted changes._"
            remote = cls.get_remote_url(repo_path)
            remote_info = f"\n• *Remote:* `{remote}`" if remote else ""

            return (
                f"🌿 *Git Status for `{repo_path.name}`*\n"
                f"• *Branch:* `{branch}`{remote_info}\n"
                f"• *Changes:*\n{status_str}"
            )
        except Exception as e:
            return f"❌ Error checking status for `{repo_path.name}`: {e}"

    @classmethod
    def get_remote_url(cls, repo_path: Path) -> Optional[str]:
        """Returns origin remote URL if configured."""
        try:
            return subprocess.check_output(
                ["git", "config", "--get", "remote.origin.url"],
                cwd=str(repo_path), stderr=subprocess.DEVNULL, text=True
            ).strip()
        except Exception:
            return None

    @classmethod
    def detect_tech_stack(cls, repo_path: Path) -> str:
        """Infers the programming language and framework for a project."""
        indicators = []
        if (repo_path / "package.json").exists():
            indicators.append("Node.js")
            try:
                pkg = json.loads((repo_path / "package.json").read_text())
                deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
                if "react" in deps:
                    indicators.append("React")
                if "next" in deps:
                    indicators.append("Next.js")
                if "vue" in deps:
                    indicators.append("Vue")
                if "vite" in deps:
                    indicators.append("Vite")
                if "express" in deps:
                    indicators.append("Express")
            except Exception:
                pass
        if (repo_path / "requirements.txt").exists() or (repo_path / "pyproject.toml").exists() or list(repo_path.glob("*.py")):
            indicators.append("Python")
            if (repo_path / "requirements.txt").exists():
                reqs = (repo_path / "requirements.txt").read_text(errors="ignore").lower()
                if "fastapi" in reqs:
                    indicators.append("FastAPI")
                if "flask" in reqs:
                    indicators.append("Flask")
                if "django" in reqs:
                    indicators.append("Django")
                if "torch" in reqs or "tensorflow" in reqs:
                    indicators.append("AI/ML")
        if (repo_path / "Cargo.toml").exists():
            indicators.append("Rust")
        if (repo_path / "go.mod").exists():
            indicators.append("Go")
        if (repo_path / "Dockerfile").exists() or (repo_path / "docker-compose.yml").exists():
            indicators.append("Docker")

        return ", ".join(indicators) if indicators else "General / Scripts"

    @classmethod
    def get_all_projects_overview(cls) -> str:
        """Returns a formatted list of all repositories, their branches, tech stack, and last commits."""
        if not PROJECTS_ROOT.exists():
            return "No projects directory found at " + str(PROJECTS_ROOT)

        active = Path(MemoryManager.get_active_workspace()).name
        lines = [f"📂 *Your GitHub & Local Repositories* (`{PROJECTS_ROOT}`):\n"]

        for d in sorted(PROJECTS_ROOT.iterdir()):
            if d.is_dir() and not d.name.startswith("."):
                is_active = " 🌟 *(Active)*" if d.name == active else ""
                stack = cls.detect_tech_stack(d)
                
                git_info = ""
                if (d / ".git").exists():
                    try:
                        branch = subprocess.check_output(
                            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                            cwd=str(d), stderr=subprocess.DEVNULL, text=True
                        ).strip()
                        commit_time = subprocess.check_output(
                            ["git", "log", "-1", "--format=%cr"],
                            cwd=str(d), stderr=subprocess.DEVNULL, text=True
                        ).strip()
                        git_info = f" | `{branch}` ({commit_time})"
                    except Exception:
                        pass

                lines.append(f"• `{d.name}`{is_active} — _{stack}_{git_info}")

        return "\n".join(lines)
