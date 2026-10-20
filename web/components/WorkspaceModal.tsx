'use client';

import React, { useEffect, useState } from 'react';
import { X, FolderGit2, Check, RefreshCw } from 'lucide-react';

interface WorkspaceItem {
  name: string;
  path: string;
}

interface WorkspaceModalProps {
  isOpen: boolean;
  onClose: () => void;
  activeWorkspace: string;
  onSelectWorkspace: (wsPath: string) => void;
}

export default function WorkspaceModal({
  isOpen,
  onClose,
  activeWorkspace,
  onSelectWorkspace,
}: WorkspaceModalProps) {
  const [workspaces, setWorkspaces] = useState<WorkspaceItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [switching, setSwitching] = useState<string | null>(null);

  const fetchWorkspaces = async () => {
    setLoading(true);
    try {
      const res = await fetch('/api/chai/workspaces');
      if (res.ok) {
        const data = await res.json();
        setWorkspaces(data.available || []);
      }
    } catch (e) {
      console.error('Error fetching workspaces:', e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (isOpen) {
      fetchWorkspaces();
    }
  }, [isOpen]);

  if (!isOpen) return null;

  const handleSelect = async (ws: WorkspaceItem) => {
    setSwitching(ws.name);
    try {
      const res = await fetch('/api/chai/workspaces/select', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ workspace: ws.path }),
      });
      if (res.ok) {
        onSelectWorkspace(ws.path);
        onClose();
      }
    } catch (e) {
      console.error('Error selecting workspace:', e);
    } finally {
      setSwitching(null);
    }
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-card" onClick={(e) => e.stopPropagation()}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '16px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <FolderGit2 size={20} color="var(--accent-cyan)" />
            <h3 style={{ fontSize: '1.1rem', fontWeight: 700 }}>Switch Workspace</h3>
          </div>
          <button
            onClick={onClose}
            style={{ background: 'transparent', border: 'none', color: 'var(--text-muted)', cursor: 'pointer' }}
          >
            <X size={20} />
          </button>
        </div>

        <p style={{ fontSize: '0.86rem', color: 'var(--text-muted)', marginBottom: '14px' }}>
          Select a project repository from your laptop. Chai and Antigravity will execute tasks in this context.
        </p>

        {loading ? (
          <div style={{ textAlign: 'center', padding: '24px', color: 'var(--text-muted)' }}>
            <RefreshCw size={24} style={{ animation: 'spin 1s infinite linear' }} />
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', maxHeight: '320px', overflowY: 'auto' }}>
            {workspaces.map((ws) => {
              const isActive = activeWorkspace === ws.path || activeWorkspace.endsWith(ws.name);
              return (
                <div
                  key={ws.path}
                  onClick={() => handleSelect(ws)}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    padding: '12px 14px',
                    borderRadius: 'var(--radius-md)',
                    background: isActive ? 'var(--bg-surface-elevated)' : 'var(--bg-surface)',
                    border: isActive ? '1px solid var(--accent-cyan)' : '1px solid var(--border-subtle)',
                    cursor: 'pointer',
                    transition: 'all 0.15s ease',
                  }}
                >
                  <div>
                    <div style={{ fontWeight: 600, fontSize: '0.92rem', color: isActive ? 'var(--accent-cyan)' : 'var(--text-main)' }}>
                      {ws.name}
                    </div>
                    <div style={{ fontSize: '0.75rem', color: 'var(--text-dim)', marginTop: '2px' }}>
                      {ws.path}
                    </div>
                  </div>
                  {isActive && <Check size={18} color="var(--accent-cyan)" />}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
