"""Record the author's voice for the STT measurement (real-voice condition).

Run:  python -m cpsagent.ui.record_clips [--out data/stt_recorded] [--redo]

Shows the sentences of data/stt_recorded_set.jsonl one at a time; Enter starts the
recording, Enter again stops it (at most 6 s). Each clip is saved as a 16 kHz mono
16-bit WAV named <id>.wav in a git-ignored folder: the voice stays on this machine,
only the reference texts are committed. Clips already recorded are skipped, so the
script can be stopped (q) and resumed; --redo records everything again.

macOS asks for microphone permission the first time. If every clip comes out silent,
enable it for the app that runs the terminal (System Settings > Privacy & Security >
Microphone > Visual Studio Code) and restart that app.
"""

import argparse
import json
import select
import sys
import time
import wave
from pathlib import Path

import numpy as np

SET_FILE = Path("data/stt_recorded_set.jsonl")
OUT_DIR = Path("data/stt_recorded")
RATE = 16_000  # what Whisper expects: no resampling needed
MAX_S = 6.0
SILENT_PEAK = 300  # int16 peak below this = nothing reached the microphone


def record(max_s: float = MAX_S) -> np.ndarray:
    """Record until Enter is pressed or max_s seconds pass; returns int16 samples."""
    import sounddevice as sd

    chunks: list[np.ndarray] = []
    with sd.InputStream(samplerate=RATE, channels=1, dtype="int16",
                        callback=lambda data, *_: chunks.append(data.copy())):  # fmt: skip
        deadline = time.monotonic() + max_s
        while (left := deadline - time.monotonic()) > 0:
            ready, _, _ = select.select([sys.stdin], [], [], min(left, 0.1))
            if ready:
                sys.stdin.readline()
                break
    return np.concatenate(chunks)[:, 0] if chunks else np.zeros(0, dtype=np.int16)


def save_wav(path: Path, samples: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(samples.tobytes())


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--out", type=Path, default=OUT_DIR)
    p.add_argument("--redo", action="store_true", help="record clips that already exist")
    args = p.parse_args(argv)
    items = [json.loads(line) for line in SET_FILE.open(encoding="utf-8")]

    print(f"{len(items)} sentences, saved to {args.out}/. Speak naturally, as to the building.")
    for n, item in enumerate(items, 1):
        path = args.out / f"{item['id']}.wav"
        if path.exists() and not args.redo:
            continue
        while True:
            print(f"\n[{n}/{len(items)}] ({item['language']})  {item['text']}")
            key = input("Enter = record, s = skip, q = quit: ").strip().lower()
            if key == "q":
                return 0
            if key == "s":
                break
            print(f"  recording... Enter to stop (max {MAX_S:.0f} s)")
            samples = record()
            peak = int(np.abs(samples.astype(np.int32)).max()) if samples.size else 0
            print(f"  {samples.size / RATE:.1f} s, peak {peak}")
            if peak < SILENT_PEAK:
                print("  silent: check the microphone permission (see the module docstring)")
            if input("  Enter = keep, r = record again: ").strip().lower() != "r":
                save_wav(path, samples)
                break
    print("\nDone. Measure with: python -m cpsagent.eval.stt --source recorded")
    return 0


if __name__ == "__main__":
    sys.exit(main())
