'use client';

import React, { useEffect, useState } from 'react';
import { 
  X, 
  Activity, 
  Cpu, 
  HardDrive, 
  Terminal, 
  Zap, 
  RefreshCw, 
  Play, 
  AlertTriangle, 
  CheckCircle2, 
  XCircle, 
  Square,
  FileText,
  Layers,
  ShieldAlert
} from 'lucide-react';

interface SystemModalProps {
  isOpen: boolean;
  onClose: () => void;
}

interface DiagnosticItem {
  name: string;
  status: 'pass' | 'warn' | 'fail';
  message: string;
}

export default function SystemModal({ isOpen, onClose }: SystemModalProps) {
  const [activeTab, setActiveTab] = useState<'overview' | 'diagnostics' | 'logs'>('overview');
  const [stats, setStats] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  
  // Diagnostics
  const [diagnosticsRunning, setDiagnosticsRunning] = useState(false);
  const [diagnosticsResults, setDiagnosticsResults] = useState<DiagnosticItem[] | null>(null);

  // Logs
  const [logs, setLogs] = useState<string[]>([]);
  const [logsLoading, setLogsLoading] = useState(false);

  // Antigravity kill action
  const [killingAgy, setKillingAgy] = useState(false);

  const fetchStats = async () => {
    try {
      const res = await fetch('/api/chai/debug/state');
      if (res.ok) {
        const data = await res.json();
        setStats(data);
      }
    } catch (e) {
      console.error('Error fetching system stats:', e);
    }
  };

  const fetchLogs = async () => {
    setLogsLoading(true);
    try {
      const res = await fetch('/api/chai/debug/logs?n=120');
      if (res.ok) {
        const data = await res.json();
        setLogs(data.lines || []);
      }
    } catch (e) {
      console.error('Error fetching logs:', e);
    } finally {
      setLogsLoading(false);
    }
  };

  const handleRunDiagnostics = async () => {
    setDiagnosticsRunning(true);
    try {
      const res = await fetch('/api/chai/diagnostics/run', { method: 'POST' });
      if (res.ok) {
        const data = await res.json();
        setDiagnosticsResults(data.results || []);
      }
    } catch (e) {
      console.error('Error running diagnostics:', e);
    } finally {
      setDiagnosticsRunning(false);
    }
  };

  const handleKillAgy = async () => {
    setKillingAgy(true);
    try {
      await fetch('/api/chai/agy/kill', { method: 'POST' });
      await fetchStats();
    } catch (e) {
      console.error('Error killing agy task:', e);
    } finally {
      setKillingAgy(false);
    }
  };

  useEffect(() => {
    if (isOpen) {
      fetchStats();
      const interval = setInterval(fetchStats, 3000);
      return () => clearInterval(interval);
    }
  }, [isOpen]);

  useEffect(() => {
    if (isOpen && activeTab === 'logs') {
      fetchLogs();
    }
  }, [isOpen, activeTab]);

  if (!isOpen) return null;

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div 
        className="modal-card" 
        onClick={(e) => e.stopPropagation()}
        style={{ maxWidth: '640px', width: '92%', maxHeight: '85vh', display: 'flex', flexDirection: 'column' }}
      >
        {/* Header */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '14px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Activity size={20} color="var(--accent-emerald)" />
            <h3 style={{ fontSize: '1.15rem', fontWeight: 700 }}>Chai Control Center</h3>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <button
              onClick={() => {
                fetchStats();
                if (activeTab === 'logs') fetchLogs();
              }}
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

        {/* Tab Navigation */}
        <div style={{ display: 'flex', gap: '6px', borderBottom: '1px solid var(--border-subtle)', paddingBottom: '10px', marginBottom: '16px' }}>
          <button
            onClick={() => setActiveTab('overview')}
            style={{
              background: activeTab === 'overview' ? 'var(--bg-surface)' : 'transparent',
              color: activeTab === 'overview' ? 'var(--text-main)' : 'var(--text-muted)',
              border: activeTab === 'overview' ? '1px solid var(--border-subtle)' : '1px solid transparent',
              borderRadius: 'var(--radius-sm)',
              padding: '6px 12px',
              fontSize: '0.82rem',
              fontWeight: 600,
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '6px'
            }}
          >
            <Activity size={14} /> Overview
          </button>
          <button
            onClick={() => setActiveTab('diagnostics')}
            style={{
              background: activeTab === 'diagnostics' ? 'var(--bg-surface)' : 'transparent',
              color: activeTab === 'diagnostics' ? 'var(--text-main)' : 'var(--text-muted)',
              border: activeTab === 'diagnostics' ? '1px solid var(--border-subtle)' : '1px solid transparent',
              borderRadius: 'var(--radius-sm)',
              padding: '6px 12px',
              fontSize: '0.82rem',
              fontWeight: 600,
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '6px'
            }}
          >
            <CheckCircle2 size={14} color="var(--accent-emerald)" /> Diagnostics Suite
          </button>
          <button
            onClick={() => setActiveTab('logs')}
            style={{
              background: activeTab === 'logs' ? 'var(--bg-surface)' : 'transparent',
              color: activeTab === 'logs' ? 'var(--text-main)' : 'var(--text-muted)',
              border: activeTab === 'logs' ? '1px solid var(--border-subtle)' : '1px solid transparent',
              borderRadius: 'var(--radius-sm)',
              padding: '6px 12px',
              fontSize: '0.82rem',
              fontWeight: 600,
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '6px'
            }}
          >
            <FileText size={14} color="var(--accent-cyan)" /> Live Logs
          </button>
        </div>

        {/* Tab Content */}
        <div style={{ flex: 1, overflowY: 'auto', paddingRight: '4px' }}>
          {activeTab === 'overview' && stats && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '14px', fontSize: '0.88rem' }}>
              {/* Host Metrics */}
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

              {/* Models & Architecture Card */}
              <div style={{ background: 'var(--bg-surface)', padding: '14px', borderRadius: 'var(--radius-md)', border: '1px solid var(--border-subtle)' }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '8px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontWeight: 600 }}>
                    <Zap size={16} color="var(--accent-amber)" /> Local LLM Configuration
                  </div>
                  <span style={{ fontSize: '0.75rem', color: stats.ollama?.status === 'online' ? 'var(--accent-emerald)' : 'var(--accent-rose)', fontWeight: 600 }}>
                    Ollama: {stats.ollama?.status}
                  </span>
                </div>
                <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginBottom: '8px', lineHeight: 1.4 }}>
                  Challenge Rule: Only local LLMs permitted are <b>qwen3.5:2b</b> for lighter tasks and <b>qwen3.5:4b</b> for heavier tasks.
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', fontSize: '0.8rem', background: '#0a0e17', padding: '10px', borderRadius: 'var(--radius-sm)' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span style={{ color: 'var(--text-dim)' }}>Primary Dispatcher:</span>
                    <span style={{ fontWeight: 600, color: 'var(--accent-cyan)' }}>{stats.models?.dispatcher || 'qwen3.5:4b'}</span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span style={{ color: 'var(--text-dim)' }}>Memory & Lighter Tasks:</span>
                    <span style={{ fontWeight: 600, color: 'var(--accent-emerald)' }}>{stats.models?.memory || 'qwen3.5:4b'}</span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span style={{ color: 'var(--text-dim)' }}>Agentic Execution:</span>
                    <span style={{ fontWeight: 600, color: 'var(--accent-pink)' }}>Google Antigravity (`agy`)</span>
                  </div>
                </div>
              </div>

              {/* Antigravity Process Controller */}
              <div style={{ background: 'var(--bg-surface)', padding: '14px', borderRadius: 'var(--radius-md)', border: '1px solid var(--border-subtle)' }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '8px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontWeight: 600 }}>
                    <Terminal size={16} color="var(--accent-cyan)" /> Antigravity Agent Controller
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <div
                      style={{
                        width: '8px',
                        height: '8px',
                        borderRadius: '50%',
                        background: stats.antigravity?.is_running ? 'var(--accent-amber)' : 'var(--accent-emerald)',
                      }}
                    />
                    <span style={{ fontSize: '0.8rem', fontWeight: 600 }}>
                      {stats.antigravity?.is_running ? `Running (PID: ${stats.antigravity.pid})` : 'Idle'}
                    </span>
                  </div>
                </div>

                {stats.antigravity?.is_running ? (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', marginTop: '8px' }}>
                    <div style={{ fontSize: '0.8rem', color: 'var(--text-main)', background: '#141a29', padding: '8px', borderRadius: 'var(--radius-sm)' }}>
                      Active task: {stats.antigravity.active_task?.prompt || 'Executing...'}
                    </div>
                    <button
                      onClick={handleKillAgy}
                      disabled={killingAgy}
                      style={{
                        background: '#dc2626',
                        color: '#fff',
                        border: 'none',
                        borderRadius: 'var(--radius-sm)',
                        padding: '6px 12px',
                        fontWeight: 600,
                        fontSize: '0.8rem',
                        cursor: 'pointer',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        gap: '6px'
                      }}
                    >
                      <Square size={14} /> Stop / Kill Active Task
                    </button>
                  </div>
                ) : (
                  <div style={{ fontSize: '0.78rem', color: 'var(--text-dim)' }}>
                    No tasks currently running. Tasks dispatched from chat run headless and stream progress here.
                  </div>
                )}
              </div>
            </div>
          )}

          {activeTab === 'diagnostics' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>
                  Validate all 7 internal subsystems without terminal commands:
                </span>
                <button
                  onClick={handleRunDiagnostics}
                  disabled={diagnosticsRunning}
                  style={{
                    background: 'var(--accent-indigo)',
                    color: '#fff',
                    border: 'none',
                    borderRadius: 'var(--radius-sm)',
                    padding: '6px 14px',
                    fontSize: '0.82rem',
                    fontWeight: 600,
                    cursor: 'pointer',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '6px'
                  }}
                >
                  {diagnosticsRunning ? (
                    <RefreshCw size={14} style={{ animation: 'spin 1s infinite linear' }} />
                  ) : (
                    <Play size={14} />
                  )}
                  {diagnosticsRunning ? 'Testing...' : 'Run Diagnostics'}
                </button>
              </div>

              {diagnosticsResults ? (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                  {diagnosticsResults.map((item, idx) => (
                    <div
                      key={idx}
                      style={{
                        background: 'var(--bg-surface)',
                        border: '1px solid var(--border-subtle)',
                        borderRadius: 'var(--radius-md)',
                        padding: '10px 12px',
                        display: 'flex',
                        alignItems: 'flex-start',
                        gap: '10px'
                      }}
                    >
                      {item.status === 'pass' && <CheckCircle2 size={18} color="var(--accent-emerald)" style={{ marginTop: '2px' }} />}
                      {item.status === 'warn' && <AlertTriangle size={18} color="var(--accent-amber)" style={{ marginTop: '2px' }} />}
                      {item.status === 'fail' && <XCircle size={18} color="var(--accent-rose)" style={{ marginTop: '2px' }} />}
                      <div style={{ flex: 1 }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                          <span style={{ fontWeight: 600, fontSize: '0.88rem' }}>{item.name}</span>
                          <span
                            style={{
                              fontSize: '0.72rem',
                              fontWeight: 700,
                              textTransform: 'uppercase',
                              color: item.status === 'pass' ? 'var(--accent-emerald)' : item.status === 'warn' ? 'var(--accent-amber)' : 'var(--accent-rose)'
                            }}
                          >
                            {item.status}
                          </span>
                        </div>
                        <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)', marginTop: '2px' }}>
                          {item.message}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div style={{ textAlign: 'center', padding: '30px', color: 'var(--text-dim)', fontSize: '0.85rem' }}>
                  Click "Run Diagnostics" to verify Database, Ollama, Whisper, PDF, Antigravity CLI, Telegram, and Debug Router.
                </div>
              )}
            </div>
          )}

          {activeTab === 'logs' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                <span>Recent Chai backend logs ({logs.length} lines)</span>
                <button
                  onClick={fetchLogs}
                  disabled={logsLoading}
                  style={{
                    background: 'transparent',
                    border: '1px solid var(--border-subtle)',
                    color: 'var(--text-dim)',
                    borderRadius: 'var(--radius-sm)',
                    padding: '4px 8px',
                    fontSize: '0.75rem',
                    cursor: 'pointer',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '4px'
                  }}
                >
                  <RefreshCw size={12} style={{ animation: logsLoading ? 'spin 1s infinite linear' : 'none' }} /> Refresh
                </button>
              </div>
              <pre
                style={{
                  background: '#070a10',
                  color: '#94a3b8',
                  padding: '12px',
                  borderRadius: 'var(--radius-md)',
                  fontSize: '0.75rem',
                  fontFamily: 'var(--font-mono)',
                  height: '340px',
                  overflowY: 'auto',
                  border: '1px solid var(--border-subtle)',
                  whiteSpace: 'pre-wrap',
                  lineHeight: 1.45
                }}
              >
                {logs.length > 0 ? logs.join('') : 'No logs recorded yet.'}
              </pre>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
