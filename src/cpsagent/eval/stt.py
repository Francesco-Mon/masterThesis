"""Speech-to-text measurement: WER and latency, separate from grounding.

Run:     python -m cpsagent.eval.stt [--source synthetic|recorded]  (results/stt_<ts>_<source>/)
Rebuild: python -m cpsagent.eval.stt --report results/stt_<ts>_<source>
Compare: python -m cpsagent.eval.stt --compare RUN... --out results/stt_comparison

Every run transcribes each clip twice: language detected (`auto`, the UI default) and
language forced to the reference one (`forced`).
- synthetic: clips synthesised with the macOS `say` command from data/stt_set.jsonl
  (dev-split requests and new sentences, never test ones; checked by `check_set`)
  into data/stt_audio/ (git-ignored, regenerated on a miss). Synthetic speech is clean
  and has no noise or accent: the WER is a best case, not the one of a real user.
- recorded: the author's voice, recorded with `python -m cpsagent.ui.record_clips`
  from data/stt_recorded_set.jsonl into data/stt_recorded/ (git-ignored).
"""

import argparse
import csv
import json
import platform
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from .report import percentile

SOURCES = {  # source -> (sentence file, audio folder)
    "synthetic": (Path("data/stt_set.jsonl"), Path("data/stt_audio")),
    "recorded": (Path("data/stt_recorded_set.jsonl"), Path("data/stt_recorded")),
}
SET_FILE, AUDIO_DIR = SOURCES["synthetic"]
REQUESTS = Path("data/requests.jsonl")
MODES = ("auto", "forced")

# "%" is spoken as a word; Whisper may write either form.
_PERCENT = {"en": " percent", "it": " per cento"}


def normalize(text: str, language: str) -> list[str]:
    """Lowercase words, apostrophes split ("dell'ufficio" -> dell ufficio), punctuation
    dropped. Numbers are compared as written (the references use digits)."""
    text = text.lower().replace("%", _PERCENT.get(language, " percent"))
    text = re.sub(r"['’]", " ", text)
    return re.sub(r"[^\w\s]", " ", text).split()


def word_errors(ref: list[str], hyp: list[str]) -> int:
    """Levenshtein distance over words: substitutions + deletions + insertions."""
    prev = list(range(len(hyp) + 1))
    for i, r in enumerate(ref, 1):
        cur = [i]
        for j, h in enumerate(hyp, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (r != h)))
        prev = cur
    return prev[-1]


def _ngrams(words: list[str], n: int) -> set[tuple[str, ...]]:
    return {tuple(words[i : i + n]) for i in range(len(words) - n + 1)}


def check_set(items: list[dict], requests: list[dict]) -> None:
    """Dev sources must be dev requests with the same text; new sentences (no source,
    or "new") must not share a 4-word sequence with any test request (or equal one)."""
    by_id = {r["id"]: r for r in requests}
    test = [normalize(r["text"], r["language"]) for r in requests if r["split"] == "test"]
    test_grams = set().union(*(_ngrams(w, 4) for w in test))
    for it in items:
        if it.get("source", "new") != "new":
            src = by_id[it["source"]]
            if src["split"] != "dev" or src["text"] != it["text"]:
                raise ValueError(f"{it['id']}: source {it['source']} is not the dev text")
            continue
        words = normalize(it["text"], it["language"])
        if words in test or _ngrams(words, 4) & test_grams:
            raise ValueError(f"{it['id']}: overlaps a test request")


def synthesize(item: dict, audio_dir: Path) -> Path:
    path = audio_dir / f"{item['id']}.wav"
    if not path.exists():
        audio_dir.mkdir(parents=True, exist_ok=True)
        cmd = ["say", "-v", item["voice"], "-o", str(path), "--data-format=LEI16@16000"]
        subprocess.run([*cmd, item["text"]], check=True)
    return path


def audio_path(item: dict, audio_dir: Path) -> Path:
    """Synthetic items (with a voice) are synthesised on a miss; recorded ones must exist."""
    if "voice" in item:
        return synthesize(item, audio_dir)
    path = audio_dir / f"{item['id']}.wav"
    if not path.exists():
        raise FileNotFoundError(f"{path}: record it with python -m cpsagent.ui.record_clips")
    return path


def measure(stt, items: list[dict], audio_dir: Path, mode: str = "auto") -> list[dict]:
    clips = []
    for it in items:
        language = it["language"] if mode == "forced" else None
        t = stt.transcribe(str(audio_path(it, audio_dir)), language=language)
        ref = normalize(it["text"], it["language"])
        errors = word_errors(ref, normalize(t.text, it["language"]))
        clips.append(
            {
                **it,
                "mode": mode,
                "transcript": t.text,
                "reliable": t.reliable,
                "detectedLanguage": t.language,
                "languageProbability": t.language_probability,
                "audioMs": round(t.audio_duration_ms, 1),
                "transcribeMs": round(t.transcribe_ms, 1),
                "rtf": round(t.transcribe_ms / t.audio_duration_ms, 3),
                "refWords": len(ref),
                "wordErrors": errors,
            }
        )
    return clips


def _ms(x: float | None) -> str:
    return "-" if x is None else f"{x:.0f}"


def _wer(cs: list[dict]) -> str:
    return f"{sum(c['wordErrors'] for c in cs) / sum(c['refWords'] for c in cs):.1%}" if cs else "-"


HEADER = [
    "group", "clips", "WER", "exact clips", "language detected", "audio ms (mean)",
    "p50 ms", "p95 ms", "RTF p50", "RTF p95",
]  # fmt: skip


def _row(label: str, cs: list[dict]) -> list[str]:
    ms = [c["transcribeMs"] for c in cs]
    rtf = [c["rtf"] for c in cs]
    return [
        label,
        str(len(cs)),
        _wer(cs),
        f"{sum(c['wordErrors'] == 0 for c in cs)}/{len(cs)}",
        f"{sum(c['detectedLanguage'] == c['language'] for c in cs)}/{len(cs)}",
        _ms(sum(c["audioMs"] for c in cs) / len(cs)),
        _ms(percentile(ms, 50)),
        _ms(percentile(ms, 95)),
        f"{percentile(rtf, 50):.2f}",
        f"{percentile(rtf, 95):.2f}",
    ]


def _mode(c: dict) -> str:
    return c.get("mode", "auto")  # the first synthetic run had no forced pass


def table(clips: list[dict]) -> tuple[list[str], list[list[str]]]:
    """Per mode: one row per language, then all clips."""
    groups = []
    for mode in MODES:
        cs = [c for c in clips if _mode(c) == mode]
        groups += [
            (f"{mode} {lang}", [c for c in cs if c["language"] == lang]) for lang in ("en", "it")
        ]
        groups.append((f"{mode} all", cs))
    return HEADER, [_row(label, cs) for label, cs in groups if cs]


# Alice is the only Italian voice of the default macOS install that is not one of the
# older, more robotic voices (Eddy, Flo, Reed, Sandy, ...); errors concentrate on those.
REFERENCE_VOICE = "Alice"


def voice_table(clips: list[dict]) -> tuple[list[str], list[list[str]]]:
    """Per mode: Italian Alice vs the other Italian voices, then one row per other voice."""
    groups = []
    for mode in MODES:
        cs = [c for c in clips if _mode(c) == mode and "voice" in c]
        it = [c for c in cs if c["language"] == "it"]
        groups += [
            (f"{mode} it {REFERENCE_VOICE}", [c for c in it if c["voice"] == REFERENCE_VOICE]),
            (f"{mode} it other voices", [c for c in it if c["voice"] != REFERENCE_VOICE]),
        ]
        for lang, voice in sorted(
            {(c["language"], c["voice"]) for c in cs} - {("it", REFERENCE_VOICE)}
        ):
            groups.append(
                (
                    f"{mode} {lang} {voice}",
                    [c for c in cs if (c["language"], c["voice"]) == (lang, voice)],
                )
            )
    return HEADER, [_row(label, cs) for label, cs in groups if cs]


NOTE = {
    "synthetic": "**The audio is synthetic (macOS `say`): clean, no noise, no accent, so "
    "these figures are optimistic.**",
    "recorded": "**The audio is the author's own voice (one speaker, laptop microphone, quiet "
    "room, sentences read from the screen): one speaker is not a population.**",
}
METHOD = (
    "WER = word-level edit distance / reference words (corpus level, after lowercasing and "
    "dropping punctuation). auto = language detected by the model; forced = reference "
    "language passed to transcribe(). Latency = wall time of transcribe(), model loading and "
    "one warm-up clip excluded; RTF = latency / audio duration."
)


def write_reports(out: Path) -> None:
    meta = json.loads((out / "run.json").read_text())
    source = meta.get("source", "synthetic")
    clips = [json.loads(line) for line in (out / "clips.jsonl").open(encoding="utf-8")]
    tables = [("Per language", *table(clips))]
    if source == "synthetic":
        tables.append(("Per voice", *voice_table(clips)))
    md = [f"# STT {meta['runId']}", "", f"{meta['model']}, compute_type={meta['computeType']}, "
          f"{meta['machine']}, load {meta['loadS']:.1f} s (excluded)", "", METHOD, "",
          NOTE[source], ""]  # fmt: skip
    for title, header, rows in tables:
        md += [f"## {title}", "", "| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
        md += ["| " + " | ".join(r) + " |" for r in rows]
        md += [""]
    md += ["## Clips", "", "| id | mode | voice | reference | transcript | errors | ms |"]
    md += ["|---" * 7 + "|"]
    md += [
        f"| {c['id']} | {_mode(c)} | {c.get('voice', 'author')} | {c['text']} | "
        f"{c['transcript']} | {c['wordErrors']}/{c['refWords']} | {c['transcribeMs']:.0f} |"
        for c in clips
    ]
    (out / "summary.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    with (out / "summary.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["table", *HEADER])
        for title, _, rows in tables:
            w.writerows([title, *r] for r in rows)


COMPARE_HEADER = [
    "condition", "clips", "WER EN", "WER IT", "language detected", "p50 ms", "p95 ms",
    "RTF p50", "RTF p95", "run",
]  # fmt: skip


def compare(runs: list[Path], out: Path) -> None:
    """One row per (source, mode) of the given runs: the four STT conditions
    (synthetic/recorded x auto/forced)."""
    rows = []
    for run in runs:
        meta = json.loads((run / "run.json").read_text())
        clips = [json.loads(line) for line in (run / "clips.jsonl").open(encoding="utf-8")]
        for mode in MODES:
            cs = [c for c in clips if _mode(c) == mode]
            if not cs:
                continue
            r = _row("", cs)
            en = [c for c in cs if c["language"] == "en"]
            it = [c for c in cs if c["language"] == "it"]
            label = f"{meta.get('source', 'synthetic')} {mode}"
            rows.append([label, r[1], _wer(en), _wer(it), r[4], *r[6:], meta["runId"]])
    md = ["# STT comparison", "", METHOD, "", NOTE["synthetic"], "", NOTE["recorded"], "",
          "| " + " | ".join(COMPARE_HEADER) + " |", "|" + "---|" * len(COMPARE_HEADER)]  # fmt: skip
    md += ["| " + " | ".join(r) + " |" for r in rows]
    out.with_suffix(".md").write_text("\n".join(md) + "\n", encoding="utf-8")
    with out.with_suffix(".csv").open("w", newline="") as f:
        csv.writer(f).writerows([COMPARE_HEADER, *rows])


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--source", choices=SOURCES, default="synthetic")
    p.add_argument("--report", type=Path, help="rebuild the tables of a saved run")
    p.add_argument("--compare", type=Path, nargs="+", help="saved runs to put in one table")
    p.add_argument("--out", type=Path, default=Path("results/stt_comparison"))
    args = p.parse_args(argv)
    if args.report:
        write_reports(args.report)
        print((args.report / "summary.md").read_text())
        return 0
    if args.compare:
        compare(args.compare, args.out)
        print(args.out.with_suffix(".md").read_text())
        return 0

    from cpsagent.ui.stt import COMPUTE_TYPE, DECODING, FasterWhisperTranscriber

    set_file, audio_dir = SOURCES[args.source]
    items = [json.loads(line) for line in set_file.open(encoding="utf-8")]
    check_set(items, [json.loads(line) for line in REQUESTS.open(encoding="utf-8")])
    for it in items:
        audio_path(it, audio_dir)  # fail before loading the model if a clip is missing
    stt = FasterWhisperTranscriber()
    stt.transcribe(str(audio_path(items[0], audio_dir)))  # warm-up, not measured
    clips = [c for mode in MODES for c in measure(stt, items, audio_dir, mode)]

    now = datetime.now(UTC)
    run_id = f"stt_{now:%Y%m%d-%H%M%S}_{args.source}"
    out = Path("results") / run_id
    out.mkdir(parents=True)
    meta = {
        "runId": run_id,
        "date": now.isoformat(timespec="seconds"),
        "source": args.source,
        "model": stt.id,
        "computeType": COMPUTE_TYPE,
        "decoding": DECODING,
        "loadS": round(stt.load_s, 2),
        "machine": f"{platform.machine()} macOS {platform.mac_ver()[0]}",
        "set": str(set_file),
    }
    (out / "run.json").write_text(json.dumps(meta, indent=2) + "\n")
    with (out / "clips.jsonl").open("w", encoding="utf-8") as f:
        for c in clips:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    write_reports(out)
    print((out / "summary.md").read_text())
    return 0


if __name__ == "__main__":
    sys.exit(main())
