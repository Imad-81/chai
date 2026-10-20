'use client';

import React, { useState, useEffect, useRef, useCallback } from 'react';
import { Menu, FolderGit2, Activity, Sparkles } from 'lucide-react';
import Sidebar, { ChatSession } from '../components/Sidebar';
import MessageList, { ChatMessage } from '../components/MessageList';
import Composer from '../components/Composer';
import WorkspaceModal from '../components/WorkspaceModal';
import SystemModal from '../components/SystemModal';

export default function ChaiChatApp() {
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [liveStatus, setLiveStatus] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  const [activeWorkspace, setActiveWorkspace] = useState('');
  const [activeWorkspaceName, setActiveWorkspaceName] = useState('Workspace');

  const [isMobileSidebarOpen, setIsMobileSidebarOpen] = useState(false);
  const [isWorkspaceModalOpen, setIsWorkspaceModalOpen] = useState(false);
  const [isSystemModalOpen, setIsSystemModalOpen] = useState(false);

  const messagesEndRef = useRef<HTMLDivElement | null>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, liveStatus]);

  // 1. Fetch initial workspace
  const fetchWorkspaceInfo = async () => {
    try {
      const res = await fetch('/api/chai/workspaces');
      if (res.ok) {
        const data = await res.json();
        setActiveWorkspace(data.active || '');
        setActiveWorkspaceName(data.active_name || 'Workspace');
      }
    } catch (e) {
      console.error('Error fetching workspace:', e);
    }
  };

  // 2. Fetch sessions list
  const fetchSessions = async () => {
    try {
      const res = await fetch('/api/chai/sessions');
      if (res.ok) {
        const data = await res.json();
        const list: ChatSession[] = data.sessions || [];
        setSessions(list);
        if (list.length > 0 && !activeSessionId) {
          selectSession(list[0].session_id);
        } else if (list.length === 0) {
          handleNewChat();
        }
      }
    } catch (e) {
      console.error('Error fetching sessions:', e);
    }
  };

  // 3. Load messages for a session
  const selectSession = async (sessionId: string) => {
    setActiveSessionId(sessionId);
    setLiveStatus(null);
    try {
      const res = await fetch(`/api/chai/sessions/${sessionId}`);
      if (res.ok) {
        const data = await res.json();
        setMessages(data.messages || []);
      }
    } catch (e) {
      console.error('Error loading session messages:', e);
    }
  };

  useEffect(() => {
    fetchWorkspaceInfo();
    fetchSessions();
  }, []);

  // 4. Create new chat session
  const handleNewChat = async () => {
    try {
      const res = await fetch('/api/chai/sessions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title: 'New Chat' }),
      });
      if (res.ok) {
        const data = await res.json();
        const newSession = data.session;
        setSessions((prev) => [newSession, ...prev]);
        setActiveSessionId(newSession.session_id);
        setMessages([]);
        setLiveStatus(null);
      }
    } catch (e) {
      console.error('Error creating new session:', e);
    }
  };

  // 5. Delete session
  const handleDeleteSession = async (sessionId: string) => {
    try {
      const res = await fetch(`/api/chai/sessions/${sessionId}`, {
        method: 'DELETE',
      });
      if (res.ok) {
        setSessions((prev) => prev.filter((s) => s.session_id !== sessionId));
        if (activeSessionId === sessionId) {
          const remaining = sessions.filter((s) => s.session_id !== sessionId);
          if (remaining.length > 0) {
            selectSession(remaining[0].session_id);
          } else {
            handleNewChat();
          }
        }
      }
    } catch (e) {
      console.error('Error deleting session:', e);
    }
  };

  // 6. Rename session
  const handleRenameSession = async (sessionId: string, newTitle: string) => {
    try {
      const res = await fetch(`/api/chai/sessions/${sessionId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title: newTitle }),
      });
      if (res.ok) {
        setSessions((prev) =>
          prev.map((s) => (s.session_id === sessionId ? { ...s, title: newTitle } : s))
        );
      }
    } catch (e) {
      console.error('Error renaming session:', e);
    }
  };

  // 7. Send message with SSE streaming
  const handleSendMessage = async (text: string) => {
    if (!text.trim() || isLoading) return;

    let targetSessionId = activeSessionId;
    if (!targetSessionId) {
      await handleNewChat();
      targetSessionId = activeSessionId;
    }

    // Optimistically append user message
    const tempUserMsg: ChatMessage = {
      role: 'user',
      content: text,
      created_at: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, tempUserMsg]);
    setIsLoading(true);
    setLiveStatus('Thinking...');

    try {
      // Use EventSource for real-time SSE stream
      const url = `/api/chai/chat/stream?session_id=${encodeURIComponent(
        targetSessionId || ''
      )}&text=${encodeURIComponent(text)}`;

      const eventSource = new EventSource(url);

      eventSource.addEventListener('status', (e: any) => {
        try {
          const payload = JSON.parse(e.data);
          if (payload.message) {
            setLiveStatus(payload.message);
          }
        } catch (err) {}
      });

      eventSource.addEventListener('result', (e: any) => {
        try {
          const payload = JSON.parse(e.data);
          if (payload.message) {
            setMessages((prev) => [...prev, payload.message]);
          }
        } catch (err) {}
      });

      eventSource.addEventListener('error', (e: any) => {
        console.warn('SSE error or closed:', e);
        eventSource.close();
        setIsLoading(false);
        setLiveStatus(null);
        fetchSessions();
      });

      eventSource.addEventListener('done', () => {
        eventSource.close();
        setIsLoading(false);
        setLiveStatus(null);
        fetchSessions();
      });
    } catch (err) {
      console.error('Failed to send message via stream:', err);
      // Fallback to regular POST
      try {
        const res = await fetch('/api/chai/chat', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ text, session_id: targetSessionId }),
        });
        if (res.ok) {
          const data = await res.json();
          if (data.message) {
            setMessages((prev) => [...prev, data.message]);
          }
        }
      } catch (fallbackErr) {
        console.error('Fallback chat failed:', fallbackErr);
      } finally {
        setIsLoading(false);
        setLiveStatus(null);
        fetchSessions();
      }
    }
  };

  const activeSession = sessions.find((s) => s.session_id === activeSessionId);
  const activeTitle = activeSession?.title || 'New Chat';

  return (
    <div className="app-container">
      <Sidebar
        sessions={sessions}
        activeSessionId={activeSessionId}
        onSelectSession={selectSession}
        onNewChat={handleNewChat}
        onDeleteSession={handleDeleteSession}
        onRenameSession={handleRenameSession}
        isOpenMobile={isMobileSidebarOpen}
        onCloseMobile={() => setIsMobileSidebarOpen(false)}
        onOpenSystemModal={() => setIsSystemModalOpen(true)}
        onOpenWorkspaceModal={() => setIsWorkspaceModalOpen(true)}
        activeWorkspaceName={activeWorkspaceName}
      />

      <main className="chat-main">
        <header className="chat-header">
          <div className="header-left">
            <button
              className="btn-sidebar-toggle"
              onClick={() => setIsMobileSidebarOpen(true)}
              title="Open Navigation"
            >
              <Menu size={20} />
            </button>
            <div className="chat-header-title">{activeTitle}</div>
          </div>

          <div className="header-actions">
            <div
              className="workspace-pill"
              onClick={() => setIsWorkspaceModalOpen(true)}
              title={`Active Project: ${activeWorkspace}`}
            >
              <div className="workspace-pill-dot" />
              <span>{activeWorkspaceName}</span>
            </div>

            <button
              className="btn-sidebar-toggle"
              onClick={() => setIsSystemModalOpen(true)}
              title="System Diagnostics"
            >
              <Activity size={18} color="var(--accent-emerald)" />
            </button>
          </div>
        </header>

        <MessageList
          messages={messages}
          liveStatus={liveStatus}
          isLoading={isLoading}
          onQuickPrompt={handleSendMessage}
          messagesEndRef={messagesEndRef}
        />

        <Composer onSendMessage={handleSendMessage} isLoading={isLoading} />
      </main>

      <WorkspaceModal
        isOpen={isWorkspaceModalOpen}
        onClose={() => setIsWorkspaceModalOpen(false)}
        activeWorkspace={activeWorkspace}
        onSelectWorkspace={(wsPath) => {
          setActiveWorkspace(wsPath);
          setActiveWorkspaceName(wsPath.split('/').pop() || 'Workspace');
          fetchWorkspaceInfo();
        }}
      />

      <SystemModal
        isOpen={isSystemModalOpen}
        onClose={() => setIsSystemModalOpen(false)}
      />
    </div>
  );
}
