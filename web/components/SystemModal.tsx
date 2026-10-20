'use client';

import React, { useEffect, useState } from 'react';
import { X, Activity, Cpu, HardDrive, Terminal, Zap, RefreshCw } from 'lucide-react';

interface SystemModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export default function SystemModal({ isOpen, onClose }: SystemModalProps) {
  const [stats, setStats] = useState<any>(null);
  const [loading, setLoading] = useState(false);

  const fetchStats = async () => {
    setLoading(true);
    try {
      const res = await fetch('/api/chai/debug/state');
      if (res.ok) {
        const data = await res.json();
        setStats(data);
      }
    } catch (e) {
      console.error('Error fetching system stats:', e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (isOpen) {
      fetchStats();
      const interval = setInterval(fetchStats, 4000);
      return () => clearInterval(interval);
    }
  }, [isOpen]);

  if (!isOpen) return null;

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-card" onClick={(e) => e.stopPropagation()}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '16px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Activity size={20} color="var(--accent-emerald)" />
            <h3 style={{ fontSize: '1.1rem', fontWeight: 700 }}>Host Diagnostics</h3>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <button
              onClick={fetchStats}
              style={{ background: 'transparent', border: 'none', color: 'var(--text-dim)', cursor: 'pointer' }}
              title="Refresh"
            >
              <RefreshCw size={16} />
            </button>
            <button
              onClick={onClose}
              style={{ background: 'transparent', border: 'none', color: 'var(--text-muted)', cursor: 'pointer' }}
            >
              <X size={20} />
            </button>
          </div>
        </div>

        {stats ? (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '14px', fontSize: '0.88rem' }}>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px' }}>
              <div style={{ background: 'var(--bg-surface)', padding: '12px', borderRadius: 'var(--radius-md)', border: '1px solid var(--border-subtle)' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px', color: 'var(--text-muted)', fontSize: '0.78rem' }}>
                  <Cpu size={14} /> CPU Usage
                </div>
                <div style={{ fontSize: '1.3rem', fontWeight: 700, marginTop: '4px', color: 'var(--text-main)' }}>
                  {stats.cpuPercent}%
                </div>
              </div>

              <div style={{ background: 'var(--bg-surface)', padding: '12px', borderRadius: 'var(--radius-md)', border: '1px solid var(--border-subtle)' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px', color: 'var(--text-muted)', fontSize: '0.78rem' }}>
                  <HardDrive size={14} /> RAM Usage
                </div>
                <div style={{ fontSize: '1.3rem', fontWeight: 700, marginTop: '4px', color: 'var(--text-main)' }}>
                  {stats.ram?.usedGb} / {stats.ram?.totalGb} GB
                </div>
              </div>
            </div>

            <div style={{ background: 'var(--bg-surface)', padding: '12px', borderRadius: 'var(--radius-md)', border: '1px solid var(--border-subtle)' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px', color: 'var(--text-muted)', fontSize: '0.78rem', marginBottom: '6px' }}>
                <Terminal size={14} /> Antigravity Agent Status
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <div
                  style={{
                    width: '10px',
                    height: '10px',
                    borderRadius: '50%',
                    background: stats.antigravity?.is_running ? 'var(--accent-amber)' : 'var(--accent-emerald)',
                  }}
                />
                <span style={{ fontWeight: 600 }}>
                  {stats.antigravity?.is_running ? `Running (PID: ${stats.antigravity.pid})` : 'Idle / Ready'}
                </span>
              </div>
              {stats.antigravity?.last_execution && (
                <div style={{ fontSize: '0.76rem', color: 'var(--text-dim)', marginTop: '6px' }}>
                  Last task: {stats.antigravity.last_execution.prompt} ({stats.antigravity.last_execution.duration_seconds}s)
                </div>
              )}
            </div>

            <div style={{ background: 'var(--bg-surface)', padding: '12px', borderRadius: 'var(--radius-md)', border: '1px solid var(--border-subtle)' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px', color: 'var(--text-muted)', fontSize: '0.78rem', marginBottom: '6px' }}>
                <Zap size={14} /> Local AI Engine (Ollama)
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <div
                  style={{
                    width: '10px',
                    height: '10px',
                    borderRadius: '50%',
                    background: stats.ollama?.status === 'online' ? 'var(--accent-emerald)' : 'var(--accent-rose)',
                  }}
                />
                <span style={{ fontWeight: 600, textTransform: 'capitalize' }}>
                  {stats.ollama?.status}
                </span>
              </div>
            </div>
          </div>
        ) : (
          <div style={{ textAlign: 'center', padding: '24px', color: 'var(--text-muted)' }}>
            Loading system metrics...
          </div>
        )}
      </div>
    </div>
  );
}
