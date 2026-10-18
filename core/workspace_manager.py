import os
import subprocess
from pathlib import Path
from typing import List, Optional, Tuple
from config import PROJECTS_ROOT
from core.memory import MemoryManager

import time

class WorkspaceManager:
    _cached_projects: List[str] = []
    _cache_time: float = 0.0
    _CACHE_TTL: float = 30.0

    @classmethod
    def list_available_projects(cls) -> List[str]:
        now = time.time()
        if cls._cached_projects and (now - cls._cache_time < cls._CACHE_TTL):
            return cls._cached_projects

        if not PROJECTS_ROOT.exists():
            return []
        projects = []
        for item in PROJECTS_ROOT.iterdir():
            if item.is_dir() and not item.name.startswith("."):
                projects.append(item.name)
        cls._cached_projects = sorted(projects)
        cls._cache_time = now
        return cls._cached_projects

    @classmethod
    def resolve_project_path(cls, query: str) -> Optional[Path]:
        query_clean = query.strip().lower()
        projects = cls.list_available_projects()

        # 1. Exact match
        for p in projects:
            if p.lower() == query_clean:
                return PROJECTS_ROOT / p

        # 2. Substring match
        for p in projects:
            if query_clean in p.lower() or p.lower() in query_clean:
                return PROJECTS_ROOT / p

        # 3. Normalized match (remove hyphens and underscores)
        norm_query = query_clean.replace("-", "").replace("_", "")
        for p in projects:
            norm_p = p.lower().replace("-", "").replace("_", "")
            if norm_query in norm_p or norm_p in norm_query:
                return PROJECTS_ROOT / p

        return None

    @classmethod
    def switch_workspace(cls, target_name_or_query: str) -> Tuple[bool, str]:
        path = cls.resolve_project_path(target_name_or_query)
        if path and path.exists():
            MemoryManager.set_active_workspace(str(path))
            return True, f"Switched active workspace to: `{path.name}` ({path})"
        
        available = ", ".join(f"`{p}`" for p in cls.list_available_projects())
        return False, f"Could not find project matching '{target_name_or_query}'. Available projects: {available}"

    @classmethod
    def get_current_workspace_info(cls) -> str:
        current_path_str = MemoryManager.get_active_workspace()
        path = Path(current_path_str)
        if not path.exists():
            return f"Active workspace is set to {path}, but the directory does not exist."

        info_lines = [f"📂 **Active Workspace:** `{path.name}` (`{path}`)"]
        
        # Check git branch if it's a git repo
        git_dir = path / ".git"
        if git_dir.exists():
            try:
                branch = subprocess.check_output(
                    ["git", "rev-parse", "--abbrev-ref", "HEAD"], 
                    cwd=str(path), 
                    stderr=subprocess.DEVNULL,
                    text=True
                ).strip()
                status = subprocess.check_output(
                    ["git", "status", "--short"], 
                    cwd=str(path), 
                    stderr=subprocess.DEVNULL,
                    text=True
                ).strip()
                dirty = " (Modified)" if status else " (Clean)"
                info_lines.append(f"🌿 Git Branch: `{branch}`{dirty}")
            except Exception:
                pass

        return "\n".join(info_lines)
