import os
import re
import time
from pathlib import Path
from typing import Dict, List, Optional, Set
from config import DATA_DIR
from core.logger import get_logger

logger = get_logger("file_detector")

IGNORED_DIRS: Set[str] = {
    ".git", ".venv", "venv", "node_modules", "__pycache__", 
    ".gemini", ".cache", ".pytest_cache", ".idea", ".vscode", 
    "site-packages", ".next", ".nuxt", "dist-types"
}

DOCUMENT_EXTENSIONS: Set[str] = {".pdf", ".docx", ".doc"}

RE_DOC_REF = re.compile(
    r"""(?:file://)?([a-zA-Z0-9_\-\.~/]+?\.(?:pdf|docx|doc))\b""",
    re.IGNORECASE
)

RE_DOCUMENT_FETCH = re.compile(
    r"^(?:(?:can\s+you\s+|could\s+you\s+|please\s+)?(?:send|give|return|get|upload|share)\s+(?:me\s+)?(?:the\s+|that\s+|this\s+|latest\s+)*(?:([a-zA-Z0-9_\-\.]+\.(?:pdf|docx|doc))|(?:pdf|docx|document|doc|paper)))\b",
    re.IGNORECASE
)

MAX_UPLOAD_SIZE = 50 * 1024 * 1024  # 50 MB limit for Telegram bot uploads


class FileDetector:
    """Detects, tracks, and extracts generated or requested documents (.pdf, .docx)."""

    @classmethod
    def scan_documents(cls, root_dir: str, max_depth: int = 4) -> Dict[str, float]:
        """
        Scans a directory for .pdf and .docx files, returning {abs_path_str: mtime}.
        Prunes ignored directories (.git, node_modules, etc.) for high performance (< 2ms).
        """
        results: Dict[str, float] = {}
        root = Path(root_dir).resolve()
        if not root.exists() or not root.is_dir():
            return results

        try:
            for current_root, dirs, files in os.walk(root):
                # Prune ignored and hidden directories in-place
                dirs[:] = [d for d in dirs if d not in IGNORED_DIRS and not d.startswith(".")]

                # Check depth
                try:
                    rel_depth = len(Path(current_root).relative_to(root).parts)
                    if rel_depth > max_depth:
                        dirs.clear()
                        continue
                except Exception:
                    pass

                for f in files:
                    ext = Path(f).suffix.lower()
                    if ext in DOCUMENT_EXTENSIONS:
                        full_p = Path(current_root) / f
                        try:
                            st = full_p.stat()
                            if 0 < st.st_size <= MAX_UPLOAD_SIZE:
                                results[str(full_p)] = st.st_mtime
                        except Exception:
                            pass
        except Exception as e:
            logger.warning(f"Error scanning documents in {root}: {e}")

        return results

    @classmethod
    def snapshot_documents(cls, workspace_dir: str) -> Dict[str, float]:
        """Snapshots all documents in the active workspace and data directories."""
        snapshot = cls.scan_documents(workspace_dir)

        # Also snapshot data/artifacts and data/assignments if they exist
        for sub in ["artifacts", "assignments"]:
            p = DATA_DIR / sub
            if p.exists() and p.is_dir():
                snapshot.update(cls.scan_documents(str(p)))

        return snapshot

    @classmethod
    def extract_document_paths_from_text(cls, text: str, workspace_dir: str) -> List[Path]:
        """Extracts and verifies any .pdf or .docx paths mentioned in model / runner output text."""
        if not text:
            return []

        found_paths: List[Path] = []
        seen: Set[str] = set()

        matches = RE_DOC_REF.findall(text)
        for match in matches:
            cleaned = match.strip("`'\"()[] ")
            if cleaned.lower().startswith("file://"):
                cleaned = cleaned[7:]

            candidates: List[Path] = []
            try:
                p = Path(cleaned).expanduser()
                if p.is_absolute():
                    candidates.append(p)
                else:
                    candidates.append((Path(workspace_dir) / cleaned).resolve())
                    candidates.append((DATA_DIR / "assignments" / cleaned).resolve())
                    candidates.append((DATA_DIR / "artifacts" / cleaned).resolve())
                    candidates.append((Path.home() / "Downloads" / cleaned).resolve())
                    candidates.append((Path("/tmp") / cleaned).resolve())
            except Exception:
                continue

            for cand in candidates:
                cand_str = str(cand)
                if cand_str not in seen and cand.exists() and cand.is_file():
                    try:
                        if 0 < cand.stat().st_size <= MAX_UPLOAD_SIZE:
                            seen.add(cand_str)
                            found_paths.append(cand)
                            break
                    except Exception:
                        pass

        return found_paths

    @classmethod
    def identify_documents(
        cls,
        workspace_dir: str,
        before_snapshot: Dict[str, float],
        start_time: float,
        prompt: str = "",
        output_text: str = ""
    ) -> List[Path]:
        """
        Identifies documents (.pdf, .docx) created, modified, or requested during a task execution.
        """
        after_snapshot = cls.snapshot_documents(workspace_dir)
        detected_paths: List[Path] = []
        seen: Set[str] = set()

        # 1. Check for newly created or modified files
        for path_str, mtime in after_snapshot.items():
            if path_str not in before_snapshot or mtime >= start_time - 1.0:
                p = Path(path_str)
                if path_str not in seen and p.exists() and p.is_file():
                    seen.add(path_str)
                    detected_paths.append(p)

        # 2. Check for file paths explicitly mentioned in the agent output
        text_paths = cls.extract_document_paths_from_text(output_text, workspace_dir)
        for tp in text_paths:
            tp_str = str(tp)
            if tp_str not in seen:
                seen.add(tp_str)
                detected_paths.append(tp)

        # 3. Check user prompt preferences (pdf vs docx)
        prompt_lower = prompt.lower()
        wants_pdf = "pdf" in prompt_lower
        wants_docx = "docx" in prompt_lower or "doc" in prompt_lower

        if wants_pdf and not wants_docx:
            pdf_only = [p for p in detected_paths if p.suffix.lower() == ".pdf"]
            if pdf_only:
                detected_paths = pdf_only
        elif wants_docx and not wants_pdf:
            docx_only = [p for p in detected_paths if p.suffix.lower() in [".docx", ".doc"]]
            if docx_only:
                detected_paths = docx_only

        # 4. Fallback: If no new file detected but user explicitly asked to return/send pdf/docx
        if not detected_paths and (wants_pdf or wants_docx):
            recent = cls.find_recent_documents(
                workspace_dir=workspace_dir,
                extension_filter=".pdf" if wants_pdf and not wants_docx else (".docx" if wants_docx and not wants_pdf else None),
                limit=1
            )
            if recent:
                detected_paths.extend(recent)

        # Sort detected files by mtime descending (newest first)
        detected_paths.sort(key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True)
        return detected_paths[:5]

    @classmethod
    def find_recent_documents(
        cls, 
        workspace_dir: str, 
        extension_filter: Optional[str] = None, 
        limit: int = 3
    ) -> List[Path]:
        """Finds the most recently modified documents in the workspace and data directories."""
        all_docs = cls.snapshot_documents(workspace_dir)
        candidates: List[Path] = []

        for path_str, _ in all_docs.items():
            p = Path(path_str)
            if extension_filter:
                if p.suffix.lower() == extension_filter.lower():
                    candidates.append(p)
            else:
                candidates.append(p)

        candidates.sort(key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True)
        return candidates[:limit]

    @classmethod
    def find_requested_document(cls, workspace_dir: str, query: str) -> Optional[Path]:
        """Finds a specific document requested by the user, by name or latest type."""
        # 1. Check if a specific filename was requested (e.g. 'summary.pdf')
        filename_match = re.search(r"([a-zA-Z0-9_\-\.]+\.(?:pdf|docx|doc))\b", query, re.IGNORECASE)
        if filename_match:
            target_name = filename_match.group(1).lower()
            all_docs = cls.snapshot_documents(workspace_dir)
            for path_str in all_docs:
                p = Path(path_str)
                if p.name.lower() == target_name:
                    return p

        # 2. Generic request (e.g. 'the pdf', 'the docx')
        q_lower = query.lower()
        ext_filter = None
        if "pdf" in q_lower and "docx" not in q_lower:
            ext_filter = ".pdf"
        elif "docx" in q_lower or "doc" in q_lower:
            ext_filter = ".docx"

        recent = cls.find_recent_documents(workspace_dir, extension_filter=ext_filter, limit=1)
        if recent:
            return recent[0]

        return None
