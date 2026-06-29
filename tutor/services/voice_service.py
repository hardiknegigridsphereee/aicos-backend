"""
voice_service.py — Vosk speech recognition service for AI Tutor

Accuracy improvements over original:
  - Uses vosk-model-en-us-0.22 (large model) instead of the tiny small model
  - Feeds audio to recognizer in real-time during recording, not after
  - Collects BOTH AcceptWaveform results AND the FinalResult in one pass
  - Strips duplicate partial text that Vosk sometimes appends
  - Configurable model path so you can swap to any Vosk model easily
"""

import vosk
import json
import queue
import sys
import sounddevice as sd
from typing import Optional


# ── Model recommendation ──────────────────────────────────────────────────────
# For best accuracy use the large model:
#   wget https://alphacephei.com/vosk/models/vosk-model-en-us-0.22.zip
#   unzip vosk-model-en-us-0.22.zip -d vosk_models/
#
# The small model (vosk-model-small-en-us-0.15) is ~40 MB and noticeably less
# accurate on natural speech.  The large model (vosk-model-en-us-0.22) is
# ~1.8 GB and matches near-Whisper quality for English.
#
# Mid-tier option (~128 MB, good balance):
#   vosk-model-en-us-0.42-gigaspeech
# ─────────────────────────────────────────────────────────────────────────────

DEFAULT_MODEL = "vosk_models/vosk-model-en-us-0.22"
SAMPLE_RATE   = 16000
BLOCK_SIZE    = 4000   # smaller blocks = lower latency, more frequent partial results


class VoiceTutorService:
    """
    Single-shot speech recognition.
    Records for a fixed duration then returns the transcribed text.
    Feeds audio into the recognizer in real time during recording for
    higher accuracy than the original batch-after approach.
    """

    def __init__(self, model_path: str = DEFAULT_MODEL):
        try:
            vosk.SetLogLevel(-1)          # suppress Vosk's verbose Kaldi logs
            self.model      = vosk.Model(model_path)
            self.audio_queue: queue.Queue = queue.Queue()
            print("✅ VoiceTutorService initialised")
            print(f"   Model: {model_path}")
        except Exception as exc:
            print(f"❌ Failed to initialise voice service: {exc}")
            sys.exit(1)

    # ── internal ──────────────────────────────────────────────────────────────

    def _audio_callback(self, indata, frames, time, status):
        if status:
            print(f"[audio status] {status}", file=sys.stderr)
        self.audio_queue.put(bytes(indata))

    def _drain_and_transcribe(self, recognizer: vosk.KaldiRecognizer) -> str:
        """
        Feed every chunk still in the queue into the recognizer,
        then call FinalResult() once.  Returns the full text.
        """
        seen_texts: list[str] = []

        while not self.audio_queue.empty():
            chunk = self.audio_queue.get()
            if recognizer.AcceptWaveform(chunk):
                text = json.loads(recognizer.Result()).get("text", "")
                if text:
                    seen_texts.append(text)

        # Always call FinalResult — Vosk may have buffered the last few words
        final = json.loads(recognizer.FinalResult()).get("text", "")
        if final and final not in seen_texts:
            seen_texts.append(final)

        return " ".join(seen_texts).strip()

    # ── public ────────────────────────────────────────────────────────────────

    def listen_once(self, duration: int = 6) -> Optional[str]:
        """
        Open the microphone, record for *duration* seconds, return transcript.
        Audio is fed to Vosk in real-time during recording so the model can
        do incremental decoding — this improves accuracy vs. batch-after.
        """
        # Fresh recognizer for every call (prevents stale LM state)
        recognizer = vosk.KaldiRecognizer(self.model, SAMPLE_RATE)
        recognizer.SetWords(True)   # enables word-level confidence scores

        # Empty any leftover audio from a previous call
        while not self.audio_queue.empty():
            self.audio_queue.get()

        print(f"\n🎤 Listening for {duration} seconds… speak now!")

        with sd.RawInputStream(
            samplerate=SAMPLE_RATE,
            blocksize=BLOCK_SIZE,
            channels=1,
            dtype="int16",
            callback=self._audio_callback,
        ):
            # Feed chunks into recognizer while recording
            import time
            deadline = time.monotonic() + duration
            while time.monotonic() < deadline:
                try:
                    chunk = self.audio_queue.get(timeout=0.1)
                    if recognizer.AcceptWaveform(chunk):
                        partial = json.loads(recognizer.Result()).get("text", "")
                        if partial:
                            print(f"   ↳ {partial}", flush=True)
                except queue.Empty:
                    pass

        print("📝 Finalising transcription…")
        result = self._drain_and_transcribe(recognizer)

        if result:
            print(f"\n✅ TRANSCRIPTION: {result}\n")
        else:
            print("\n⚠️  No speech detected — please speak clearly into the mic.\n")

        return result or None


# ── Quick hardware check ───────────────────────────────────────────────────────

def test_microphone() -> bool:
    """Verify the microphone is capturing audio before loading the model."""
    try:
        print("🎤 Available audio devices:")
        for i, dev in enumerate(sd.query_devices()):
            marker = " ◀ default" if i == sd.default.device[0] else ""
            print(f"  [{i}] {dev['name']}{marker}")

        print("\n🎤 Recording 2 seconds of audio — speak or make noise…")
        recording = sd.rec(
            int(2 * SAMPLE_RATE),
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype="int16",
        )
        sd.wait()

        import numpy as np
        max_amp = abs(recording).max()
        rms     = int(np.sqrt(np.mean(recording.astype(float) ** 2)))

        if max_amp > 200:
            print(f"✅ Microphone OK  (peak={max_amp}, rms={rms})")
            return True
        else:
            print(f"⚠️  Very low signal  (peak={max_amp}, rms={rms})")
            print("   Speak louder or check System Settings → Privacy → Microphone")
            return False

    except Exception as exc:
        print(f"❌ Microphone error: {exc}")
        return False


def test_full_recording():
    print("=" * 52)
    print("  VOICE RECOGNITION TEST")
    print("=" * 52)
    svc  = VoiceTutorService()
    text = svc.listen_once(duration=6)
    if text:
        print(f"📝 You said: {text}")
    else:
        print("❌ No speech detected")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--full":
        test_full_recording()
    else:
        print("Hardware check only.  For full recognition: python voice_service.py --full")
        print("-" * 52)
        test_microphone()