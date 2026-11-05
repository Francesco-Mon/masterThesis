"""SpeechToText: the one interface the UI and the STT evaluation call.

Model loading happens in the implementation's constructor, never in `transcribe`,
so `transcribe_ms` measures only the transformation audio -> text (load time is
recorded separately in `load_s`, like the embedding model's).
"""

import re
import time
from typing import Literal, Protocol

from pydantic import BaseModel, Field

MODEL_ID = "Systran/faster-whisper-small"
MODEL_REVISION = "536b0662742c02347bc0e980a01041f333bce120"  # Hugging Face commit, 4 Nov 2026
COMPUTE_TYPE = "int8"  # CTranslate2 runs on the CPU only on Apple Silicon; int8 is its fastest type
# Fixed decoding: temperature 0 without fallback, so the same audio gives the same text.
DECODING = {"beam_size": 5, "temperature": 0.0, "vad_filter": False}

# Outcome check. Whisper can fall into a repetition loop on short clips (seen with
# automatic language detection on rec-01/rec-08 of the STT measurement): over 100 characters for
# 2-3 s of speech. Normal transcripts of the 80 measured clips stay below 22 chars/s.
MAX_CHARS_PER_S = 25.0
CHAR_SLACK = 20  # very short clips: a few words in under a second
_REPEATED = re.compile(r"(.{1,4})\1{7,}")  # a 1-4 character unit, 8 or more times in a row


class Transcription(BaseModel):
    text: str
    language: str = Field(description="ISO 639-1 code, detected or forced (en, it)")
    language_probability: float | None = Field(default=None, ge=0, le=1)
    audio_duration_ms: float = Field(ge=0)
    transcribe_ms: float = Field(ge=0, description="wall time of transcribe(), load excluded")
    # False: the output looked degenerate and `text` is empty; callers must not use it
    reliable: bool = True
    unreliable_reason: Literal["too_long", "repetition"] | None = None


def check_outcome(t: Transcription) -> Transcription:
    """Replace a degenerate transcript with an empty, unreliable one."""
    if len(t.text) > MAX_CHARS_PER_S * t.audio_duration_ms / 1000 + CHAR_SLACK:
        reason = "too_long"
    elif _REPEATED.search(t.text):
        reason = "repetition"
    else:
        return t
    return t.model_copy(update={"text": "", "reliable": False, "unreliable_reason": reason})


class SpeechToText(Protocol):
    id: str  # model and revision, recorded with every measurement

    def transcribe(self, audio_path: str, language: str | None = None) -> Transcription:
        """`language=None` lets the model detect it; "en"/"it" forces it."""
        ...


class FasterWhisperTranscriber:
    """Local Whisper (faster-whisper / CTranslate2) on CPU. Needs the `ui` extra; the
    first use downloads the model (about 484 MB) into the Hugging Face cache.
    `model` lets tests inject an object with the same `transcribe` as WhisperModel."""

    def __init__(self, model=None, model_id: str = MODEL_ID, revision: str = MODEL_REVISION):
        start = time.perf_counter()
        if model is None:
            from faster_whisper import WhisperModel

            model = WhisperModel(
                model_id, device="cpu", compute_type=COMPUTE_TYPE, revision=revision
            )
        self._model = model
        self.load_s = time.perf_counter() - start
        self.id = f"{model_id}@{revision}"

    def transcribe(self, audio_path: str, language: str | None = None) -> Transcription:
        start = time.perf_counter()
        segments, info = self._model.transcribe(audio_path, language=language, **DECODING)
        # `segments` is a lazy generator: decoding happens while it is consumed.
        text = " ".join(s.text.strip() for s in segments).strip()
        elapsed_ms = (time.perf_counter() - start) * 1000
        return check_outcome(
            Transcription(
                text=text,
                language=info.language,
                language_probability=info.language_probability,
                audio_duration_ms=info.duration * 1000,
                transcribe_ms=elapsed_ms,
            )
        )


class FakeTranscriber:
    """Deterministic, offline: returns the scripted text for each audio path."""

    id = "fake"

    def __init__(self, script: dict[str, tuple[str, str]], duration_ms: float = 1000.0):
        self.script = script  # audio path -> (text, language)
        self.duration_ms = duration_ms
        self.calls: list[tuple[str, str | None]] = []

    def transcribe(self, audio_path: str, language: str | None = None) -> Transcription:
        self.calls.append((audio_path, language))
        text, detected = self.script[audio_path]
        return check_outcome(
            Transcription(
                text=text,
                language=language or detected,
                audio_duration_ms=self.duration_ms,
                transcribe_ms=0.0,
            )
        )
