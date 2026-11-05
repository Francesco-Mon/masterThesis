"""Streamlit chat that drives the Orchestration Engine.

Run: streamlit run src/cpsagent/ui/app.py

Sidebar: grounder (keyword, embedding, LLM with a model id), speech language, start
zone, movement (go to a zone, or play a scripted path). Main: chat with text,
microphone or audio-file input; each turn shows transcript, zone, intent or
clarification, plan, commands and replies. Below: device states and the event chain
with its verification. The OpenRouter key stays in .env: the page only says whether it
is set.
"""

import os
import tempfile
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

from cpsagent.contracts import ToolResult
from cpsagent.ui.session import AgentSession, Turn, plan_status, result_summary

# LLM calls made from the page are demo traffic, not experimental data: they go to a
# git-ignored log instead of results/llm_calls.jsonl (which the evaluation runner writes).
UI_CALLS_LOG = Path("logs/ui_llm_calls.jsonl")
LANGUAGES = {"Italiano": "it", "English": "en", "Automatic (not recommended)": None}


@st.cache_resource
def zone_ids() -> list[str]:
    from cpsagent.environment import EmulatedEnvironment

    return [z.zone_id for z in EmulatedEnvironment().scenario.zones]


@st.cache_resource
def stt_model():
    from cpsagent.ui.stt import FasterWhisperTranscriber

    return FasterWhisperTranscriber()


@st.cache_resource
def embedder():
    from cpsagent.grounding.embedding import SentenceTransformerEmbedder

    return SentenceTransformerEmbedder()


def make_grounder(kind: str, model: str):
    if kind == "keyword":
        from cpsagent.grounding.keyword import KeywordGrounder

        return KeywordGrounder()
    if kind == "embedding":
        from cpsagent.grounding.embedding import EmbeddingGrounder

        return EmbeddingGrounder(embedder())
    from cpsagent.grounding.llm import LLMGrounder
    from cpsagent.grounding.openrouter import OpenRouterClient

    return LLMGrounder(OpenRouterClient(model, calls_log=UI_CALLS_LOG))


def sidebar() -> tuple[tuple, str | None]:
    st.sidebar.header("Agent")
    kind = st.sidebar.selectbox("Grounder", ["keyword", "embedding", "llm"])
    model = ""
    if kind == "llm":
        from cpsagent.grounding.llm import default_model

        model = st.sidebar.text_input("OpenRouter model", default_model())
        load_dotenv()
        key_set = bool(os.getenv("OPENROUTER_API_KEY"))
        st.sidebar.caption(f"OPENROUTER_API_KEY in .env: {'set' if key_set else 'MISSING'}")
    language = LANGUAGES[st.sidebar.selectbox("Speech language", list(LANGUAGES))]
    if language is None:
        st.sidebar.caption("Detection is unreliable on short commands (see the STT measurements).")
    zones = zone_ids()
    start = st.sidebar.selectbox("Start zone", zones, index=zones.index("hallway"))
    config = (kind, model, start)
    changed = st.session_state.get("config") != config
    if st.sidebar.button("New session") or changed or "agent" not in st.session_state:
        new_session(config)  # also retried while a failed grounder left no session
    return config, language


def new_session(config) -> None:
    kind, model, start = config
    if "agent" in st.session_state:
        st.session_state.agent.close()
    try:
        grounder = make_grounder(kind, model)
    except Exception as e:  # missing key or extra: show it, never the key itself
        st.session_state.pop("agent", None)
        st.session_state.config = config
        st.error(f"Grounder not available: {type(e).__name__}: {e}")
        st.stop()
    st.session_state.agent = AgentSession(grounder, start_zone=start)
    st.session_state.config = config


def movement(agent: AgentSession) -> None:
    st.sidebar.header("Movement")
    st.sidebar.caption(f"True position: {agent.position} (the agent only sees the estimate)")
    zones = [z.zone_id for z in agent.scenario.zones]
    target = st.sidebar.selectbox("Go to zone", zones, index=zones.index(agent.position))
    # A walk is computed from the current position but would be queued after the ticks
    # already queued, so the user would jump back at the end: finish the queue first.
    queued = agent.pending_ticks > 0
    if st.sidebar.button("Walk there", disabled=queued) and not queued:
        agent.walk_to(target)
        st.rerun()  # "True position" above was drawn before the walk
    if queued:
        st.sidebar.caption('Walk there is disabled while ticks are queued: press "To end" first.')
    path = st.sidebar.selectbox("Scripted path", list(agent.scenario.paths))
    # The queue changes below, after "True position" and "Walk there" were drawn: rerun
    # so that both always match the queue.
    if st.sidebar.button("Load path"):
        agent.load_path(path)
        st.rerun()
    if agent.pending_ticks:
        st.sidebar.caption(f"{agent.pending_ticks} ticks queued")
        c1, c2, c3 = st.sidebar.columns(3)
        for column, label, until in ((c1, "1 tick", "tick"), (c2, "Next zone", "zone"),
                                     (c3, "To end", "end")):  # fmt: skip
            if column.button(label):
                agent.advance(until)
                st.rerun()


def transcribe(audio_bytes: bytes, suffix: str, language: str | None):
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
        f.write(audio_bytes)
    try:
        return stt_model().transcribe(f.name, language=language)
    finally:
        Path(f.name).unlink(missing_ok=True)


def show_turn(turn: Turn) -> None:
    if turn.kind == "movement":
        if not turn.transitions:
            return
        with st.chat_message("assistant", avatar="🚶"):
            st.caption(f"User moved; estimated zone {turn.zone.zone_id if turn.zone else '-'}")
            show_details(turn)
        return
    with st.chat_message("user"):
        t = turn.transcript
        if t is None:
            st.write(turn.text)
        elif t.reliable:
            st.write(t.text)
            st.caption(f"transcribed ({t.language}, {t.transcribe_ms:.0f} ms for "
                       f"{t.audio_duration_ms:.0f} ms of audio)")  # fmt: skip
        else:
            st.warning(f"Transcription not reliable ({t.unreliable_reason}): no text sent")
    with st.chat_message("assistant"):
        st.write(turn.reply.message if turn.reply else "-")
        z = turn.zone
        st.caption(f"zone {z.zone_id} ({z.confidence:.2f})" if z else "zone unknown")
        st.caption(result_summary(turn))
        show_details(turn)


def show_details(turn: Turn) -> None:
    if turn.plan is not None:
        steps = [
            f"{s.device_id}.{s.command}" + (f"({s.value})" if s.value is not None else "")
            + f" [{status}]"
            for s, status in plan_status(turn)
        ]  # fmt: skip
        zone = turn.plan.valid_for.zone_id
        st.caption(f"plan (valid for {zone}): " + ("; ".join(steps) or "no steps"))
    for c in turn.commands:  # only rows with an action and a ToolResult (see Turn.commands)
        a, out = c.action.args, c.outcome
        result = out.state if out.ok else out.error
        st.caption(f"{c.action.operation}({a.device_id}, {a.command}) -> {result}")
    with st.expander(f"{len(turn.transitions)} transitions"):
        st.table(
            [
                {
                    "guard": t.guard.value,
                    "from": t.source.value,
                    "to": t.target.value,
                    "zone": t.zone.zone_id if t.zone else "",
                    "outcome": ""
                    if t.outcome is None or isinstance(t.outcome, ToolResult)
                    else str(t.outcome),
                }  # fmt: skip
                for t in turn.transitions
            ]
        )


def panels(agent: AgentSession) -> None:
    st.subheader("Devices")
    st.dataframe(agent.devices(), hide_index=True)
    st.subheader("Event log")
    report = agent.verify()
    if report.ok:
        st.success(f"Chain verified: {report.length} records, head {(report.head or '-')[:16]}")
    else:
        st.error(f"Chain NOT verified: {report.errors}")
    rows = []
    for position, e in enumerate(agent.events(), 1):
        r = e.get("record")  # None once erased: commitment and link stay (verifier)
        rows.append(
            {
                "seq": r["seq"] if r else position,
                "time": r["time"][11:19] if r else "",
                "guard": r["guard"] if r else "(erased)",
                "from": r["from"] if r else "",
                "to": r["to"] if r else "",
                "commitment": e["commitment"][:12],
                "link": e["link"][:12],
            }
        )
    st.dataframe(rows, hide_index=True)
    st.caption(f"Log file: {agent.log_path}")


def main() -> None:
    st.set_page_config(page_title="Person Agent", layout="wide")
    st.title("Person Agent")
    (kind, _, _), language = sidebar()
    agent: AgentSession = st.session_state.agent
    movement(agent)

    st.caption(f'Grounder: {kind}. Say or type a request, e.g. "I want to walk in the light".')
    # An error raised while handling audio is shown after the rerun that empties the widget.
    if notice := st.session_state.pop("audio_error", None):
        st.error(notice)
    # A widget is emptied by giving it a new key: each sent recording or upload bumps the
    # counter of its widget, and the page reruns (chat and panels live in the AgentSession,
    # so they survive the rerun).
    rounds = st.session_state.setdefault("audio_rounds", {"mic": 0, "upload": 0})
    chat, side = st.columns([3, 2])
    with side:
        audio = st.audio_input("Microphone", key=f"mic_{rounds['mic']}")
        upload = st.file_uploader("Audio file", type=["wav", "mp3", "m4a", "ogg", "flac"],
                                  key=f"upload_{rounds['upload']}")  # fmt: skip
    text = st.chat_input("Type a request")

    # chat_input returns its text on one rerun only. Each recording and each upload is
    # also sent once, identified by its file_id (new for every recording or upload, even
    # with the same content): kept as a guard besides the emptying. One set for both
    # widgets: a single "last sent" id was overwritten by the other widget, and the
    # upload was sent again after a recording.
    # Errors of a backend (OpenRouter auth or budget, an audio file that cannot be decoded)
    # are shown, not raised; the log written so far stays on disk.
    sent: set[str] = st.session_state.setdefault("sent_audio_ids", set())
    emptied = False
    try:
        if text:
            agent.say(text, language or "en")
        for name, widget, suffix in (("mic", audio, ".wav"), ("upload", upload, None)):
            if widget is not None and widget.file_id not in sent:
                sent.add(widget.file_id)  # before transcribing: a failing file is not retried
                rounds[name] += 1  # emptied on the rerun below, even if what follows fails
                emptied = True
                t = transcribe(widget.getvalue(), suffix or Path(widget.name).suffix, language)
                spoken = language or (t.language if t.language in ("en", "it") else "en")
                agent.say(t.text if t.reliable else "", spoken, transcript=t)
    except Exception as e:
        # the engine stops in the middle of the request (e.g. AuthError propagates by
        # design), so this session cannot take another one: the next rerun starts anew
        message = f"Request not handled: {type(e).__name__}: {e}. A new session will start."
        st.error(message)
        if emptied:
            st.session_state.audio_error = message
        agent.close()
        del st.session_state["agent"]
    if emptied:
        st.rerun()  # outside the try: RerunException is a BaseException anyway

    with chat:
        for turn in agent.turns:
            show_turn(turn)
    with side:
        panels(agent)


if __name__ == "__main__":  # streamlit runs the file as __main__
    main()
