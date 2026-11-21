"""Run a command that writes its own result files and write `metadata.json` next to them.

Run: python -m cpsagent.bench.record --out DIR [--broker URL] -- COMMAND ARGS...

Used for the commands whose code is frozen or already approved (the evaluation runner,
the backends harness): it does not change them, it only records how they were run (see
`meta.py`), how long they took and their exit code. `--broker` adds the versions the
Orion-LD broker reports and the platform of its images.
"""

import argparse
import subprocess
import sys
import time
from pathlib import Path

from . import meta


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if "--" not in argv:
        raise SystemExit("usage: python -m cpsagent.bench.record --out DIR -- COMMAND...")
    split = argv.index("--")
    parser = argparse.ArgumentParser(prog="python -m cpsagent.bench.record")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--broker", help="Orion-LD URL, to record its versions")
    args = parser.parse_args(argv[:split])
    cmd = argv[split + 1 :]
    record = meta.run_metadata("cpsagent.bench.record", argv)
    record["recordedCommand"] = " ".join(cmd)
    if args.broker:
        record["broker"] = meta.broker(args.broker)
    started = time.perf_counter()
    code = subprocess.run(cmd, cwd=meta.ROOT).returncode
    record["durationS"] = round(time.perf_counter() - started, 3)
    record["exitCode"] = code
    record["gitAfter"] = meta.git()
    meta.write(args.out / "metadata.json", record)
    print(f"metadata written to {args.out / 'metadata.json'}")
    return code


if __name__ == "__main__":
    sys.exit(main())
