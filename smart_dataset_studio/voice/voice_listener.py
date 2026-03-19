# voice/voice_listener.py
#
# VoiceListener — background thread that listens for voice commands.
#
# What this does:
#   Runs Vosk speech recognition on a background QThread.
#   Listens continuously for the four command words defined in config.py.
#   When a recognised word is heard, emits command_detected(word) signal.
#   The RecorderPanel connects this signal to its existing button handlers —
#   so voice commands and button clicks do exactly the same thing.
#
# What this does NOT do:
#   - No recording logic — that stays in GestureRecorder
#   - No UI interaction — communicates only via Qt Signal
#   - Does not run unless explicitly started via start() — zero CPU when off
#
# Cross-platform design:
#   Uses sounddevice (not pyaudio) for microphone access.
#   sounddevice installs cleanly on Ubuntu and Windows with a single
#   pip install — no compiler, no .whl file hunting.
#
# Dependencies:
#   pip install vosk sounddevice
#   Download Vosk model: see VOICE_MODEL_PATH in config.py
#
# Vosk fixed-vocabulary mode:
#   Instead of recognising all English words, Vosk is configured with
#   ONLY the four command words. This makes recognition faster and more
#   accurate — the model only has to distinguish 4 words, not 170,000.
#   A word like "start" is recognised reliably even in a noisy room.

import json
import logging
import os

import sounddevice as sd
from vosk import Model, KaldiRecognizer
from PyQt5.QtCore import QThread, pyqtSignal

from config import (
    VOICE_MODEL_PATH,
    VOICE_COMMANDS,
    VOICE_SAMPLE_RATE,
    VOICE_BLOCK_SIZE,
)

logger = logging.getLogger(__name__)


class VoiceListener(QThread):
    """
    Background thread for continuous voice command recognition.

    Inherits from QThread so it can emit Qt Signals safely to the main thread.
    Python's threading.Thread cannot emit Qt Signals.

    Signals:
        command_detected(str):  emitted when a command word is heard.
                                Carries the word in lowercase, e.g. "start".
        error_occurred(str):    emitted if the model is missing or mic fails.
                                RecorderPanel shows this to the user.

    Usage:
        listener = VoiceListener()
        listener.command_detected.connect(recorder_panel.on_voice_command)
        listener.error_occurred.connect(recorder_panel.on_voice_error)
        listener.start()    # begin listening
        listener.stop()     # stop listening cleanly
        listener.wait()     # block until thread exits
    """

    command_detected = pyqtSignal(str)   # carries command word e.g. "start"
    error_occurred   = pyqtSignal(str)   # carries human-readable error message

    def __init__(self):
        super().__init__()
        self._running = False

    # ── Public API ────────────────────────────────────────────────────

    def stop(self):
        """
        Signal the thread to stop cleanly.

        Sets _running = False. The run() loop checks this flag between
        audio blocks and exits. Call wait() after stop() to block until
        the thread has fully exited before doing anything else.
        """
        self._running = False

    # ── Thread entry point ────────────────────────────────────────────

    def run(self):
        """
        Main thread loop. Called automatically by QThread.start().
        Never call run() directly.

        Sequence:
          1. Validate model path — emit error and return if missing
          2. Load Vosk model
          3. Create KaldiRecognizer with fixed vocabulary
          4. Open sounddevice input stream
          5. Feed audio blocks to recogniser in a loop
          6. On each result, check if a command word was spoken
          7. If yes, emit command_detected signal
          8. Loop until _running = False
        """
        self._running = True

        # ── Step 1: Validate model path ───────────────────────────────
        # Check before trying to load — gives a clear, actionable error
        # instead of a confusing Vosk exception.
        if not os.path.isdir(VOICE_MODEL_PATH):
            msg = (
                f"Vosk model not found at: {VOICE_MODEL_PATH}\n\n"
                f"To fix this:\n"
                f"1. Download the model:\n"
                f"   https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip\n"
                f"2. Extract the zip file\n"
                f"3. Place the extracted folder at:\n"
                f"   {os.path.abspath(VOICE_MODEL_PATH)}\n\n"
                f"The folder should contain: am/, conf/, graph/, ivector/"
            )
            logger.error(msg)
            self.error_occurred.emit(msg)
            self._running = False
            return

        # ── Step 2: Load Vosk model ───────────────────────────────────
        # Model loading takes ~1-2 seconds on first run (reads from disk).
        # This is fine — it happens on the background thread, not the UI thread.
        try:
            model = Model(VOICE_MODEL_PATH)
        except Exception as e:
            msg = f"Failed to load Vosk model: {e}"
            logger.error(msg)
            self.error_occurred.emit(msg)
            self._running = False
            return

        # ── Step 3: Create recogniser with fixed vocabulary ───────────
        # The grammar parameter restricts recognition to only these words.
        # Vosk builds a tiny language model from just these 4 words —
        # far more accurate than full English for short command detection.
        # Format required by Vosk: JSON array string.
        grammar = json.dumps(VOICE_COMMANDS)
        recogniser = KaldiRecognizer(model, VOICE_SAMPLE_RATE, grammar)

        # ── Step 4 & 5: Open mic stream and process audio blocks ──────
        # sounddevice.RawInputStream reads raw bytes from the microphone.
        # dtype='int16' matches what Vosk expects — 16-bit signed integers.
        # blocksize controls how many samples per chunk (see config.py).
        try:
            with sd.RawInputStream(
                samplerate=VOICE_SAMPLE_RATE,
                blocksize=VOICE_BLOCK_SIZE,
                dtype='int16',
                channels=1,         # mono — Vosk requires single channel
            ) as mic_stream:

                logger.info("Voice listener started — listening for commands")

                while self._running:
                    # Read one block of audio from the microphone.
                    # This call blocks until VOICE_BLOCK_SIZE samples are ready.
                    # At 16000 Hz with blocksize 8000: blocks for ~0.5 seconds.
                    # That means _running is checked every ~0.5 seconds —
                    # acceptable latency for stopping the thread.
                    audio_block, _ = mic_stream.read(VOICE_BLOCK_SIZE)

                    # Feed block to Vosk recogniser.
                    # AcceptWaveform returns True when Vosk has a final result
                    # (silence detected after speech), False for partial results.
                    # We only act on final results — partial results are
                    # incomplete and unreliable for command detection.
                    if recogniser.AcceptWaveform(bytes(audio_block)):
                        result = json.loads(recogniser.Result())
                        self._handle_result(result)

        except sd.PortAudioError as e:
            msg = (
                f"Microphone error: {e}\n\n"
                f"Check that a microphone is connected and not in use by another app."
            )
            logger.error(msg)
            self.error_occurred.emit(msg)

        except Exception as e:
            msg = f"Voice listener error: {e}"
            logger.error(msg)
            self.error_occurred.emit(msg)

        finally:
            self._running = False
            logger.info("Voice listener stopped")

    # ── Private helpers ───────────────────────────────────────────────

    def _handle_result(self, result: dict):
        """
        Check a Vosk recognition result for command words and emit signal.

        Vosk returns a dict like: {"text": "start"} or {"text": ""}
        We check if the recognised text matches any of our command words.

        Why check 'in' rather than exact match?
            Sometimes Vosk returns multiple words if sounds bleed together,
            e.g. {"text": "hey start"}. Checking if the command word appears
            anywhere in the result handles this gracefully.
            With the fixed grammar, spurious extra words are rare but possible.

        Args:
            result: parsed JSON dict from Vosk recogniser
        """
        text = result.get("text", "").strip().lower()

        if not text:
            return   # empty result — silence or unrecognised sound

        # Check each command word against the recognised text
        for command in VOICE_COMMANDS:
            if command in text:
                logger.info(f"Voice command detected: '{command}' (from: '{text}')")
                self.command_detected.emit(command)
                return   # emit only the first matching command per result
