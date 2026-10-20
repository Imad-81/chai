'use client';

import React, { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { 
  Bot, 
  User, 
  Copy, 
  Check, 
  FileText, 
  Download, 
  Sparkles, 
  Terminal, 
  Code2, 
  Cpu
} from 'lucide-react';

export interface ChatMessage {
  id?: number | string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  content_type?: string;
  created_at?: string;
  files?: Array<{
    fileName: string;
    filePath?: string;
    caption?: string;
  }>;
}

interface MessageListProps {
  messages: ChatMessage[];
  liveStatus: string | null;
  isLoading: boolean;
  onQuickPrompt: (prompt: string) => void;
  messagesEndRef: React.RefObject<HTMLDivElement | null>;
}

function CodeBlock({ children, className }: any) {
  const [copied, setCopied] = useState(false);
  const match = /language-(\w+)/.exec(className || '');
  const lang = match ? match[1] : '';
  const codeContent = String(children).replace(/\n$/, '');

  const handleCopy = () => {
    navigator.clipboard.writeText(codeContent);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  if (!match) {
    return <code className={className}>{children}</code>;
  }

  return (
    <div style={{ position: 'relative', margin: '12px 0' }}>
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          background: '#0e1320',
          padding: '6px 12px',
          borderTopLeftRadius: 'var(--radius-md)',
          borderTopRightRadius: 'var(--radius-md)',
          border: '1px solid var(--border-subtle)',
          borderBottom: 'none',
          fontSize: '0.75rem',
          color: 'var(--text-dim)',
          fontFamily: 'var(--font-mono)',
        }}
      >
        <span>{lang || 'code'}</span>
        <button
          onClick={handleCopy}
          style={{
            background: 'transparent',
            border: 'none',
            color: copied ? 'var(--accent-emerald)' : 'var(--text-muted)',
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            gap: '4px',
            fontSize: '0.75rem',
          }}
        >
          {copied ? <Check size={14} /> : <Copy size={14} />}
          <span>{copied ? 'Copied' : 'Copy'}</span>
        </button>
      </div>
      <pre style={{ margin: 0, borderTopLeftRadius: 0, borderTopRightRadius: 0 }}>
        <code className={className}>{codeContent}</code>
      </pre>
    </div>
  );
}

export default function MessageList({
  messages,
  liveStatus,
  isLoading,
  onQuickPrompt,
  messagesEndRef,
}: MessageListProps) {
  if (messages.length === 0 && !liveStatus && !isLoading) {
    return (
      <div className="messages-viewport">
        <div className="empty-chat-state">
          <div className="empty-icon-glow">
            <Sparkles size={34} />
          </div>
          <h2 className="empty-title">What would you like to build?</h2>
          <p className="empty-desc">
            Chai is linked directly to your local projects, Antigravity CLI, and system tools. Select a starter prompt or type your instructions below.
          </p>

          <div className="quick-prompts">
            <div
              className="quick-prompt-card"
              onClick={() => onQuickPrompt('List and inspect the recent git status and modified files')}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontWeight: 600, color: 'var(--text-main)', marginBottom: '4px' }}>
                <Terminal size={14} color="var(--accent-cyan)" /> Inspect Workspace
              </div>
              Check git status, branches, and modified files.
            </div>

            <div
              className="quick-prompt-card"
              onClick={() => onQuickPrompt('Review the code in core/ and recommend optimizations')}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontWeight: 600, color: 'var(--text-main)', marginBottom: '4px' }}>
                <Code2 size={14} color="var(--accent-indigo)" /> Code Review
              </div>
              Analyze repository code and get architectural guidance.
            </div>

            <div
              className="quick-prompt-card"
              onClick={() => onQuickPrompt('Run tests and verify our current pipeline')}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontWeight: 600, color: 'var(--text-main)', marginBottom: '4px' }}>
                <Cpu size={14} color="var(--accent-emerald)" /> Run Diagnostics
              </div>
              Execute test suite and diagnose any active errors.
            </div>

            <div
              className="quick-prompt-card"
              onClick={() => onQuickPrompt('Create an assignment report comparing Next.js vs Vite architecture')}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontWeight: 600, color: 'var(--text-main)', marginBottom: '4px' }}>
                <FileText size={14} color="var(--accent-pink)" /> Generate PDF
              </div>
              Draft a formatted academic document or report.
            </div>
          </div>
        </div>
        <div ref={messagesEndRef} />
      </div>
    );
  }

  return (
    <div className="messages-viewport">
      {messages.map((msg, index) => {
        const isUser = msg.role === 'user';
        return (
          <div key={msg.id || index} className={`message-row ${isUser ? 'user' : 'assistant'}`}>
            <div className={`message-avatar ${isUser ? 'user' : 'assistant'}`}>
              {isUser ? <User size={18} /> : <Bot size={18} />}
            </div>

            <div className="message-bubble">
              <div className="markdown-content">
                <ReactMarkdown
                  remarkPlugins={[remarkGfm]}
                  components={{
                    code: CodeBlock,
                  }}
                >
                  {msg.content}
                </ReactMarkdown>
              </div>

              {msg.files && msg.files.length > 0 && (
                <div style={{ marginTop: '12px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
                  {msg.files.map((file, fIdx) => (
                    <a
                      key={fIdx}
                      href={`/api/chai/files/download?path=${encodeURIComponent(file.filePath || '')}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="file-attachment-card"
                    >
                      <FileText size={20} color="var(--accent-cyan)" />
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div style={{ fontWeight: 600, fontSize: '0.86rem', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                          {file.fileName}
                        </div>
                        {file.caption && (
                          <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                            {file.caption}
                          </div>
                        )}
                      </div>
                      <Download size={16} color="var(--text-muted)" />
                    </a>
                  ))}
                </div>
              )}
            </div>
          </div>
        );
      })}

      {(liveStatus || isLoading) && (
        <div className="message-row assistant">
          <div className="message-avatar assistant">
            <Bot size={18} />
          </div>
          <div className="message-bubble" style={{ background: 'transparent', border: 'none', padding: '6px 0' }}>
            <div className="agent-step-badge">
              <Sparkles size={14} />
              <span>{liveStatus || 'Antigravity thinking...'}</span>
            </div>
          </div>
        </div>
      )}

      <div ref={messagesEndRef} />
    </div>
  );
}
