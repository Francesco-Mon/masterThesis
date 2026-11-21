"""Resources of the two models: the embedding interpreter (environment side) and the
speech-to-text model (person side).

Run: python -m cpsagent.bench.models [--repeats 3] [--out results/bench/models]

Each model is measured in a fresh Python process (`--child embedding|stt`), so that the
resident memory it adds is not mixed with another model's or with an earlier run's:
  - resident memory (RSS, read with `ps`) after the imports and before loading the model,
    and after loading it; the difference is the memory the loaded model adds. The peak RSS
    of the process (`getrusage`) is recorded too;
  - load time;
  - embedding: the interpreter as the environment builds it (`EmbeddingGrounder` with the
    pinned model, from the local cache), then CPU and wall time of one request's encoding
    over the English and Italian texts of data/load/requests.jsonl and
    data/qualitative/requests.jsonl, `--repeats` times;
  - speech-to-text: `ui.stt.FasterWhisperTranscriber` (faster-whisper small, int8 on CPU,
    the model of the UI), each recorded clip of data/stt_recorded/ transcribed with its
    language forced (as the UI does), `--repeats` times after one warm-up clip: CPU time of
    the process (CTranslate2 decodes on its own threads, so the process time is the right
    clock, not the thread's), wall time and the clip's duration. The clips are the author's
    voice and are not in the repository; without them the speech-to-text part is skipped.
CPU time is `time.process_time` (every thread of the process).
"""

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from . import meta as runmeta
from .accounting import max_rss_bytes, rss_bytes

CLIPS = runmeta.ROOT / "data" / "stt_recorded"
CLIP_SET = runmeta.ROOT / "data" / "stt_recorded_set.jsonl"
TEXTS = (
    runmeta.ROOT / "data" / "load" / "requests.jsonl",
    runmeta.ROOT / "data" / "qualitative" / "requests.jsonl",
)


def _stats(values: list[float]) -> dict[str, float]:
    ordered = sorted(values)
    n = len(ordered)

    def q(p):
        return ordered[max(1, -(-n * p // 100)) - 1]

    return {"n": n, "mean": sum(ordered) / n, "p50": q(50), "p95": q(95), "max": ordered[-1]}


def child_embedding(repeats: int) -> dict[str, Any]:
    from cpsagent.grounding import embedding  # imports torch and sentence-transformers

    rss_imported = rss_bytes()
    start = time.perf_counter()
    cpu0 = time.process_time()
    grounder = embedding.EmbeddingGrounder(embedding.SentenceTransformerEmbedder())
    load = {"wallS": time.perf_counter() - start, "cpuS": time.process_time() - cpu0}
    rss_loaded = rss_bytes()
    texts = []
    for path in TEXTS:
        texts += [json.loads(x)["text"] for x in path.read_text(encoding="utf-8").splitlines()]
    grounder.embedder.encode([texts[0]])  # warm-up
    cpu, wall = [], []
    for _ in range(repeats):
        for text in texts:
            c0, w0 = time.process_time(), time.perf_counter()
            grounder.embedder.encode([text])
            cpu.append((time.process_time() - c0) * 1e3)
            wall.append((time.perf_counter() - w0) * 1e3)
    import torch

    return {
        "model": embedding.MODEL_ID,
        "revision": embedding.MODEL_REVISION,
        "torchThreads": torch.get_num_threads(),
        "rssAfterImportsBytes": rss_imported,
        "rssAfterLoadBytes": rss_loaded,
        "rssAddedByModelBytes": rss_loaded - rss_imported,
        "peakRssBytes": max_rss_bytes(),
        "load": load,
        "encodeTexts": len(texts),
        "encodeCpuMs": _stats(cpu),
        "encodeWallMs": _stats(wall),
    }


def child_stt(repeats: int) -> dict[str, Any]:
    from cpsagent.ui import stt  # imports faster-whisper and CTranslate2

    clips = [json.loads(x) for x in CLIP_SET.read_text(encoding="utf-8").splitlines()]
    clips = [c for c in clips if (CLIPS / f"{c['id']}.wav").exists()]
    if not clips:
        return {"skipped": f"no recorded clips in {CLIPS}"}
    rss_imported = rss_bytes()
    start = time.perf_counter()
    cpu0 = time.process_time()
    model = stt.FasterWhisperTranscriber()
    load = {"wallS": time.perf_counter() - start, "cpuS": time.process_time() - cpu0}
    rss_loaded = rss_bytes()
    first = clips[0]
    model.transcribe(str(CLIPS / f"{first['id']}.wav"), first["language"])  # warm-up
    rows = []
    for r in range(repeats):
        for c in clips:
            c0, w0 = time.process_time(), time.perf_counter()
            t = model.transcribe(str(CLIPS / f"{c['id']}.wav"), c["language"])
            rows.append({
                "repeat": r, "id": c["id"], "language": c["language"],
                "cpuMs": (time.process_time() - c0) * 1e3,
                "wallMs": (time.perf_counter() - w0) * 1e3,
                "audioMs": t.audio_duration_ms, "transcribeMs": t.transcribe_ms,
            })  # fmt: skip
    return {
        "model": stt.MODEL_ID,
        "revision": stt.MODEL_REVISION,
        "computeType": stt.COMPUTE_TYPE,
        "decoding": stt.DECODING,
        "clips": len(clips),
        "rssAfterImportsBytes": rss_imported,
        "rssAfterLoadBytes": rss_loaded,
        "rssAddedByModelBytes": rss_loaded - rss_imported,
        "peakRssBytes": max_rss_bytes(),
        "load": load,
        "cpuMsPerClip": _stats([x["cpuMs"] for x in rows]),
        "wallMsPerClip": _stats([x["wallMs"] for x in rows]),
        "cpuPerAudioSecond": _stats([x["cpuMs"] / x["audioMs"] for x in rows]),
        "rows": rows,
    }


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    p = argparse.ArgumentParser(prog="python -m cpsagent.bench.models")
    p.add_argument("--repeats", type=int, default=3)
    p.add_argument("--child", choices=["embedding", "stt"])
    p.add_argument("--out", type=Path, default=runmeta.ROOT / "results" / "bench" / "models")
    args = p.parse_args(argv)
    if args.child:
        fn = child_embedding if args.child == "embedding" else child_stt
        print(json.dumps(fn(args.repeats)))
        return 0
    record = runmeta.run_metadata("cpsagent.bench.models", argv, repeats=args.repeats)
    for name in ("embedding", "stt"):
        cmd = [sys.executable, "-m", "cpsagent.bench.models", "--child", name,
               "--repeats", str(args.repeats)]  # fmt: skip
        done = subprocess.run(cmd, capture_output=True, text=True, cwd=runmeta.ROOT)
        if done.returncode != 0:
            record[name] = {"error": done.stderr[-2000:]}
            continue
        record[name] = json.loads(done.stdout.strip().splitlines()[-1])
        result = record[name]
        if "rssAddedByModelBytes" in result:
            print(f"{name}: +{result['rssAddedByModelBytes'] / 2**20:.0f} MB resident, "
                  f"load {result['load']['wallS']:.2f} s")  # fmt: skip
    runmeta.write(args.out / "metadata.json", record)
    print(f"written to {args.out / 'metadata.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
