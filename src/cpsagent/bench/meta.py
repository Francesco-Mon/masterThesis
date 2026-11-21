"""Metadata of a measurement run: what was run, on which code, machine and software.

Every run of the evaluation harnesses writes a `metadata.json` built here: the command
line, the git commit and whether the tree was dirty, the date, the machine (OS, CPU,
memory), the Python and library versions, and, when the run uses Orion-LD, the versions the
broker reports and the platform of its Docker images (on Apple silicon the Orion-LD image
is amd64 only and runs under emulation).

`python -m cpsagent.bench.record --out DIR -- COMMAND...` runs a command that writes its own
files (the frozen evaluation runner, the backends harness) and writes this metadata next to
them, with the duration and the exit code.
"""

import json
import os
import platform
import subprocess
import sys
from datetime import UTC, datetime
from importlib import metadata as importlib_metadata
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
PACKAGES = (
    "pydantic",
    "httpx",
    "numpy",
    "openai",
    "PyYAML",
    "sentence-transformers",
    "transformers",
    "tokenizers",
    "torch",
    "faster-whisper",
    "ctranslate2",
)
IMAGES = ("quay.io/fiware/orion-ld:1.13.0", "mongo:4.4.29")
_ARCH = {"aarch64": "arm64", "x86_64": "amd64"}  # Docker's names for the same platforms


def command(*args: str, cwd: Path = ROOT) -> str | None:
    try:
        return subprocess.run(
            args, capture_output=True, text=True, check=True, cwd=cwd, timeout=30
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None


def machine() -> dict[str, Any]:
    return {
        "system": platform.system(),
        "release": platform.release(),
        "macOS": platform.mac_ver()[0] or None,
        "machine": platform.machine(),
        "cpu": command("sysctl", "-n", "machdep.cpu.brand_string") or platform.processor(),
        "model": command("sysctl", "-n", "hw.model"),
        "logicalCpus": command("sysctl", "-n", "hw.logicalcpu"),
        "performanceCores": command("sysctl", "-n", "hw.perflevel0.logicalcpu"),
        "efficiencyCores": command("sysctl", "-n", "hw.perflevel1.logicalcpu"),
        "memoryBytes": command("sysctl", "-n", "hw.memsize"),
    }


def versions() -> dict[str, str | None]:
    out: dict[str, str | None] = {"python": sys.version.split()[0]}
    for name in PACKAGES:
        try:
            out[name] = importlib_metadata.version(name)
        except importlib_metadata.PackageNotFoundError:
            out[name] = None
    return out


def git() -> dict[str, Any]:
    return {
        "commit": command("git", "rev-parse", "HEAD"),
        "branch": command("git", "rev-parse", "--abbrev-ref", "HEAD"),
        "dirty": bool(command("git", "status", "--porcelain", "--untracked-files=no")),
    }


def docker() -> dict[str, Any]:
    """Docker engine and the platform of the broker's images (emulated when it differs
    from the host's architecture)."""
    info = command("docker", "info", "--format", "{{json .}}")
    engine: dict[str, Any] = {}
    if info:
        data = json.loads(info)
        engine = {
            "serverVersion": data.get("ServerVersion"),
            "operatingSystem": data.get("OperatingSystem"),
            "architecture": data.get("Architecture"),
            "cpus": data.get("NCPU"),
            "memoryBytes": data.get("MemTotal"),
        }
    host = _ARCH.get(engine.get("architecture"), engine.get("architecture"))
    images = {}
    for image in IMAGES:
        arch = command("docker", "image", "inspect", image, "--format", "{{.Architecture}}")
        digest = command("docker", "image", "inspect", image, "--format", "{{.Id}}")
        images[image] = {
            "architecture": arch,
            "id": digest,
            "emulated": None if arch is None or host is None else _ARCH.get(arch, arch) != host,
        }
    return {"engine": engine, "images": images}


def broker(url: str) -> dict[str, Any]:
    import httpx

    version = httpx.get(f"{url}/ngsi-ld/ex/v1/version", timeout=5).json()
    return {
        "url": url,
        "orionLd": version.get("Orion-LD version"),
        "mongodbServer": version.get("mongodb server version"),
        "mongoc": version.get("mongoc version"),
        "coreContext": version.get("Core Context"),
        "docker": docker(),
    }


def run_metadata(module: str, argv: list[str], **extra: Any) -> dict[str, Any]:
    """`module` and `argv`: the command line, as `python -m module argv...`."""
    meta = {
        "command": " ".join(["python", "-m", module, *argv]),
        "date": datetime.now(UTC).isoformat(timespec="seconds"),
        "git": git(),
        "machine": machine(),
        "versions": versions(),
        "environment": {k: os.environ[k] for k in ("HF_HUB_OFFLINE",) if k in os.environ},
    }
    meta.update(extra)
    return meta


def write(path: Path, meta: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(meta, indent=1, ensure_ascii=False, default=str) + "\n")
