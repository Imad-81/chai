'use client';

import React, { useState } from 'react';
import { 
  Plus, 
  Search, 
  MessageSquare, 
  Trash2, 
  Edit3, 
  Activity, 
  FolderGit2, 
  X,
  Sparkles
} from 'lucide-react';

export interface ChatSession {
  session_id: string;
  title: string;
  workspace?: string;
  turn_count: number;
  is_active: boolean;
  agy_conversation_id?: string;
  started_at?: string;
  last_activity_at?: string;
}

interface SidebarProps {
  sessions: ChatSession[];
  activeSessionId: string | null;
  onSelectSession: (id: string) => void;
  onNewChat: () => void;
  onDeleteSession: (id: string) => void;
  onRenameSession: (id: string, newTitle: string) => void;
  isOpenMobile: boolean;
  onCloseMobile: () => void;
  onOpenSystemModal: () => void;
  onOpenWorkspaceModal: () => void;
  activeWorkspaceName: string;
}

export default function Sidebar({
  sessions,
  activeSessionId,
  onSelectSession,
  onNewChat,
  onDeleteSession,
  onRenameSession,
  isOpenMobile,
  onCloseMobile,
  onOpenSystemModal,
  onOpenWorkspaceModal,
  activeWorkspaceName,
}: SidebarProps) {
  const [search, setSearch] = useState('');
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editTitle, setEditTitle] = useState('');

  const filteredSessions = sessions.filter((s) =>
    (s.title || 'New Chat').toLowerCase().includes(search.toLowerCase())
  );

  const startRename = (s: ChatSession, e: React.MouseEvent) => {
    e.stopPropagation();
    setEditingId(s.session_id);
    setEditTitle(s.title || 'New Chat');
  };

  const submitRename = (id: string) => {
    if (editTitle.trim()) {
      onRenameSession(id, editTitle.trim());
    }
    setEditingId(null);
  };

  return (
    <>
      <div 
        className={`mobile-overlay ${isOpenMobile ? 'open' : ''}`} 
        onClick={onCloseMobile} 
      />
      <aside className={`sidebar ${isOpenMobile ? 'open' : ''}`}>
        <div className="sidebar-header">
          <div className="brand-badge">
            <div className="brand-icon">
              <Sparkles size={18} />
            </div>
            <span>Chai Assistant</span>
          </div>
          <button 
            className="btn-sidebar-toggle"
            onClick={onCloseMobile}
            style={{ display: isOpenMobile ? 'flex' : 'none' }}
          >
            <X size={20} />
          </button>
        </div>

        <button className="btn-new-chat" onClick={onNewChat}>
          <Plus size={18} />
          <span>New Chat</span>
        </button>

        <div className="search-box">
          <Search size={15} className="search-icon" />
          <input
            type="text"
            className="search-input"
            placeholder="Search conversations..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>

        <div className="sessions-list">
          {filteredSessions.length === 0 ? (
            <div style={{ textAlign: 'center', padding: '24px 12px', color: 'var(--text-dim)', fontSize: '0.85rem' }}>
              {search ? 'No matching conversations' : 'No chats yet. Start one!'}
            </div>
          ) : (
            filteredSessions.map((session) => {
              const isActive = session.session_id === activeSessionId;
              const isEditing = editingId === session.session_id;

              return (
                <div
                  key={session.session_id}
                  className={`session-item ${isActive ? 'active' : ''}`}
                  onClick={() => {
                    onSelectSession(session.session_id);
                    onCloseMobile();
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px', overflow: 'hidden', flex: 1 }}>
                    <MessageSquare size={16} color={isActive ? 'var(--accent-cyan)' : 'var(--text-dim)'} style={{ minWidth: 16 }} />
                    {isEditing ? (
                      <input
                        type="text"
                        value={editTitle}
                        onChange={(e) => setEditTitle(e.target.value)}
                        onBlur={() => submitRename(session.session_id)}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter') submitRename(session.session_id);
                          if (e.key === 'Escape') setEditingId(null);
                        }}
                        autoFocus
                        onClick={(e) => e.stopPropagation()}
                        style={{
                          background: 'var(--bg-base)',
                          border: '1px solid var(--accent-cyan)',
                          color: 'var(--text-main)',
                          padding: '2px 6px',
                          borderRadius: '4px',
                          fontSize: '0.86rem',
                          width: '100%',
                          outline: 'none',
                        }}
                      />
                    ) : (
                      <span className="session-title">{session.title || 'New Chat'}</span>
                    )}
                  </div>

                  {!isEditing && (
                    <div className="session-actions" onClick={(e) => e.stopPropagation()}>
                      <button
                        className="btn-icon-tiny"
                        title="Rename"
                        onClick={(e) => startRename(session, e)}
                      >
                        <Edit3 size={13} />
                      </button>
                      <button
                        className="btn-icon-tiny danger"
                        title="Delete"
                        onClick={(e) => {
                          e.stopPropagation();
                          if (confirm('Delete this conversation?')) {
                            onDeleteSession(session.session_id);
                          }
                        }}
                      >
                        <Trash2 size={13} />
                      </button>
                    </div>
                  )}
                </div>
              );
            })
          )}
        </div>

        <div className="sidebar-footer">
          <button
            onClick={onOpenWorkspaceModal}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              background: 'transparent',
              border: 'none',
              color: 'var(--text-muted)',
              fontSize: '0.8rem',
              cursor: 'pointer',
              maxWidth: '180px',
              whiteSpace: 'nowrap',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
            }}
            title={`Workspace: ${activeWorkspaceName}`}
          >
            <FolderGit2 size={16} color="var(--accent-cyan)" />
            <span style={{ overflow: 'hidden', textOverflow: 'ellipsis' }}>{activeWorkspaceName}</span>
          </button>

          <button
            onClick={onOpenSystemModal}
            className="btn-icon-tiny"
            title="System Diagnostics"
            style={{ padding: '6px' }}
          >
            <Activity size={18} color="var(--accent-emerald)" />
          </button>
        </div>
      </aside>
    </>
  );
}
