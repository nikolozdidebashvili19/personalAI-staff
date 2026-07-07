"""Wake word detection — no API needed.

Continuously records short chunks, transcribes them locally with whisper,
and activates full listening mode when the wake word ("hey aria") is heard.
Runs in a daemon thread started by main.py.
"""

import difflib
import time

from config.settings import settings
from core.logger import get_logger
from core.voice import listen, record, speak, transcribe

log = get_logger("wake_word")

CHUNK_SECONDS = 3.0


def _matches_wake_word(text: str) -> bool:
    text = text.lower().strip()
    if not text:
        return False
    wake = settings.wake_word
    if wake in text:
        return True
    # tolerate whisper mishearings ("hey area", "hey arya", …)
    words = text.split()
    for i in range(len(words) - len(wake.split()) + 1):
        candidate = " ".join(words[i : i + len(wake.split())])
        if difflib.SequenceMatcher(None, candidate, wake).ratio() > 0.75:
            return True
    return False


class WakeWordListener:
    def __init__(self, agent, speak_fn=None):
        self.agent = agent
        self.speak = speak_fn or speak
        self.running = True

    def run_forever(self) -> None:
        log.info('Wake word listener started ("%s")', settings.wake_word)
        while self.running:
            try:
                chunk = record(CHUNK_SECONDS)
                heard = transcribe(chunk)
                if _matches_wake_word(heard):
                    self._handle_activation(heard)
            except Exception as e:
                log.warning("Wake word loop error: %s", e)
                time.sleep(5)  # e.g. mic unplugged — back off, don't spin

    def _handle_activation(self, heard: str) -> None:
        # If the command came in the same breath ("hey aria, check my email"),
        # use the remainder directly; otherwise listen for the command.
        remainder = ""
        lower = heard.lower()
        idx = lower.find(settings.wake_word)
        if idx != -1:
            remainder = heard[idx + len(settings.wake_word):].strip(" ,.!?")

        if not remainder:
            self.speak("Yes?")
            remainder = listen(seconds=7.0)

        if not remainder:
            self.speak("I didn't catch that.")
            return

        log.info("Voice command: %s", remainder)
        try:
            reply = self.agent.run_turn(remainder)
        except Exception as e:
            reply = f"Sorry, something went wrong: {e}"
        self.speak(reply)
