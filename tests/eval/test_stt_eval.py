import json
from pathlib import Path

import pytest

from cpsagent.eval import stt as ev
from cpsagent.ui.stt import FakeTranscriber


def test_normalize_and_word_errors():
    assert ev.normalize("Abbassa le tapparelle dell'ufficio.", "it") == [
        "abbassa", "le", "tapparelle", "dell", "ufficio",
    ]  # fmt: skip
    assert ev.normalize("Set it to 70%", "en") == ["set", "it", "to", "70", "percent"]
    assert ev.word_errors(["a", "b", "c"], ["a", "x", "c", "d"]) == 2  # 1 sub + 1 ins
    assert ev.word_errors(["a", "b"], []) == 2


def test_stt_set_uses_only_dev_requests_and_new_sentences():
    items = [json.loads(line) for line in ev.SET_FILE.open(encoding="utf-8")]
    requests = [json.loads(line) for line in ev.REQUESTS.open(encoding="utf-8")]
    ev.check_set(items, requests)  # raises on a test sentence
    assert sum(i["language"] == "en" for i in items) == 10
    assert sum(i["language"] == "it" for i in items) == 10


def test_check_set_rejects_a_test_sentence():
    test = {"id": "t1", "split": "test", "language": "en", "text": "Dim the lamp to 40 percent"}
    requests = [test]
    new = [{"id": "s1", "language": "en", "text": "please dim the lamp to 40 now", "source": "new"}]
    with pytest.raises(ValueError):
        ev.check_set(new, requests)


def test_measure_and_table_offline(tmp_path: Path):
    items = [
        {"id": "a", "language": "en", "voice": "v", "text": "turn on the light", "source": "new"},
        {"id": "b", "language": "it", "voice": "v", "text": "accendi la luce", "source": "new"},
    ]
    for i in items:
        (tmp_path / f"{i['id']}.wav").write_bytes(b"")  # exists: `say` is not called
    fake = FakeTranscriber(
        {
            str(tmp_path / "a.wav"): ("Turn on the light.", "en"),
            str(tmp_path / "b.wav"): ("Accendi la luce!", "en"),
        },  # fmt: skip
        duration_ms=1000,
    )
    clips = ev.measure(fake, items, tmp_path)
    assert [c["wordErrors"] for c in clips] == [0, 0]
    header, rows = ev.table(clips)
    by_lang = {r[0]: dict(zip(header, r, strict=True)) for r in rows}
    assert by_lang["auto all"]["WER"] == "0.0%"
    assert by_lang["auto it"]["language detected"] == "0/1"  # wrong detection is counted


def test_forced_mode_passes_the_reference_language(tmp_path: Path):
    item = {"id": "a", "language": "it", "voice": "v", "text": "fai più caldo", "source": "new"}
    (tmp_path / "a.wav").write_bytes(b"")
    fake = FakeTranscriber({str(tmp_path / "a.wav"): ("fai più caldo", "es")})
    clips = [c for m in ev.MODES for c in ev.measure(fake, [item], tmp_path, m)]
    assert fake.calls == [(str(tmp_path / "a.wav"), None), (str(tmp_path / "a.wav"), "it")]
    assert [(c["mode"], c["detectedLanguage"]) for c in clips] == [("auto", "es"), ("forced", "it")]


def test_recorded_clip_must_exist(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        ev.audio_path({"id": "rec-01", "language": "en", "text": "x"}, tmp_path)


def test_recorded_set_is_new_balanced_and_has_numbers():
    set_file, _ = ev.SOURCES["recorded"]
    items = [json.loads(line) for line in set_file.open(encoding="utf-8")]
    ev.check_set(items, [json.loads(line) for line in ev.REQUESTS.open(encoding="utf-8")])
    for lang in ("en", "it"):
        texts = [i["text"] for i in items if i["language"] == lang]
        assert len(texts) == 10
        assert sum(any(ch.isdigit() for ch in t) for t in texts) >= 2
    assert all(set(i) == {"id", "language", "text"} for i in items)  # text only, no audio


def test_compare_puts_each_source_and_mode_on_one_row(tmp_path: Path):
    item = {"id": "a", "language": "en", "text": "turn on the light"}
    (tmp_path / "a.wav").write_bytes(b"")
    fake = FakeTranscriber({str(tmp_path / "a.wav"): ("turn on the night", "en")})
    run = tmp_path / "run"
    run.mkdir()
    (run / "run.json").write_text(json.dumps({"runId": "r1", "source": "recorded"}))
    clips = [c for m in ev.MODES for c in ev.measure(fake, [item], tmp_path, m)]
    (run / "clips.jsonl").write_text("\n".join(json.dumps(c) for c in clips))
    ev.compare([run], tmp_path / "cmp")
    rows = (tmp_path / "cmp.csv").read_text().splitlines()
    assert [r.split(",")[0] for r in rows[1:]] == ["recorded auto", "recorded forced"]
    assert rows[1].split(",")[2:4] == ["25.0%", "-"]  # WER EN, no Italian clip
