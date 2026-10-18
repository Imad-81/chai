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
            # compute_type='int8' is super fast and low memory on CPU
            cls._model = WhisperModel(WHISPER_MODEL_SIZE, device=WHISPER_DEVICE, compute_type="int8")
            print("[Transcriber] Model loaded successfully.")
        return cls._model

    @classmethod
    def transcribe(cls, audio_path: str) -> str:
        """
        Transcribes an incoming WhatsApp audio file (usually .ogg).
        Returns the transcribed text.
        """
        path = Path(audio_path)
        if not path.exists():
            raise FileNotFoundError(f"Audio file does not exist: {audio_path}")

        # If it's an .ogg file from WhatsApp, convert to a standard 16kHz WAV for maximum fidelity
        wav_path = path.with_suffix(".wav")
        try:
            cmd = [
                "ffmpeg", "-y", "-i", str(path),
                "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le",
                str(wav_path)
            ]
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            target_file = str(wav_path)
        except Exception as e:
            print(f"[Transcriber] ffmpeg conversion failed, trying raw audio: {e}")
            target_file = str(path)

        try:
            model = cls.get_model()
            segments, info = model.transcribe(target_file, beam_size=5)
            text_chunks = [segment.text.strip() for segment in segments]
            full_text = " ".join(text_chunks).strip()
            print(f"[Transcriber] Transcribed {info.duration:.1f}s audio (lang: {info.language}): '{full_text}'")
            return full_text
        finally:
            if wav_path.exists() and wav_path != path:
                try:
                    wav_path.unlink()
                except Exception:
                    pass
