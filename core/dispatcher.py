import json
import re
import time
import asyncio
from pathlib import Path
from typing import Dict, Any, Optional
import ollama
from config import DISPATCHER_MODEL
from core.memory import MemoryManager
from core.workspace_manager import WorkspaceManager
from core.agy_runner import AntigravityRunner
from core.pdf_compiler import PDFCompiler
from core.logger import get_logger
from core.debug_router import DebugRouter, is_debug_verbose
from core.file_detector import FileDetector

logger = get_logger("dispatcher")

SYSTEM_ROUTER_PROMPT = """You are an intelligent triage agent for a personal Linux assistant.
The user is messaging you from Telegram.
Available projects on this computer: {projects_list}
Active workspace: {active_workspace}

Classify the user's message into one of these action types:
1. "SWITCH_WORKSPACE": User wants to switch to or ask about a repository/project.
   Output format: {"action": "SWITCH_WORKSPACE", "target": "<project_name or empty if asking>"}
2. "ASSIGNMENT_CREATE": User wants an assignment, report, essay, paper, or homework completed with a PDF document.
   Output format: {"action": "ASSIGNMENT_CREATE", "title": "<short title>", "topic": "<detailed topic description>"}
3. "ASSIGNMENT_REVISE": User wants to edit, update, or revise an existing assignment or PDF previously generated.
   Output format: {"action": "ASSIGNMENT_REVISE", "changes": "<description of requested changes>"}
4. "ANTIGRAVITY": User asks to fix code, debug, edit files, run tests, run bash commands, do git operations, or browser tasks on their computer.
   Output format: {"action": "ANTIGRAVITY", "task": "<clear instruction for the developer agent>"}
5. "CHAT": Casual conversation, quick questions, or general discussion not needing file edits or assignments.
   Output format: {"action": "CHAT", "reply": "<direct conversational reply>"}

Respond ONLY with a valid JSON object matching one of the schemas above. No preamble, no markdown fences."""

from core.triage import FastTriage
from core.context_engine import ContextEngine
from core.memory_agent import MemoryAgent

class Dispatcher:
    @classmethod
    async def process_user_input(
        cls, 
        user_text: str, 
        sender_jid: str,
        status_updater: Optional[Any] = None
    ) -> Dict[str, Any]:
        """
        Main entry point for processing incoming user input.
        Returns a dict:
        - {"type": "text", "text": "..."}
        - {"type": "file", "filePath": "...", "fileName": "...", "caption": "..."}
        """
        pipeline_start = time.perf_counter()

        # 0. Intercept Debug Commands immediately (< 1ms)
        if DebugRouter.is_debug_command(user_text):
            return await DebugRouter.handle_debug_command(user_text, sender_jid)

        # 1. Tier 0: Fast-Path Rule & Regex Triage (< 1ms)
        fast_match = FastTriage.match_fast_path(user_text)
        if fast_match:
            action = fast_match.get("action")
            if action in ["FAST_CHAT", "DIRECT_REPLY"]:
                res_dict = {"type": "text", "text": fast_match.get("reply", "")}
                return cls._format_result(res_dict, action, pipeline_start)
            elif action == "ANTIGRAVITY":
                return await cls._execute_antigravity(fast_match.get("task", user_text), sender_jid, status_updater, pipeline_start)
            elif action == "ASSIGNMENT_CREATE":
                return await cls._execute_assignment_create(
                    fast_match.get("title", "Academic Assignment"),
                    fast_match.get("topic", user_text),
                    user_text,
                    status_updater,
                    pipeline_start
                )
            elif action == "ASSIGNMENT_REVISE":
                return await cls._execute_assignment_revise(
                    fast_match.get("changes", user_text),
                    user_text,
                    status_updater,
                    pipeline_start
                )
            elif action == "DOCUMENT_FETCH":
                return await cls._execute_document_fetch(
                    fast_match.get("target"),
                    fast_match.get("query", user_text),
                    sender_jid,
                    pipeline_start
                )

        # 2. Tier 1: Micro-Classifier for Ambiguous Requests
        intent_cat = await FastTriage.classify_ambiguous(user_text)
        print(f"[Dispatcher] Tier-1 Triage classified '{user_text[:40]}' -> {intent_cat}")

        if intent_cat == "ANTIGRAVITY":
            return await cls._execute_antigravity(user_text, sender_jid, status_updater, pipeline_start)
        elif intent_cat == "ASSIGNMENT_CREATE":
            return await cls._execute_assignment_create("Academic Assignment", user_text, user_text, status_updater, pipeline_start)
        elif intent_cat == "SWITCH_WORKSPACE":
            return cls._format_result({"type": "text", "text": WorkspaceManager.get_current_workspace_info()}, "WORKSPACE", pipeline_start)

        # 3. Default: Grounded Single-Pass Conversational Chat
        return await cls._execute_single_pass_chat(user_text, sender_jid, pipeline_start)

    @classmethod
    async def _execute_antigravity(
        cls, 
        task_prompt: str, 
        sender_jid: str,
        status_updater: Optional[Any], 
        pipeline_start: float
    ) -> Dict[str, Any]:
        active_path = MemoryManager.get_active_workspace()
        
        # Check if user explicitly asked for a fresh/new conversation
        is_explicit_new = bool(re.search(
            r"^(?:new\s+(?:chat|session|task|conversation)|start\s+fresh|fresh\s+chat)\b", 
            task_prompt.strip(), 
            re.IGNORECASE
        ))

        # Check if we should continue an existing AGY conversation in this workspace
        has_existing_agy = MemoryManager.get_session_agy_state(sender_jid, active_path)
        is_continuation = has_existing_agy and not is_explicit_new

        if is_explicit_new:
            MemoryManager.reset_session_agy_state(sender_jid)
            task_prompt = re.sub(
                r"^(?:new\s+(?:chat|session|task|conversation)|start\s+fresh|fresh\s+chat)[:\s,]*", 
                "", 
                task_prompt, 
                flags=re.IGNORECASE
            ).strip()

        # Resolve ambiguous pronouns and follow-ups with dedicated MemoryAgent
        resolved_ctx = await MemoryAgent.resolve_context(task_prompt, sender_jid, active_path)
        base_prompt = resolved_ctx.resolved_prompt

        # Synthesize into high-signal instruction (concise, 1-2 sentences)
        if status_updater:
            status_updater("🧠 Refining task instruction...")

        synthesized_prompt = await ContextEngine.synthesize_antigravity_task(
            prompt=base_prompt,
            sender_jid=sender_jid,
            workspace_path=active_path,
            is_continuation=is_continuation
        )

        can_gui, _ = AntigravityRunner.can_spawn_terminal()
        mode_note = " (🖥️ terminal opened on your screen)" if can_gui else ""
        cont_note = " (continuing chat)" if is_continuation else ""
        if status_updater:
            status_updater(f"🤖 Antigravity CLI dispatched in `{active_path}`{cont_note}{mode_note}...")

        # Snapshot documents before Antigravity executes
        before_docs = FileDetector.snapshot_documents(active_path)
        agy_start_time = time.time()

        output = await AntigravityRunner.run_prompt(
            prompt=synthesized_prompt,
            workspace_dir=active_path,
            timeout=300,
            continue_session=is_continuation,
            status_callback=status_updater
        )

        # Mark that Antigravity has executed for this session in this workspace
        MemoryManager.mark_session_agy_used(sender_jid, active_path)

        # Identify newly created, modified, or requested documents (.pdf, .docx)
        detected_docs = FileDetector.identify_documents(
            workspace_dir=active_path,
            before_snapshot=before_docs,
            start_time=agy_start_time,
            prompt=task_prompt,
            output_text=output
        )

        res_payload: Dict[str, Any] = {"type": "text", "text": output}
        if detected_docs:
            doc_names = ", ".join(f"`{d.name}`" for d in detected_docs)
            logger.info(f"Antigravity generated documents detected: {doc_names}")
            if status_updater:
                status_updater(f"📄 Identified document: {detected_docs[0].name}, sending to Telegram...")
            res_payload["files"] = [
                {
                    "filePath": str(d),
                    "fileName": d.name,
                    "caption": f"📄 Delivered: `{d.name}`"
                }
                for d in detected_docs
            ]

        return cls._format_result(res_payload, "ANTIGRAVITY", pipeline_start)

    @classmethod
    async def _execute_document_fetch(
        cls, 
        target: Optional[str], 
        query: str, 
        sender_jid: str, 
        pipeline_start: float
    ) -> Dict[str, Any]:
        active_path = MemoryManager.get_active_workspace()
        doc = FileDetector.find_requested_document(active_path, target or query)
        if doc and doc.exists():
            return cls._format_result({
                "type": "file",
                "filePath": str(doc),
                "fileName": doc.name,
                "caption": f"📄 Here is `{doc.name}` from `{Path(active_path).name}`."
            }, "DOCUMENT_FETCH", pipeline_start)
        else:
            return cls._format_result({
                "type": "text",
                "text": f"⚠️ Could not find a matching `.pdf` or `.docx` file in `{active_path}`. Would you like me to generate one?"
            }, "DOCUMENT_FETCH", pipeline_start)

    @classmethod
    async def _execute_assignment_create(
        cls, 
        title: str, 
        topic: str, 
        user_text: str, 
        status_updater: Optional[Any], 
        pipeline_start: float
    ) -> Dict[str, Any]:
        if status_updater:
            status_updater(f"✍️ Researching and writing assignment: *{title}*...")

        doc_prompt = f"""You are an expert academic tutor and researcher. Write a comprehensive, thorough academic assignment/paper.
Title: {title}
Requirements: {topic}

Guidelines:
- Use clear markdown formatting with headers (# and ##).
- Include an Introduction, Core Concepts/Theory, Detailed Explanations, Practical Examples/Code (if technical), Analysis, and Conclusion.
- Use bullet points and bold keywords for readability.
- Write in academic, professional tone."""

        print(f"[Dispatcher] Writing assignment: {title}")
        doc_res = await asyncio.to_thread(
            ollama.chat,
            model=DISPATCHER_MODEL,
            messages=[{"role": "user", "content": doc_prompt}],
            options={"temperature": 0.4, "num_predict": 1024, "num_ctx": 4096}
        )
        msg_obj = doc_res.get('message', {})
        markdown_content = (msg_obj.get('content') or getattr(msg_obj, 'content', '') or '').strip()
        if not markdown_content:
            thinking = getattr(msg_obj, 'thinking', None) or (msg_obj.get('thinking') if isinstance(msg_obj, dict) else None)
            if thinking:
                markdown_content = str(thinking).strip()

        if status_updater:
            status_updater("📄 Compiling PDF document with styling...")

        pdf_path = PDFCompiler.compile_markdown_to_pdf(
            title=title, 
            markdown_text=markdown_content,
            filename_prefix=title
        )

        MemoryManager.save_assignment(
            title=title,
            prompt=user_text,
            markdown_content=markdown_content,
            pdf_path=pdf_path,
            version=1
        )

        res_dict = {
            "type": "file",
            "filePath": pdf_path,
            "fileName": f"{title.replace(' ', '_')}.pdf",
            "caption": f"✅ Completed assignment: *{title}*\nAttached PDF compiled and delivered."
        }
        return cls._format_result(res_dict, "ASSIGNMENT_CREATE", pipeline_start)

    @classmethod
    async def _execute_assignment_revise(
        cls, 
        changes: str, 
        user_text: str, 
        status_updater: Optional[Any], 
        pipeline_start: float
    ) -> Dict[str, Any]:
        latest = MemoryManager.get_latest_assignment()
        if not latest:
            return {"type": "text", "text": "I don't have a previous assignment in memory to revise. Would you like me to create a new one?"}

        if status_updater:
            status_updater(f"📝 Applying revisions to *{latest.title}* (v{latest.version + 1})...")

        revise_prompt = f"""You are revising an existing academic assignment.
Original Title: {latest.title}

Current Content:
{latest.markdown_content}

Requested Changes:
{changes}

Instructions:
Apply the requested changes to the content. Maintain the overall structure and academic quality.
Output the complete revised markdown text."""

        print(f"[Dispatcher] Revising assignment: {latest.title}")
        rev_res = await asyncio.to_thread(
            ollama.chat,
            model=DISPATCHER_MODEL,
            messages=[{"role": "user", "content": revise_prompt}],
            options={"temperature": 0.3, "num_predict": 1024, "num_ctx": 4096}
        )
        msg_obj = rev_res.get('message', {})
        revised_markdown = (msg_obj.get('content') or getattr(msg_obj, 'content', '') or '').strip()
        if not revised_markdown:
            thinking = getattr(msg_obj, 'thinking', None) or (msg_obj.get('thinking') if isinstance(msg_obj, dict) else None)
            if thinking:
                revised_markdown = str(thinking).strip()

        new_version = latest.version + 1
        new_pdf_path = PDFCompiler.compile_markdown_to_pdf(
            title=f"{latest.title} (v{new_version})",
            markdown_text=revised_markdown,
            filename_prefix=f"{latest.title}_v{new_version}"
        )

        MemoryManager.save_assignment(
            title=latest.title,
            prompt=user_text,
            markdown_content=revised_markdown,
            pdf_path=new_pdf_path,
            version=new_version
        )

        res_dict = {
            "type": "file",
            "filePath": new_pdf_path,
            "fileName": f"{latest.title.replace(' ', '_')}_v{new_version}.pdf",
            "caption": f"✅ Updated *{latest.title}* to version {new_version}.\nChanges applied."
        }
        return cls._format_result(res_dict, "ASSIGNMENT_REVISE", pipeline_start)

    @classmethod
    async def _execute_single_pass_chat(
        cls, 
        user_text: str, 
        sender_jid: str,
        pipeline_start: float
    ) -> Dict[str, Any]:
        """Grounded single-pass chat completion with developer persona, active session history, and project context."""
        history = MemoryManager.get_active_session_history(sender_jid, limit=6, exclude_last_if_current=True)
        grounded_system_prompt = ContextEngine.build_system_prompt(sender_jid)
        chat_messages = [
            {"role": "system", "content": grounded_system_prompt}
        ]
        chat_messages.extend(history)
        chat_messages.append({"role": "user", "content": user_text})

        chat_res = await asyncio.to_thread(
            ollama.chat,
            model=DISPATCHER_MODEL,
            messages=chat_messages,
            options={
                "temperature": 0.4,
                "num_predict": 768,
                "num_ctx": 4096
            }
        )
        msg_obj = chat_res.get('message', {})
        reply = (msg_obj.get('content') or getattr(msg_obj, 'content', '') or '').strip()
        if not reply:
            thinking = getattr(msg_obj, 'thinking', None) or (msg_obj.get('thinking') if isinstance(msg_obj, dict) else None)
            if thinking:
                reply = str(thinking).strip()
        return cls._format_result({"type": "text", "text": reply}, "CHAT", pipeline_start)

    @classmethod
    def _format_result(cls, result: Dict[str, Any], action: str, start_time: float) -> Dict[str, Any]:
        """Appends latency and debug metadata if debug verbose mode is on."""
        if not is_debug_verbose():
            return result
        duration = time.perf_counter() - start_time
        footer = f"\n\n_⏱️ {duration:.2f}s | Action: {action} | Model: {DISPATCHER_MODEL}_"
        if result.get("type") == "text":
            result["text"] = result.get("text", "") + footer
        elif result.get("type") == "file":
            result["caption"] = result.get("caption", "") + footer
        return result
