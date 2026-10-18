import json
import re
from typing import Dict, Any, Optional
import ollama
from config import DISPATCHER_MODEL
from core.memory import MemoryManager
from core.workspace_manager import WorkspaceManager
from core.agy_runner import AntigravityRunner
from core.pdf_compiler import PDFCompiler

SYSTEM_ROUTER_PROMPT = """You are an intelligent triage agent for a personal Linux assistant.
The user is messaging you from WhatsApp.
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
        projects_list = ", ".join(WorkspaceManager.list_available_projects())
        active_ws = MemoryManager.get_active_workspace()

        # Check for direct explicit commands first for instant speed
        text_lower = user_text.strip().lower()
        if text_lower in ["projects", "list projects", "ls projects"]:
            available = "\n".join(f"• `{p}`" for p in WorkspaceManager.list_available_projects())
            current = WorkspaceManager.get_current_workspace_info()
            return {"type": "text", "text": f"{current}\n\n📁 **Available Projects:**\n{available}"}

        if text_lower.startswith("switch to ") or text_lower.startswith("cd "):
            target = text_lower.replace("switch to ", "").replace("cd ", "").strip()
            success, msg = WorkspaceManager.switch_workspace(target)
            return {"type": "text", "text": msg}

        if text_lower in ["status", "workspace", "pwd"]:
            return {"type": "text", "text": WorkspaceManager.get_current_workspace_info()}

        # Intent classification via local Ollama
        system_prompt = (
            SYSTEM_ROUTER_PROMPT
            .replace("{projects_list}", projects_list)
            .replace("{active_workspace}", active_ws)
        )

        # Fetch recent conversation context for multi-turn intent resolution
        recent_history = MemoryManager.get_recent_history(limit=4)
        messages = [{"role": "system", "content": system_prompt}]
        for turn in recent_history:
            messages.append({"role": turn["role"], "content": turn["content"]})
        messages.append({"role": "user", "content": user_text})

        try:
            res = ollama.chat(
                model=DISPATCHER_MODEL,
                format="json",
                messages=messages,
                options={"temperature": 0.1}
            )
            raw_output = res['message']['content'].strip()
            intent = json.loads(raw_output)
            if not isinstance(intent, dict):
                intent = {"action": "CHAT", "reply": str(intent)}
        except Exception as e:
            print(f"[Dispatcher] Intent parsing error ({e}), defaulting to CHAT: {raw_output if 'raw_output' in locals() else ''}")
            intent = {"action": "CHAT", "reply": ""}

        action = intent.get("action", "CHAT")

        # 1. SWITCH WORKSPACE
        if action == "SWITCH_WORKSPACE":
            target = intent.get("target", "").strip()
            if not target:
                return {"type": "text", "text": WorkspaceManager.get_current_workspace_info()}
            success, msg = WorkspaceManager.switch_workspace(target)
            return {"type": "text", "text": msg}

        # 2. CREATE ASSIGNMENT & COMPILE PDF
        elif action == "ASSIGNMENT_CREATE":
            title = intent.get("title", "Academic Assignment")
            topic = intent.get("topic", user_text)

            if status_updater:
                status_updater(f"✍️ Researching and writing assignment: *{title}*...")

            # Generate deep assignment markdown using the model
            doc_prompt = f"""You are an expert academic tutor and researcher. Write a comprehensive, thorough academic assignment/paper.
Title: {title}
Requirements: {topic}

Guidelines:
- Use clear markdown formatting with headers (# and ##).
- Include an Introduction, Core Concepts/Theory, Detailed Explanations, Practical Examples/Code (if technical), Analysis, and Conclusion.
- Use bullet points and bold keywords for readability.
- Write in academic, professional tone."""

            doc_res = ollama.chat(
                model=DISPATCHER_MODEL,
                messages=[{"role": "user", "content": doc_prompt}],
                options={"temperature": 0.4}
            )
            markdown_content = doc_res['message']['content'].strip()

            if status_updater:
                status_updater("📄 Compiling PDF document with styling...")

            pdf_path = PDFCompiler.compile_markdown_to_pdf(
                title=title, 
                markdown_text=markdown_content,
                filename_prefix=title
            )

            # Save in memory
            MemoryManager.save_assignment(
                title=title,
                prompt=user_text,
                markdown_content=markdown_content,
                pdf_path=pdf_path,
                version=1
            )

            return {
                "type": "file",
                "filePath": pdf_path,
                "fileName": f"{title.replace(' ', '_')}.pdf",
                "caption": f"✅ Completed assignment: *{title}*\nAttached PDF compiled and delivered."
            }

        # 3. REVISE ASSIGNMENT & COMPILE UPDATED PDF
        elif action == "ASSIGNMENT_REVISE":
            latest = MemoryManager.get_latest_assignment()
            if not latest:
                return {"type": "text", "text": "I don't have a previous assignment in memory to revise. Would you like me to create a new one?"}

            changes = intent.get("changes", user_text)
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

            rev_res = ollama.chat(
                model=DISPATCHER_MODEL,
                messages=[{"role": "user", "content": revise_prompt}],
                options={"temperature": 0.3}
            )
            revised_markdown = rev_res['message']['content'].strip()

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

            return {
                "type": "file",
                "filePath": new_pdf_path,
                "fileName": f"{latest.title.replace(' ', '_')}_v{new_version}.pdf",
                "caption": f"✅ Updated *{latest.title}* to version {new_version}.\nChanges applied."
            }

        # 4. ANTIGRAVITY TASK (Code editing, debugging, terminal, browser)
        elif action == "ANTIGRAVITY":
            task_prompt = intent.get("task", user_text)
            active_path = MemoryManager.get_active_workspace()

            if status_updater:
                status_updater(f"🤖 Antigravity CLI dispatched in `{active_path}`...")

            output = await AntigravityRunner.run_prompt(
                prompt=task_prompt,
                workspace_dir=active_path,
                timeout=300
            )
            return {"type": "text", "text": output}

        # 5. CHAT (Direct conversational answer)
        else:
            reply = intent.get("reply", "")
            if not reply:
                # Fallback to direct chat with recent history
                history = MemoryManager.get_recent_history(limit=4)
                chat_messages = [{"role": "system", "content": "You are a helpful personal assistant on WhatsApp. Answer concisely."}]
                chat_messages.extend(history)
                chat_messages.append({"role": "user", "content": user_text})
                chat_res = ollama.chat(model=DISPATCHER_MODEL, messages=chat_messages)
                reply = chat_res['message']['content'].strip()

            return {"type": "text", "text": reply}
