"""
voice_activity_service.py — VAD-controlled speech recognition for AI Tutor

Key fixes over the original:
  - Real-time recognizer feeding (not batch-after-silence)
  - RMS energy for VAD instead of raw peak amplitude (far less trigger-happy)
  - Pre-roll buffer: keeps ~300 ms of audio before speech onset so the first
    word isn't clipped
  - Larger default model for dramatically better accuracy
  - WebSocket server (optional) so the browser UI can start/stop recording
    and receive results in real time
  - Thread-safe start/stop via an Event flag
"""

import vosk
import json
import queue
import sys
import time
import threading
import numpy as np
import sounddevice as sd
from typing import Optional, Callable
from collections import deque

# ── Default model (same recommendation as voice_service.py) ──────────────────
DEFAULT_MODEL = "vosk_models/vosk-model-en-us-0.22"
SAMPLE_RATE   = 16000
BLOCK_SIZE    = 4000          # 250 ms chunks at 16 kHz
PRE_ROLL_CHUNKS = 2           # keep 2 chunks (~500 ms) before speech onset


class VoiceActivityDetector:
    """
    Continuous VAD-based recorder.

    Improvements:
    - Uses RMS energy (not raw peak) — much more stable VAD signal
    - Pre-roll buffer avoids clipping the first syllable
    - Feeds audio into Vosk in real-time while recording
    - Thread-safe: external code can call .stop() from another thread
    - Optional WebSocket broadcast so the browser receives live partials
    """

    def __init__(
        self,
        model_path: str     = DEFAULT_MODEL,
        silence_timeout: float = 1.8,   # seconds of silence before committing
        rms_threshold: int  = 80,       # RMS energy threshold (tune per environment)
        sample_rate: int    = SAMPLE_RATE,
    ):
        vosk.SetLogLevel(-1)
        self.model          = vosk.Model(model_path)
        self.sample_rate    = sample_rate
        self.silence_timeout= silence_timeout
        self.rms_threshold  = rms_threshold

        self.audio_queue: queue.Queue = queue.Queue()
        self._stop_event              = threading.Event()

        # State
        self.is_recording   = False
        self.audio_buffer:  list[bytes] = []
        self.pre_roll:      deque       = deque(maxlen=PRE_ROLL_CHUNKS)
        self.silence_chunks = 0

        # WebSocket broadcaster (injected externally if needed)
        self.ws_broadcast: Optional[Callable[[str], None]] = None

        print("✅ VoiceActivityDetector initialised")
        print(f"   Model:           {model_path}")
        print(f"   Silence timeout: {silence_timeout}s")
        print(f"   RMS threshold:   {rms_threshold}")

    # ── internal helpers ──────────────────────────────────────────────────────

    def _audio_callback(self, indata, frames, time_info, status):
        if status:
            print(f"[audio status] {status}", file=sys.stderr)
        self.audio_queue.put(bytes(indata))

    @staticmethod
    def _rms(chunk: bytes) -> float:
        arr = np.frombuffer(chunk, dtype=np.int16).astype(np.float32)
        return float(np.sqrt(np.mean(arr ** 2)))

    def _process_buffer(self) -> Optional[str]:
        """Transcribe the accumulated audio buffer. Returns text or None."""
        if not self.audio_buffer:
            return None

        print(f"   📝 Transcribing {len(self.audio_buffer)} chunks…")

        recognizer = vosk.KaldiRecognizer(self.model, self.sample_rate)
        recognizer.SetWords(True)

        texts: list[str] = []
        for chunk in self.audio_buffer:
            if recognizer.AcceptWaveform(chunk):
                t = json.loads(recognizer.Result()).get("text", "")
                if t:
                    texts.append(t)

        final = json.loads(recognizer.FinalResult()).get("text", "")
        if final and final not in texts:
            texts.append(final)

        result = " ".join(texts).strip()
        if result:
            print(f"\n✅ TRANSCRIBED: {result}")
            print("-" * 52)
        else:
            print("   ⚠️  No speech recognised in buffer.")
        return result or None

    # ── public API ────────────────────────────────────────────────────────────

    def stop(self):
        """Signal the listen loop to exit cleanly (call from any thread)."""
        self._stop_event.set()

    def listen_continuously(self, callback: Optional[Callable[[str], None]] = None):
        """
        Open the microphone and loop until .stop() is called or Ctrl-C.
        Calls *callback(text)* each time a complete utterance is detected.
        """
        self._stop_event.clear()

        print("\n" + "=" * 52)
        print("  🎤  Voice Activity Detection — ready")
        print("=" * 52)
        print("Start speaking.  System auto-detects start / end of speech.")
        print(f"RMS threshold: {self.rms_threshold}  |  silence timeout: {self.silence_timeout}s")
        print("Call .stop() or press Ctrl-C to exit.\n")

        # Live recognizer for partial results during recording
        live_recognizer = vosk.KaldiRecognizer(self.model, self.sample_rate)

        with sd.RawInputStream(
            samplerate=self.sample_rate,
            blocksize=BLOCK_SIZE,
            channels=1,
            dtype="int16",
            callback=self._audio_callback,
        ):
            while not self._stop_event.is_set():
                try:
                    chunk = self.audio_queue.get(timeout=0.2)
                except queue.Empty:
                    continue

                rms = self._rms(chunk)
                is_speech = rms > self.rms_threshold

                # ── amplitude bar (idle only) ──────────────────────────────
                if not self.is_recording:
                    bar = "█" * min(30, int(rms / 30))
                    print(f"\r  🔊 [{bar:<30}] {int(rms):4d}", end="", flush=True)

                # ── speech onset ───────────────────────────────────────────
                if is_speech and not self.is_recording:
                    self.is_recording   = True
                    self.silence_chunks = 0
                    # Include pre-roll so the first word isn't cut
                    self.audio_buffer   = list(self.pre_roll) + [chunk]
                    live_recognizer     = vosk.KaldiRecognizer(self.model, self.sample_rate)
                    print(f"\n🎙️  Speech detected  (rms={int(rms)})")

                # ── speech continues ───────────────────────────────────────
                elif is_speech and self.is_recording:
                    self.audio_buffer.append(chunk)
                    self.silence_chunks = 0

                    # Stream partial result to terminal + optional WS
                    if live_recognizer.AcceptWaveform(chunk):
                        partial = json.loads(live_recognizer.Result()).get("text", "")
                        if partial:
                            print(f"   ↳ {partial}", flush=True)
                            if self.ws_broadcast:
                                self.ws_broadcast(json.dumps({"type": "partial", "text": partial}))

                # ── silence while recording ────────────────────────────────
                elif not is_speech and self.is_recording:
                    self.audio_buffer.append(chunk)
                    self.silence_chunks += 1

                    # Each chunk is BLOCK_SIZE/SAMPLE_RATE seconds
                    silence_sec = self.silence_chunks * (BLOCK_SIZE / self.sample_rate)

                    if silence_sec >= self.silence_timeout:
                        print(f"\n⏸  Silence {silence_sec:.1f}s — committing utterance…")
                        text = self._process_buffer()

                        if text:
                            if callback:
                                callback(text)
                            if self.ws_broadcast:
                                self.ws_broadcast(json.dumps({"type": "final", "text": text}))

                        # Reset
                        self.is_recording   = False
                        self.audio_buffer   = []
                        self.silence_chunks = 0
                        self.pre_roll.clear()
                        print("\n🎤 Ready — start speaking\n🔊 ", end="", flush=True)

                # ── always update pre-roll when idle ──────────────────────
                if not self.is_recording:
                    self.pre_roll.append(chunk)

        print("\n\n👋 VAD loop exited cleanly.")


# ── WebSocket bridge (optional, for browser UI) ───────────────────────────────

class VoiceWebSocketServer:
    """
    Minimal asyncio WebSocket server that bridges the browser UI to the VAD.

    The browser sends:
      {"action": "start"}   — begin listening
      {"action": "stop"}    — stop listening and return final result

    The server pushes:
      {"type": "partial", "text": "..."}  — live partials
      {"type": "final",   "text": "..."}  — committed utterance
      {"type": "status",  "state": "listening"|"idle"}
    """

    def __init__(self, host="localhost", port=8765, model_path=DEFAULT_MODEL):
        self.host       = host
        self.port       = port
        self.detector   = VoiceActivityDetector(model_path=model_path)
        self._vad_thread: Optional[threading.Thread] = None
        self._clients   = set()

    def _broadcast(self, message: str):
        """Send to all connected WebSocket clients (thread-safe via loop)."""
        import asyncio
        for ws, loop in list(self._clients):
            asyncio.run_coroutine_threadsafe(ws.send(message), loop)

    def start(self):
        """Start the WebSocket server (blocking)."""
        try:
            import websockets
            import asyncio
        except ImportError:
            print("❌ websockets not installed.  pip install websockets")
            return

        import asyncio

        self.detector.ws_broadcast = self._broadcast

        async def handler(websocket):
            loop = asyncio.get_event_loop()
            self._clients.add((websocket, loop))
            print(f"🌐 Browser connected ({websocket.remote_address})")
            try:
                async for raw in websocket:
                    try:
                        msg = json.loads(raw)
                    except json.JSONDecodeError:
                        continue

                    action = msg.get("action")

                    if action == "start":
                        if self._vad_thread and self._vad_thread.is_alive():
                            continue   # already running
                        self.detector._stop_event.clear()
                        self._vad_thread = threading.Thread(
                            target=self.detector.listen_continuously,
                            daemon=True,
                        )
                        self._vad_thread.start()
                        await websocket.send(json.dumps({"type": "status", "state": "listening"}))
                        print("▶️  VAD started by browser")

                    elif action == "stop":
                        self.detector.stop()
                        if self._vad_thread:
                            self._vad_thread.join(timeout=3)
                        await websocket.send(json.dumps({"type": "status", "state": "idle"}))
                        print("⏹  VAD stopped by browser")

            except Exception as exc:
                print(f"WS error: {exc}")
            finally:
                self._clients.discard((websocket, loop))

        async def main():
            print(f"🌐 WebSocket server → ws://{self.host}:{self.port}")
            async with websockets.serve(handler, self.host, self.port):
                await asyncio.Future()   # run forever

        asyncio.run(main())


# ── CLI entry points ──────────────────────────────────────────────────────────

def run_terminal_demo():
    """Pure terminal demo — no browser needed."""
    detector = VoiceActivityDetector(rms_threshold=80, silence_timeout=1.8)

    def on_text(text: str):
        print(f"\n🎯 → AI Tutor: {text}\n")

    try:
        detector.listen_continuously(callback=on_text)
    except KeyboardInterrupt:
        detector.stop()


def run_ws_server(port: int = 8765):
    """Start WebSocket server for the browser UI."""
    server = VoiceWebSocketServer(port=port)
    server.start()


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--ws":
        port = int(sys.argv[2]) if len(sys.argv) > 2 else 8765
        run_ws_server(port)
    else:
        run_terminal_demo()