import json
import os
import time
import asyncio
from pathlib import Path
from typing import Dict, Any, Optional

from aiohttp import web
from config import (
    DATA_DIR,
    AUDIO_DIR,
    ARTIFACTS_DIR,
    PROJECTS_ROOT,
    WHISPER_MODEL_SIZE,
    OLLAMA_HOST
)
from core.memory import MemoryManager
from core.dispatcher import Dispatcher
from core.transcriber import VoiceTranscriber
from core.workspace_manager import WorkspaceManager
from core.agy_runner import AntigravityRunner
from core.logger import get_logger

logger = get_logger("web_api")

def cors_headers():
    return {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, POST, PATCH, DELETE, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type, Authorization"
    }

async def handle_options(request: web.Request):
    return web.Response(headers=cors_headers())

async def handle_list_sessions(request: web.Request):
    """GET /api/sessions: Lists all chat sessions."""
    sessions = MemoryManager.list_all_sessions(limit=100)
    return web.json_response({"sessions": sessions}, headers=cors_headers())

async def handle_create_session(request: web.Request):
    """POST /api/sessions: Creates a new chat session."""
    try:
        data = await request.json() if request.can_read_body else {}
    except Exception:
        data = {}
    title = data.get("title", "New Chat")
    workspace = data.get("workspace")
    sender_jid = data.get("sender_jid", "web_user")

    session_rec = MemoryManager.create_chat_session(title=title, workspace=workspace, sender_jid=sender_jid)
    return web.json_response({
        "status": "ok",
        "session": {
            "session_id": session_rec.session_id,
            "title": session_rec.title,
            "workspace": session_rec.workspace,
            "turn_count": session_rec.turn_count,
            "is_active": session_rec.is_active,
            "agy_conversation_id": session_rec.agy_conversation_id,
            "started_at": session_rec.started_at.isoformat() if session_rec.started_at else None,
            "last_activity_at": session_rec.last_activity_at.isoformat() if session_rec.last_activity_at else None,
        }
    }, headers=cors_headers())

async def handle_get_session(request: web.Request):
    """GET /api/sessions/{session_id}: Fetches session details and message history."""
    session_id = request.match_info.get("session_id")
    rec = MemoryManager.get_session_by_id(session_id)
    if not rec:
        return web.json_response({"error": "Session not found"}, status=404, headers=cors_headers())

    messages = MemoryManager.get_messages_for_session(session_id)
    return web.json_response({
        "session": {
            "session_id": rec.session_id,
            "title": rec.title,
            "workspace": rec.workspace,
            "turn_count": rec.turn_count,
            "is_active": rec.is_active,
            "agy_conversation_id": rec.agy_conversation_id,
            "started_at": rec.started_at.isoformat() if rec.started_at else None,
            "last_activity_at": rec.last_activity_at.isoformat() if rec.last_activity_at else None,
        },
        "messages": messages
    }, headers=cors_headers())

async def handle_update_session(request: web.Request):
    """PATCH /api/sessions/{session_id}: Updates session title, workspace, etc."""
    session_id = request.match_info.get("session_id")
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"error": "Invalid JSON"}, status=400, headers=cors_headers())

    title = data.get("title")
    workspace = data.get("workspace")
    agy_id = data.get("agy_conversation_id")

    rec = MemoryManager.update_chat_session(
        session_id=session_id,
        title=title,
        workspace=workspace,
        agy_conversation_id=agy_id
    )
    if not rec:
        return web.json_response({"error": "Session not found"}, status=404, headers=cors_headers())

    return web.json_response({
        "status": "ok",
        "session": {
            "session_id": rec.session_id,
            "title": rec.title,
            "workspace": rec.workspace,
            "turn_count": rec.turn_count,
            "agy_conversation_id": rec.agy_conversation_id
        }
    }, headers=cors_headers())

async def handle_delete_session(request: web.Request):
    """DELETE /api/sessions/{session_id}: Deletes session and its messages."""
    session_id = request.match_info.get("session_id")
    success = MemoryManager.delete_chat_session(session_id)
    if not success:
        return web.json_response({"error": "Session not found"}, status=404, headers=cors_headers())
    return web.json_response({"status": "deleted", "session_id": session_id}, headers=cors_headers())

async def handle_chat_message(request: web.Request):
    """POST /api/chat: Dispatches user message, saves history, returns agent response."""
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"error": "Invalid JSON"}, status=400, headers=cors_headers())

    user_text = data.get("text", "").strip()
    session_id = data.get("session_id")
    sender_jid = data.get("sender_jid", "web_user")

    if not user_text:
        return web.json_response({"error": "Missing message text"}, status=400, headers=cors_headers())

    # Ensure session exists or create one
    session_rec = None
    if session_id:
        session_rec = MemoryManager.get_session_by_id(session_id)
    if not session_rec:
        session_rec = MemoryManager.create_chat_session(
            title=user_text[:30] + ("..." if len(user_text) > 30 else ""),
            sender_jid=sender_jid
        )
        session_id = session_rec.session_id

    # Auto-title chat on first turn if it still has default title
    if session_rec.title in ("New Chat", "", None) and session_rec.turn_count == 0:
        clean_title = user_text[:35].strip()
        MemoryManager.update_chat_session(session_id, title=clean_title)

    # 1. Save user message
    user_msg_rec = MemoryManager.save_message(
        sender_jid=sender_jid,
        role="user",
        content=user_text,
        content_type="text",
        session_id=session_id,
        workspace=session_rec.workspace
    )

    # 2. Process via Dispatcher
    result = await Dispatcher.process_user_input(
        user_text=user_text,
        sender_jid=sender_jid,
        session_id=session_id
    )

    reply_text = result.get("text", "")
    content_type = "text"
    if result.get("type") == "file":
        content_type = "pdf" if result.get("fileName", "").endswith(".pdf") else "file"
        if not reply_text:
            reply_text = result.get("caption", f"Delivered file: {result.get('fileName')}")

    # 3. Save assistant message
    asst_msg_rec = MemoryManager.save_message(
        sender_jid=sender_jid,
        role="assistant",
        content=reply_text,
        content_type=content_type,
        session_id=session_id,
        workspace=session_rec.workspace
    )

    # Normalize files response for UI
    files_out = []
    if result.get("files"):
        for f in result["files"]:
            files_out.append({
                "fileName": f.get("fileName"),
                "filePath": f.get("filePath"),
                "caption": f.get("caption")
            })
    elif result.get("filePath"):
        files_out.append({
            "fileName": result.get("fileName") or Path(result["filePath"]).name,
            "filePath": result.get("filePath"),
            "caption": result.get("caption")
        })

    return web.json_response({
        "status": "ok",
        "session_id": session_id,
        "message": {
            "id": asst_msg_rec.id,
            "role": "assistant",
            "content": reply_text,
            "content_type": content_type,
            "created_at": asst_msg_rec.created_at.isoformat() if asst_msg_rec.created_at else None,
            "files": files_out
        },
        "action": result.get("action"),
        "agy_conversation_id": result.get("agy_conversation_id")
    }, headers=cors_headers())

async def handle_chat_stream(request: web.Request):
    """
    GET /api/chat/stream?session_id=...&text=...
    Server-Sent Events (SSE) streaming endpoint for real-time thoughts and updates.
    """
    session_id = request.query.get("session_id")
    user_text = request.query.get("text", "").strip()
    sender_jid = request.query.get("sender_jid", "web_user")

    if not user_text:
        return web.Response(text="Missing text parameter", status=400)

    # Ensure session exists
    session_rec = None
    if session_id:
        session_rec = MemoryManager.get_session_by_id(session_id)
    if not session_rec:
        session_rec = MemoryManager.create_chat_session(
            title=user_text[:35].strip(),
            sender_jid=sender_jid
        )
        session_id = session_rec.session_id

    response = web.StreamResponse(
        status=200,
        reason='OK',
        headers={
            'Content-Type': 'text/event-stream',
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'Access-Control-Allow-Origin': '*'
        }
    )
    await response.prepare(request)

    # 1. Save user message
    MemoryManager.save_message(
        sender_jid=sender_jid,
        role="user",
        content=user_text,
        content_type="text",
        session_id=session_id,
        workspace=session_rec.workspace
    )

    async def sse_send(event: str, data_dict: dict):
        line = f"event: {event}\ndata: {json.dumps(data_dict)}\n\n"
        await response.write(line.encode("utf-8"))

    # Status updater callback that feeds SSE
    def status_callback(msg: str):
        asyncio.create_task(sse_send("status", {"message": msg, "session_id": session_id}))

    await sse_send("start", {"session_id": session_id})

    try:
        result = await Dispatcher.process_user_input(
            user_text=user_text,
            sender_jid=sender_jid,
            status_updater=status_callback,
            session_id=session_id
        )

        reply_text = result.get("text", "")
        content_type = "text"
        if result.get("type") == "file":
            content_type = "pdf" if result.get("fileName", "").endswith(".pdf") else "file"
            if not reply_text:
                reply_text = result.get("caption", f"Delivered file: {result.get('fileName')}")

        asst_msg = MemoryManager.save_message(
            sender_jid=sender_jid,
            role="assistant",
            content=reply_text,
            content_type=content_type,
            session_id=session_id,
            workspace=session_rec.workspace
        )

        files_out = []
        if result.get("files"):
            files_out = result["files"]
        elif result.get("filePath"):
            files_out = [{"fileName": result.get("fileName"), "filePath": result.get("filePath")}]

        await sse_send("result", {
            "session_id": session_id,
            "message": {
                "id": asst_msg.id,
                "role": "assistant",
                "content": reply_text,
                "content_type": content_type,
                "created_at": asst_msg.created_at.isoformat() if asst_msg.created_at else None,
                "files": files_out
            },
            "action": result.get("action"),
            "agy_conversation_id": result.get("agy_conversation_id")
        })
    except Exception as e:
        logger.error(f"Error in chat stream: {e}", exc_info=True)
        await sse_send("error", {"error": str(e)})
    finally:
        await sse_send("done", {"session_id": session_id})
        await response.write_eof()

    return response

async def handle_audio_transcribe(request: web.Request):
    """POST /api/audio/transcribe: Accepts multipart audio file and runs Whisper STT."""
    try:
        reader = await request.multipart()
        audio_bytes = bytearray()
        filename = f"web_voice_{int(time.time() * 1000)}.webm"

        while True:
            part = await reader.next()
            if part is None:
                break
            if part.name == "audio" or part.filename:
                if part.filename:
                    ext = Path(part.filename).suffix or ".webm"
                    filename = f"web_voice_{int(time.time() * 1000)}{ext}"
                while True:
                    chunk = await part.read_chunk()
                    if not chunk:
                        break
                    audio_bytes.extend(chunk)

        if not audio_bytes:
            return web.json_response({"error": "No audio content provided"}, status=400, headers=cors_headers())

        audio_dest = AUDIO_DIR / filename
        with open(audio_dest, "wb") as f:
            f.write(audio_bytes)

        logger.info(f"Received audio recording ({len(audio_bytes)} bytes), transcribing with Whisper...")
        transcription = await asyncio.to_thread(VoiceTranscriber.transcribe, str(audio_dest))
        logger.info(f"Transcribed audio: '{transcription}'")

        return web.json_response({
            "status": "ok",
            "text": transcription.strip(),
            "filename": filename
        }, headers=cors_headers())
    except Exception as e:
        logger.error(f"Failed audio transcription: {e}", exc_info=True)
        return web.json_response({"error": str(e)}, status=500, headers=cors_headers())

async def handle_list_workspaces(request: web.Request):
    """GET /api/workspaces: Lists available project directories and current active workspace."""
    available = WorkspaceManager.list_available_projects()
    active = MemoryManager.get_active_workspace()
    return web.json_response({
        "active": active,
        "active_name": Path(active).name,
        "available": [
            {
                "name": p,
                "path": str(PROJECTS_ROOT / p)
            }
            for p in available
        ]
    }, headers=cors_headers())

async def handle_select_workspace(request: web.Request):
    """POST /api/workspaces/select: Sets the global active workspace."""
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"error": "Invalid JSON"}, status=400, headers=cors_headers())

    target = data.get("workspace", "").strip()
    if not target:
        return web.json_response({"error": "Missing workspace target"}, status=400, headers=cors_headers())

    success, msg = WorkspaceManager.switch_workspace(target)
    if not success:
        return web.json_response({"error": msg}, status=404, headers=cors_headers())

    return web.json_response({
        "status": "ok",
        "message": msg,
        "active": MemoryManager.get_active_workspace(),
        "active_name": Path(MemoryManager.get_active_workspace()).name
    }, headers=cors_headers())

async def handle_download_file(request: web.Request):
    """GET /api/files/download?path=...: Serves generated files (PDFs, artifacts) securely."""
    fpath_str = request.query.get("path", "").strip()
    if not fpath_str:
        return web.Response(text="Missing path query param", status=400)

    fpath = Path(fpath_str).resolve()
    # Security: ensure file exists and is within safe boundaries
    if not fpath.exists() or not fpath.is_file():
        return web.Response(text="File not found", status=404)

    return web.FileResponse(fpath, headers=cors_headers())

def register_web_routes(app: web.Application):
    """Registers all Web UI API routes onto the aiohttp application."""
    # OPTIONS handler for CORS preflight
    app.router.add_route("OPTIONS", "/api/{tail:.*}", handle_options)

    # Sessions CRUD
    app.router.add_get("/api/sessions", handle_list_sessions)
    app.router.add_post("/api/sessions", handle_create_session)
    app.router.add_get("/api/sessions/{session_id}", handle_get_session)
    app.router.add_patch("/api/sessions/{session_id}", handle_update_session)
    app.router.add_delete("/api/sessions/{session_id}", handle_delete_session)

    # Chat & Streaming
    app.router.add_post("/api/chat", handle_chat_message)
    app.router.add_get("/api/chat/stream", handle_chat_stream)

    # Audio & Voice STT
    app.router.add_post("/api/audio/transcribe", handle_audio_transcribe)

    # Workspaces
    app.router.add_get("/api/workspaces", handle_list_workspaces)
    app.router.add_post("/api/workspaces/select", handle_select_workspace)

    # File Downloads
    app.router.add_get("/api/files/download", handle_download_file)

    logger.info("Registered Chai Web UI REST & SSE routes on /api/*")
