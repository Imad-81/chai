'use client';

import React, { useState, useRef, useEffect } from 'react';
import { Send, Mic, Square, Loader2 } from 'lucide-react';

interface ComposerProps {
  onSendMessage: (text: string) => void;
  isLoading: boolean;
}

export default function Composer({ onSendMessage, isLoading }: ComposerProps) {
  const [text, setText] = useState('');
  const [isRecording, setIsRecording] = useState(false);
  const [recordSeconds, setRecordSeconds] = useState(0);
  const [isTranscribing, setIsTranscribing] = useState(false);

  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const timerRef = useRef<NodeJS.Timeout | null>(null);

  // Auto-resize textarea height
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 160)}px`;
    }
  }, [text]);

  const handleSubmit = (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!text.trim() || isLoading) return;

    onSendMessage(text.trim());
    setText('');
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  // Audio Recording via MediaRecorder API
  const startRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      audioChunksRef.current = [];
      const mediaRecorder = new MediaRecorder(stream);
      mediaRecorderRef.current = mediaRecorder;

      mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          audioChunksRef.current.push(event.data);
        }
      };

      mediaRecorder.onstop = async () => {
        const tracks = stream.getTracks();
        tracks.forEach((t) => t.stop());

        const audioBlob = new Blob(audioChunksRef.current, { type: 'audio/webm' });
        await sendAudioForTranscription(audioBlob);
      };

      mediaRecorder.start(250);
      setIsRecording(true);
      setRecordSeconds(0);

      timerRef.current = setInterval(() => {
        setRecordSeconds((sec) => sec + 1);
      }, 1000);
    } catch (err) {
      console.error('Error accessing microphone:', err);
      alert('Could not access microphone. Please ensure microphone permissions are granted.');
    }
  };

  const stopRecording = () => {
    if (mediaRecorderRef.current && isRecording) {
      mediaRecorderRef.current.stop();
      setIsRecording(false);
      if (timerRef.current) {
        clearInterval(timerRef.current);
        timerRef.current = null;
      }
    }
  };

  const toggleRecording = () => {
    if (isRecording) {
      stopRecording();
    } else {
      startRecording();
    }
  };

  const sendAudioForTranscription = async (blob: Blob) => {
    setIsTranscribing(true);
    try {
      const formData = new FormData();
      formData.append('audio', blob, 'voice_recording.webm');

      const res = await fetch('/api/chai/audio/transcribe', {
        method: 'POST',
        body: formData,
      });

      if (res.ok) {
        const data = await res.json();
        const transcribedText = data.text?.trim();
        if (transcribedText) {
          setText((prev) => (prev ? `${prev} ${transcribedText}` : transcribedText));
        }
      } else {
        console.error('Transcription failed:', await res.text());
      }
    } catch (err) {
      console.error('Error sending audio:', err);
    } finally {
      setIsTranscribing(false);
      setRecordSeconds(0);
    }
  };

  const formatSeconds = (sec: number) => {
    const mins = Math.floor(sec / 60);
    const remaining = sec % 60;
    return `${mins}:${remaining < 10 ? '0' : ''}${remaining}`;
  };

  return (
    <div className="composer-dock">
      <div className="composer-wrapper">
        {isRecording ? (
          <div style={{ flex: 1, display: 'flex', alignItems: 'center', gap: '10px', padding: '8px 0', color: 'var(--accent-rose)' }}>
            <div style={{ width: 10, height: 10, borderRadius: '50%', background: 'var(--accent-rose)', animation: 'micPulse 1s infinite alternate' }} />
            <span style={{ fontWeight: 600, fontSize: '0.9rem' }}>Recording: {formatSeconds(recordSeconds)}</span>
            <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>(Tap red button to transcribe)</span>
          </div>
        ) : isTranscribing ? (
          <div style={{ flex: 1, display: 'flex', alignItems: 'center', gap: '8px', padding: '8px 0', color: 'var(--accent-cyan)' }}>
            <Loader2 size={16} style={{ animation: 'spin 1s infinite linear' }} />
            <span style={{ fontSize: '0.88rem' }}>Transcribing with Whisper STT...</span>
          </div>
        ) : (
          <textarea
            ref={textareaRef}
            className="composer-textarea"
            placeholder="Message Chai or instruct Antigravity... (Shift+Enter for newline)"
            rows={1}
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={isLoading}
          />
        )}

        <button
          type="button"
          className={`composer-btn btn-mic ${isRecording ? 'recording' : ''}`}
          onClick={toggleRecording}
          disabled={isLoading || isTranscribing}
          title={isRecording ? 'Stop Recording' : 'Record Voice Note'}
        >
          {isRecording ? <Square size={18} /> : isTranscribing ? <Loader2 size={18} style={{ animation: 'spin 1s infinite linear' }} /> : <Mic size={18} />}
        </button>

        <button
          type="button"
          className="composer-btn btn-send"
          onClick={() => handleSubmit()}
          disabled={!text.trim() || isLoading || isRecording || isTranscribing}
          title="Send Message"
        >
          <Send size={18} />
        </button>
      </div>
    </div>
  );
}
