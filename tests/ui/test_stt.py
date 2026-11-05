import shutil
import subprocess
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from cpsagent.ui.stt import (
    DECODING,
    FakeTranscriber,
    FasterWhisperTranscriber,
    SpeechToText,
    Transcription,
    check_outcome,
)


class FakeWhisperModel:
    """Same `transcribe` shape as faster_whisper.WhisperModel: lazy segments + info."""

    def __init__(self, decode_s: float = 0.0):
        self.decode_s = decode_s
        self.kwargs = None

    def transcribe(self, audio, language=None, **kwargs):
        self.kwargs = {"language": language, **kwargs}

        def segments():
            time.sleep(self.decode_s)  # work happens while the generator is consumed
            yield SimpleNamespace(text=" it's too dark ")
            yield SimpleNamespace(text="here. ")

        info = SimpleNamespace(language=language or "en", language_probability=0.97, duration=1.5)
        return segments(), info


def test_wrapper_joins_segments_and_reports_metadata():
    stt: SpeechToText = FasterWhisperTranscriber(model=FakeWhisperModel())
    t = stt.transcribe("a.wav")
    assert t.text == "it's too dark here."
    assert (t.language, t.language_probability, t.audio_duration_ms) == ("en", 0.97, 1500.0)


def test_wrapper_forces_language_and_uses_fixed_decoding():
    fake = FakeWhisperModel()
    FasterWhisperTranscriber(model=fake).transcribe("a.wav", language="it")
    assert fake.kwargs == {"language": "it", **DECODING}
    assert DECODING["temperature"] == 0.0


def test_latency_covers_lazy_decoding_but_not_loading():
    stt = FasterWhisperTranscriber(model=FakeWhisperModel(decode_s=0.05))
    assert stt.load_s < 0.05  # injected model: nothing loaded
    assert stt.transcribe("a.wav").transcribe_ms >= 50


def test_fake_transcriber_is_scripted():
    fake = FakeTranscriber({"x.wav": ("fa buio qui", "it")})
    t = fake.transcribe("x.wav")
    assert (t.text, t.language) == ("fa buio qui", "it")
    assert fake.calls == [("x.wav", None)]


@pytest.mark.stt
@pytest.mark.skipif(shutil.which("say") is None, reason="needs the macOS `say` command")
def test_real_model_transcribes_english_and_italian(tmp_path):
    pytest.importorskip("faster_whisper")
    stt = FasterWhisperTranscriber()
    cases = [("Samantha", "turn on the light", "en"), ("Alice", "accendi la luce", "it")]
    for voice, sentence, lang in cases:
        wav = tmp_path / f"{lang}.wav"
        subprocess.run(
            ["say", "-v", voice, "-o", str(wav), "--data-format=LEI16@16000", sentence],
            check=True,
        )
        t = stt.transcribe(str(wav))
        assert t.language == lang
        assert "luce" in t.text.lower() if lang == "it" else "light" in t.text.lower()


def _t(text: str, ms: float = 2000.0) -> Transcription:
    return Transcription(text=text, language="en", audio_duration_ms=ms, transcribe_ms=1.0)


@pytest.mark.parametrize(
    "text, reason",
    [
        ("Po" + "ĺ" * 111, "too_long"),  # rec-08 in automatic mode (STT measurement)
        ("ని" + "కి" * 54, "too_long"),  # rec-01 in automatic mode
        ("lights " + "la" * 9, "repetition"),  # short, but a loop
    ],
)
def test_degenerate_transcript_is_unreliable_and_empty(text, reason):
    t = check_outcome(_t(text))
    assert (t.text, t.reliable, t.unreliable_reason) == ("", False, reason)


@pytest.mark.parametrize(
    "text, ms",
    [
        ("Brightened the hallway lamp to 80%.", 3508),
        ("It's getting chilly.", 930),  # the fastest measured clip, 21.6 chars/s
        ("Fai più caldo", 600),
        ("", 1000),
    ],
)
def test_normal_transcripts_pass(text, ms):
    assert check_outcome(_t(text, ms)).reliable


def test_fake_transcriber_applies_the_check():
    fake = FakeTranscriber({"x.wav": ("ab" * 40, "en")}, duration_ms=2000)
    t = fake.transcribe("x.wav")
    assert not t.reliable and t.text == ""


RECORDED = Path("data/stt_recorded")


@pytest.mark.stt
@pytest.mark.parametrize("clip", ["rec-01", "rec-08"])
def test_real_degenerate_clips_are_flagged_in_auto_mode(clip):
    """The two loops of the STT measurement, on the author's recordings
    (git-ignored: skipped elsewhere)."""
    path = RECORDED / f"{clip}.wav"
    if not path.exists():
        pytest.skip(f"{path} not recorded on this machine")
    stt = FasterWhisperTranscriber()
    auto = stt.transcribe(str(path))
    assert not auto.reliable and auto.text == ""
    assert stt.transcribe(str(path), language="en").reliable  # forced language: fine
