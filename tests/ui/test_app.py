"""The Streamlit page, headless (streamlit.testing), keyword grounder: no model, no network."""

from pathlib import Path

import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402
from streamlit.testing.v1.errors import AppTestError  # noqa: E402

APP = Path(__file__).parents[2] / "src/cpsagent/ui/app.py"


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # logs/ of the session go to a temporary folder
    return AppTest.from_file(str(APP), default_timeout=30).run()


def captions(app) -> str:
    return " ".join(c.value for c in app.caption)


def test_page_starts_with_a_verified_empty_chain(app):
    assert not app.exception
    assert any("Chain verified: 0 records" in s.value for s in app.success)
    labels = {s.label for s in app.sidebar.selectbox}
    assert {"Grounder", "Speech language", "Start zone", "Go to zone"} <= labels
    language = next(s for s in app.sidebar.selectbox if s.label == "Speech language")
    assert language.value == "Italiano"  # forced language by default, automatic last


def test_text_request_drives_the_engine_and_the_log(app):
    app.chat_input[0].set_value("I want to walk in the light").run()
    assert not app.exception
    assert "intent: action=activate" in captions(app)
    assert "invokeCommand(lamp_hallway, on)" in captions(app)
    assert any("Chain verified" in s.value and "0 records" not in s.value for s in app.success)
    go_to = next(s for s in app.sidebar.selectbox if s.label == "Go to zone")
    go_to.set_value("office")
    next(b for b in app.sidebar.button if b.label == "Walk there").click().run()
    assert not app.exception
    assert "invokeCommand(lamp_office, on)" in captions(app)


def say(app, text: str):
    app.chat_input[0].set_value(text).run()
    assert not app.exception, app.exception
    return captions(app)


def test_clarification_then_many_commands_render(app):
    """Manual bug of 5 Nov: the last row (T8, Observe -> Perceive) carries the last
    ToolResult but no action; the page crashed reading `action.args`."""
    assert "clarification:ambiguous_target" in say(app, "spegni tutto")
    text = say(app, "spegni tutte le luci")
    for lamp in ("lamp_lobby", "lamp_hallway", "lamp_corridor", "lamp_kitchen"):
        assert f"invokeCommand({lamp}, off)" in text
        assert f"{lamp}.off [done]" in text  # full plan, not only the last step


def test_unsupported_request_then_walk_render(app):
    assert "unsupported:capability_absent" in say(app, "accendi la ventilazione")
    next(s for s in app.sidebar.selectbox if s.label == "Go to zone").set_value("kitchen")
    next(b for b in app.sidebar.button if b.label == "Walk there").click().run()
    assert not app.exception


def _unreliable_and_empty_turns():
    """Run by AppTest: the turns audio input produces, without a microphone."""
    import tempfile

    from cpsagent.grounding.keyword import KeywordGrounder
    from cpsagent.ui import app
    from cpsagent.ui.session import AgentSession
    from cpsagent.ui.stt import Transcription

    agent = AgentSession(KeywordGrounder(), log_dir=tempfile.mkdtemp())
    bad = Transcription(text="", language="en", audio_duration_ms=2000, transcribe_ms=900,
                        reliable=False, unreliable_reason="repetition")  # fmt: skip
    good = Transcription(text="accendi la luce", language="it", audio_duration_ms=1500,
                         transcribe_ms=700)  # fmt: skip
    agent.say("", "en", transcript=bad)
    agent.say("", "it")  # typed nothing understandable
    agent.say(good.text, "it", transcript=good)
    for turn in agent.turns:
        app.show_turn(turn)
    app.panels(agent)
    agent.close()


def test_unreliable_transcript_and_empty_text_render():
    at = AppTest.from_function(_unreliable_and_empty_turns, default_timeout=30).run()
    assert not at.exception, at.exception
    assert any("Transcription not reliable (repetition)" in w.value for w in at.warning)
    assert " ".join(c.value for c in at.caption).count("request_unintelligible") == 2
    assert any("Chain verified" in s.value for s in at.success)


def test_failed_grounder_is_shown_and_retried(tmp_path, monkeypatch):
    import cpsagent.grounding.keyword as keyword

    def broken(*args, **kwargs):
        raise RuntimeError("grounder extra missing")

    monkeypatch.setattr(keyword, "KeywordGrounder", broken)
    monkeypatch.chdir(tmp_path)
    at = AppTest.from_file(str(APP), default_timeout=30).run()
    assert not at.exception and "grounder extra missing" in at.error[0].value
    at.run()  # rerun without a session: retried, not a KeyError
    assert not at.exception and "grounder extra missing" in at.error[0].value


def test_grounder_error_during_a_request_is_shown(app, monkeypatch):
    from cpsagent.grounding.keyword import KeywordGrounder
    from cpsagent.grounding.openrouter import AuthError

    def denied(self, request):
        raise AuthError("401 from OpenRouter")

    monkeypatch.setattr(KeywordGrounder, "ground", denied)
    app.chat_input[0].set_value("accendi la luce").run()
    assert not app.exception
    assert any("AuthError" in e.value and "new session" in e.value for e in app.error)
    monkeypatch.undo()
    app.run()
    assert not app.exception and any("Chain verified" in s.value for s in app.success)


def _erased_record_panel():
    import tempfile

    from cpsagent.grounding.keyword import KeywordGrounder
    from cpsagent.ui import app
    from cpsagent.ui.session import AgentSession

    agent = AgentSession(KeywordGrounder(), log_dir=tempfile.mkdtemp())
    agent.say("accendi la luce", "it")
    agent.log.flush()
    agent.store.erase(2)  # record and salt deleted, commitment and link kept
    app.panels(agent)
    agent.close()


def test_erased_record_is_shown_in_the_event_panel():
    at = AppTest.from_function(_erased_record_panel, default_timeout=30).run()
    assert not at.exception, at.exception
    assert any("Chain verified" in s.value for s in at.success)  # erasure is not an error


def sidebar_button(app, label):
    return next(b for b in app.sidebar.button if b.label == label)


def test_walk_there_is_disabled_while_a_path_is_queued(app):
    """Manual finding of 5 Nov: a walk queued after a loaded path made the user jump back."""
    next(s for s in app.sidebar.selectbox if s.label == "Start zone").set_value("lobby").run()
    next(s for s in app.sidebar.selectbox if s.label == "Scripted path").set_value(
        "walk_in_the_light"
    )
    sidebar_button(app, "Load path").click().run()
    assert sidebar_button(app, "Walk there").disabled
    assert any('press "To end" first' in c.value for c in app.sidebar.caption)

    next(s for s in app.sidebar.selectbox if s.label == "Go to zone").set_value("kitchen")
    with pytest.raises(AppTestError, match="disabled"):  # a browser user cannot press it
        sidebar_button(app, "Walk there").click()
    sidebar_button(app, "To end").click().run()
    assert not app.exception
    assert any("True position: office" in c.value for c in app.sidebar.caption)  # path's end
    assert not sidebar_button(app, "Walk there").disabled
    next(s for s in app.sidebar.selectbox if s.label == "Go to zone").set_value("kitchen")
    sidebar_button(app, "Walk there").click().run()
    assert any("True position: kitchen" in c.value for c in app.sidebar.caption)


def test_ui_llm_calls_are_logged_outside_results(monkeypatch):
    """Experimental data stay in results/llm_calls.jsonl, written by the runner only."""
    pytest.importorskip("openai")
    from cpsagent.eval import run
    from cpsagent.grounding import openrouter
    from cpsagent.ui import app as page

    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key-not-used")  # no call is made
    ui = page.make_grounder("llm", "openai/gpt-oss-120b")
    assert ui.client._calls_log == Path("logs/ui_llm_calls.jsonl")
    assert page.UI_CALLS_LOG.parts[0] == "logs"  # git-ignored

    from types import SimpleNamespace

    from cpsagent.grounding.prompts import PROMPT_VERSION

    args = SimpleNamespace(grounder="llm", model="openai/gpt-oss-120b", provider=None,
                           no_cache=False, max_cost=None, temperature=0.0,
                           prompt=PROMPT_VERSION)  # fmt: skip
    _, client = run.make_grounder(args)  # what `python -m cpsagent.eval.run` builds
    assert client._calls_log == openrouter.DEFAULT_CALLS_LOG == Path("results/llm_calls.jsonl")


class EchoTranscriber:
    """Fake STT: the audio bytes are the text, so each input is recognisable in the chat."""

    calls: list[str] = []

    def transcribe(self, audio_path, language=None):
        from cpsagent.ui.stt import Transcription

        text = Path(audio_path).read_bytes().decode()
        EchoTranscriber.calls.append(text)
        return Transcription(text=text, language=language or "it", audio_duration_ms=1500,
                             transcribe_ms=1)  # fmt: skip


@pytest.fixture
def audio_app(tmp_path, monkeypatch):
    import streamlit as st

    import cpsagent.ui.stt as stt

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(stt, "FasterWhisperTranscriber", EchoTranscriber)
    EchoTranscriber.calls = []
    st.cache_resource.clear()  # stt_model() must build the fake, not reuse a cached model
    yield AppTest.from_file(str(APP), default_timeout=30).run()
    st.cache_resource.clear()


def requests_sent(app) -> list[str]:
    return [t.text for t in app.session_state["agent"].turns if t.kind != "movement"]


def test_uploaded_file_is_not_resent_by_a_microphone_recording(audio_app):
    """Manual bug of 5 Nov: a file left in the uploader was transcribed and sent again
    when a recording arrived, because one key remembered the last audio of both inputs."""
    audio_app.file_uploader[0].set_value(("a.wav", b"accendi la luce", "audio/wav")).run()
    audio_app.audio_input[0].set_value(("mic.wav", b"spegni la luce", "audio/wav")).run()
    assert not audio_app.exception, audio_app.exception
    assert requests_sent(audio_app) == ["accendi la luce", "spegni la luce"]
    assert EchoTranscriber.calls == ["accendi la luce", "spegni la luce"]


def test_recording_is_not_resent_by_an_upload_or_a_typed_request(audio_app):
    audio_app.audio_input[0].set_value(("mic.wav", b"accendi la luce", "audio/wav")).run()
    audio_app.file_uploader[0].set_value(("a.wav", b"spegni la luce", "audio/wav")).run()
    audio_app.chat_input[0].set_value("accendi la luce").run()
    sidebar_button(audio_app, "Walk there").click().run()  # a rerun with no new input
    assert not audio_app.exception, audio_app.exception
    assert requests_sent(audio_app) == ["accendi la luce", "spegni la luce", "accendi la luce"]
    assert EchoTranscriber.calls == ["accendi la luce", "spegni la luce"]


def test_typed_request_is_not_resent_by_audio_inputs(audio_app):
    audio_app.chat_input[0].set_value("accendi la luce").run()
    audio_app.file_uploader[0].set_value(("a.wav", b"spegni la luce", "audio/wav")).run()
    audio_app.audio_input[0].set_value(("mic.wav", b"accendi la luce", "audio/wav")).run()
    assert not audio_app.exception, audio_app.exception
    assert requests_sent(audio_app) == ["accendi la luce", "spegni la luce", "accendi la luce"]


def test_same_recording_content_twice_is_two_requests(audio_app):
    """Identity is the upload (file_id), not the bytes: saying the same thing twice, or
    uploading the same file again, is a new request."""
    audio_app.audio_input[0].set_value(("mic.wav", b"accendi la luce", "audio/wav")).run()
    audio_app.audio_input[0].set_value(("mic.wav", b"accendi la luce", "audio/wav")).run()
    assert requests_sent(audio_app) == ["accendi la luce", "accendi la luce"]


def chat_texts(app) -> str:
    return " ".join(m.value for m in app.markdown)


def test_audio_widgets_are_emptied_after_sending(audio_app):
    audio_app.audio_input[0].set_value(("mic.wav", b"accendi la luce", "audio/wav")).run()
    assert not audio_app.exception, audio_app.exception
    assert audio_app.audio_input[0].value is None  # ready for the next command
    audio_app.file_uploader[0].set_value(("a.wav", b"spegni la luce", "audio/wav")).run()
    assert not audio_app.exception, audio_app.exception
    assert audio_app.file_uploader[0].value is None
    # a second command from each emptied widget goes through
    audio_app.audio_input[0].set_value(("mic.wav", b"chiudi le tende", "audio/wav")).run()
    audio_app.file_uploader[0].set_value(("b.wav", b"accendi la luce", "audio/wav")).run()
    assert not audio_app.exception, audio_app.exception
    assert requests_sent(audio_app) == [
        "accendi la luce", "spegni la luce", "chiudi le tende", "accendi la luce",
    ]  # fmt: skip
    # chat, devices and event log keep their state across the reruns
    assert "invokeCommand(lamp_hallway, off)" in captions(audio_app)
    assert any("Chain verified" in s.value and "0 records" not in s.value
               for s in audio_app.success)  # fmt: skip
    assert len(audio_app.session_state["agent"].turns) == 4


def test_unreliable_or_failed_transcription_also_empties_the_widget(audio_app, monkeypatch):
    from cpsagent.ui.stt import Transcription

    def unreliable(self, audio_path, language=None):
        return Transcription(text="", language="it", audio_duration_ms=2000, transcribe_ms=1,
                             reliable=False, unreliable_reason="repetition")  # fmt: skip

    monkeypatch.setattr(EchoTranscriber, "transcribe", unreliable)
    audio_app.audio_input[0].set_value(("mic.wav", b"x", "audio/wav")).run()
    assert not audio_app.exception, audio_app.exception
    assert audio_app.audio_input[0].value is None
    assert any("Transcription not reliable" in w.value for w in audio_app.warning)

    def broken(self, audio_path, language=None):
        raise ValueError("cannot decode audio")

    monkeypatch.setattr(EchoTranscriber, "transcribe", broken)
    audio_app.file_uploader[0].set_value(("bad.ogg", b"x", "audio/ogg")).run()
    assert not audio_app.exception, audio_app.exception
    assert audio_app.file_uploader[0].value is None
    assert any("cannot decode audio" in e.value for e in audio_app.error)  # survives the rerun
    monkeypatch.undo()
    audio_app.run()  # the error is shown once, then the page is normal again
    assert not any("cannot decode audio" in e.value for e in audio_app.error)


def test_changing_language_or_grounder_after_an_audio_request(audio_app):
    audio_app.audio_input[0].set_value(("mic.wav", b"accendi la luce", "audio/wav")).run()
    next(s for s in audio_app.sidebar.selectbox if s.label == "Speech language").set_value(
        "English"
    ).run()
    assert not audio_app.exception and len(requests_sent(audio_app)) == 1  # same session
    audio_app.audio_input[0].set_value(("mic.wav", b"turn off the light", "audio/wav")).run()
    assert requests_sent(audio_app) == ["accendi la luce", "turn off the light"]
    assert audio_app.session_state["agent"].turns[-1].transcript.language == "en"
    next(s for s in audio_app.sidebar.selectbox if s.label == "Grounder").set_value("embedding")
    import cpsagent.grounding.embedding as embedding

    class NoModel:  # the real embedding model is not loaded in the offline suite
        def __init__(self, *a, **k):
            raise RuntimeError("embeddings extra not loaded in tests")

    with pytest.MonkeyPatch.context() as m:
        m.setattr(embedding, "SentenceTransformerEmbedder", NoModel)
        audio_app.run()
    assert not audio_app.exception and "embeddings extra" in audio_app.error[0].value
    next(s for s in audio_app.sidebar.selectbox if s.label == "Grounder").set_value("keyword").run()
    assert not audio_app.exception
    audio_app.audio_input[0].set_value(("mic.wav", b"accendi la luce", "audio/wav")).run()
    assert requests_sent(audio_app) == ["accendi la luce"]  # new session, widget works
