import os
import subprocess
from pathlib import Path
from faster_whisper import WhisperModel
from config import WHISPER_MODEL_SIZE, WHISPER_DEVICE

class VoiceTranscriber:
    _model = None

    @classmethod
    def get_model(cls):
        if cls._model is None:
            print(f"[Transcriber] Loading faster-whisper model ({WHISPER_MODEL_SIZE}) on {WHISPER_DEVICE}...")
            # compute_type='int8' with cpu_threads=6 for maximum throughput on Intel Ultra P-cores
            cls._model = WhisperModel(
                WHISPER_MODEL_SIZE, 
                device=WHISPER_DEVICE, 
                compute_type="int8",
                cpu_threads=6,
                num_workers=1
            )
            print("[Transcriber] Model loaded successfully.")
        return cls._model

    @classmethod
    def transcribe(cls, audio_path: str) -> str:
        """
        Transcribes an incoming audio file (e.g. Telegram .ogg voice note).
        Directly streams using PyAV with greedy decoding (beam_size=1) for sub-second speed.
        """
        path = Path(audio_path)
        if not path.exists():
            raise FileNotFoundError(f"Audio file does not exist: {audio_path}")

        model = cls.get_model()

        # 1. First attempt: Direct in-memory decode via PyAV (fastest, zero disk overhead)
        try:
            segments, info = model.transcribe(
                str(path), 
                beam_size=1, 
                best_of=1,
                condition_on_previous_text=False,
                vad_filter=True
            )
            text_chunks = [segment.text.strip() for segment in segments]
            full_text = " ".join(text_chunks).strip()
            print(f"[Transcriber] Transcribed {info.duration:.1f}s audio (greedy, lang: {info.language}): '{full_text}'")
            return full_text
        except Exception as direct_err:
            print(f"[Transcriber] Direct PyAV decode failed ({direct_err}), falling back to ffmpeg...")

        # 2. Fallback: Convert to 16kHz PCM WAV with ffmpeg if direct PyAV decode failed
        wav_path = path.with_suffix(".wav")
        try:
            cmd = [
                "ffmpeg", "-y", "-i", str(path),
                "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le",
                str(wav_path)
            ]
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            segments, info = model.transcribe(
                str(wav_path), 
                beam_size=1, 
                best_of=1,
                condition_on_previous_text=False
            )
            text_chunks = [segment.text.strip() for segment in segments]
            full_text = " ".join(text_chunks).strip()
            print(f"[Transcriber] Transcribed via ffmpeg fallback {info.duration:.1f}s audio: '{full_text}'")
            return full_text
        finally:
            if wav_path.exists() and wav_path != path:
                try:
                    wav_path.unlink()
                except Exception:
                    pass
