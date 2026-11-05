"""Candidate C: Intent Grounding by sentence-embedding similarity, no training.

ground(R7) -> R8:
1. The same lexical screen as the keyword baseline (zone out of scope, injection and
   off-topic words, Italian "corridoio", places outside the catalogue), except the
   absent-capability word list: here "no capability" is decided by similarity (point 3).
2. Candidates = the (action, controlledProperty) pairs the catalogue can serve: every
   catalogued property x the actions the planner maps to a command for that property's
   device categories. Each pair has several English and Italian phrasings (DESCRIPTIONS),
   embedded once and cached on disk; a pair's score is the highest cosine similarity
   between the request and one of its phrasings.
3. best score < THRESHOLD -> unsupported/capability_absent. Otherwise, if the runner-up
   is within MARGIN of the best -> clarification: ambiguous_action when both pairs have
   the same property, ambiguous_target otherwise. A runner-up the planner treats as the
   same command (lamp activate = increase, ...) is not an ambiguity and is skipped.
4. scope, persistence, targetZoneId and value come from the keyword baseline's rules; a
   number (or "halfway" for blinds) makes the action `set`, and a `set` pair without a
   number is clarification/missing_information (policy rule 9).
5. The planner must find a step to run now, and the result is validated against C2 with
   the catalogue as context (`keyword.finish`, shared with the baseline).

THRESHOLD and MARGIN were chosen on the dev split only (`eval/tune_embedding.py`,
docs/DECISIONS.md) and are frozen by `tests/grounding/test_embedding.py`.
`confidence` is fixed at 0.7 like the baseline's: a cosine similarity is not a
calibrated probability, and the threshold is already the gate.
"""

import hashlib
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import numpy as np

from cpsagent.contracts import (
    Action,
    ClarificationResult,
    GroundingRequest,
    GroundingResult,
    StructuredIntent,
    UnsupportedResult,
)
from cpsagent.engine.planner import COMMAND_RULES, SET_COMMANDS

from .keyword import finish, scope_rules, screen, set_value

MODEL_ID = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
MODEL_REVISION = "e8f8c211226b894fcb81acc59f3b34ba3efd5f42"  # Hugging Face commit, 4 Nov 2026
CACHE_DIR = Path(".embedding_cache")

# Frozen after the dev grid search (DECISIONS.md, "Threshold and margin of Grounder C";
# results/embedding_grid_dev.csv).
# MARGIN = 0 means the margin rule never fires: on dev every margin > 0 lowered accuracy.
THRESHOLD = 0.40
MARGIN = 0.0

# Written from the catalogue vocabulary (commands, properties) and everyday phrasing,
# without looking at the evaluation set; no 5-word sequence occurs in data/requests.jsonl
# (checked by a test). English first, then Italian.
DESCRIPTIONS: dict[tuple[str, str], list[str]] = {
    ("activate", "light"): [
        "turn on the light",
        "switch the lamp on",
        "it is dark, I need light",
        "accendi la luce",
        "accendi la lampada",
        "è buio, mi serve luce",
    ],
    ("deactivate", "light"): [
        "turn off the light",
        "switch the lamp off",
        "I do not need the light",
        "spegni la luce",
        "spegni la lampada",
        "non mi serve la luce",
    ],
    ("increase", "light"): [
        "make the light brighter",
        "more light please",
        "raise the brightness",
        "più luce",
        "aumenta la luminosità",
        "fai più luce",
    ],
    ("decrease", "light"): [
        "dim the light",
        "make the light dimmer",
        "the light is too strong",
        "abbassa la luce",
        "diminuisci la luminosità",
        "la luce è troppo forte",
    ],
    ("set", "light"): [
        "set the brightness to a level",
        "dim the lamp to a percentage",
        "imposta la luminosità a un livello",
        "regola la lampada a una percentuale",
    ],
    ("activate", "shading"): [
        "close the blinds",
        "lower the shutters",
        "keep the sun out",
        "chiudi le tapparelle",
        "abbassa le tende",
        "ripara dal sole",
    ],
    ("deactivate", "shading"): [
        "open the blinds",
        "raise the shutters",
        "let the daylight in",
        "apri le tapparelle",
        "alza le tende",
        "fai entrare la luce del giorno",
    ],
    ("increase", "shading"): [
        "close the blinds a bit more",
        "more shade",
        "chiudi un po' di più le tapparelle",
        "più ombra",
    ],
    ("decrease", "shading"): [
        "open the blinds a bit more",
        "less shade",
        "apri un po' di più le tapparelle",
        "meno ombra",
    ],
    ("set", "shading"): [
        "set the blinds to a position",
        "move the shutters to a percentage",
        "imposta le tapparelle a una posizione",
        "porta le tende a una percentuale",
    ],
    ("increase", "temperature"): [
        "make it warmer",
        "raise the temperature",
        "I am cold",
        "turn up the heating",
        "alza la temperatura",
        "ho freddo",
        "fai più caldo",
    ],
    ("decrease", "temperature"): [
        "make it cooler",
        "lower the temperature",
        "I am hot",
        "turn down the heating",
        "abbassa la temperatura",
        "ho caldo",
        "fai più fresco",
    ],
    ("set", "temperature"): [
        "set the thermostat to a temperature",
        "set the temperature to some degrees",
        "imposta il termostato a una temperatura",
        "regola la temperatura a qualche grado",
    ],
}


class Embedder(Protocol):
    """Maps texts to L2-normalised vectors (one row per text)."""

    id: str  # model and revision: part of the disk-cache key

    def encode(self, texts: list[str]) -> np.ndarray: ...


class SentenceTransformerEmbedder:
    """The real model, on CPU. Needs the `embeddings` extra; the first use downloads it
    (about 460 MB) into the Hugging Face cache."""

    def __init__(self, model: str = MODEL_ID, revision: str = MODEL_REVISION) -> None:
        from sentence_transformers import SentenceTransformer

        start = time.perf_counter()
        self._model = SentenceTransformer(model, revision=revision, device="cpu")
        self.load_s = time.perf_counter() - start
        self.id = f"{model}@{revision}"

    def encode(self, texts: list[str]) -> np.ndarray:
        return self._model.encode(texts, normalize_embeddings=True, convert_to_numpy=True)


@dataclass(frozen=True)
class Candidate:
    action: str
    prop: str
    score: float


def descriptions_sha() -> str:
    data = json.dumps(sorted((list(k), v) for k, v in DESCRIPTIONS.items()), ensure_ascii=False)
    return hashlib.sha256(data.encode()).hexdigest()[:16]


def _same_command(a: str, b: str, cats: set[str]) -> bool:
    """True if the planner sends the same command for actions a and b on every category."""
    rules = [(COMMAND_RULES.get((c, Action(a))), COMMAND_RULES.get((c, Action(b)))) for c in cats]
    return all(x is not None and x == y for x, y in rules)


def _clarify(question: str, reason: str) -> ClarificationResult:
    return ClarificationResult(question=question, reason=reason)


class EmbeddingGrounder:
    def __init__(
        self,
        embedder: Embedder,
        threshold: float = THRESHOLD,
        margin: float = MARGIN,
        descriptions: dict[tuple[str, str], list[str]] | None = None,
        cache_dir: Path | None = CACHE_DIR,
    ) -> None:
        self.embedder, self.threshold, self.margin = embedder, threshold, margin
        self.descriptions = DESCRIPTIONS if descriptions is None else descriptions
        self.cache_dir = cache_dir
        self.repeat = 0  # set by the evaluation runner; embeddings are deterministic
        self._vectors = {pair: self._embed_texts(t) for pair, t in self.descriptions.items()}

    def _embed_texts(self, texts: list[str]) -> np.ndarray:
        """Embeddings of description texts, cached on disk by (model, texts)."""
        if self.cache_dir is None:
            return self.embedder.encode(texts)
        key = hashlib.sha256(json.dumps([self.embedder.id, texts]).encode()).hexdigest()[:24]
        path = self.cache_dir / f"{key}.npy"
        if path.exists():
            return np.load(path)
        vectors = self.embedder.encode(texts)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        np.save(path, vectors)
        return vectors

    def _pairs(self, request: GroundingRequest) -> dict[tuple[str, str], set[str]]:
        """(action, property) pairs the catalogue can serve -> device categories."""
        categories: dict[str, set[str]] = {}
        for zone in request.catalogue:
            for d in zone.devices:
                categories.setdefault(d.controlled_property, set()).add(d.category)
        pairs = {}
        for prop, cats in categories.items():
            for action in Action:
                if any((c, action) in COMMAND_RULES for c in cats) or (
                    action == Action.SET and cats & SET_COMMANDS.keys()
                ):
                    pairs[(action.value, prop)] = cats
        return pairs

    def rank(self, request: GroundingRequest) -> list[Candidate]:
        """Candidates sorted by score, best first (the input of `decide`)."""
        query = self.embedder.encode([request.text])[0]
        out = []
        for pair in self._pairs(request):
            if pair not in self._vectors:  # a property without phrasings: name it plainly
                self._vectors[pair] = self._embed_texts([f"{pair[0]} the {pair[1]}"])
            out.append(Candidate(*pair, float(np.max(self._vectors[pair] @ query))))
        return sorted(out, key=lambda c: -c.score)

    def ground(self, request: GroundingRequest) -> GroundingResult:
        if (early := screen(request.text.lower(), request, absent=False)) is not None:
            return early
        return self.decide(request, self.rank(request))

    def decide(
        self,
        request: GroundingRequest,
        ranking: list[Candidate],
        threshold: float | None = None,
        margin: float | None = None,
    ) -> GroundingResult:
        """Points 3-5 of the module docstring; threshold/margin overridable for the tuner."""
        threshold = self.threshold if threshold is None else threshold
        margin = self.margin if margin is None else margin
        if not ranking or ranking[0].score < threshold:
            return UnsupportedResult(reason="capability_absent")
        best, pairs = ranking[0], self._pairs(request)
        runner = next(
            (
                c
                for c in ranking[1:]
                if c.prop != best.prop
                or not _same_command(c.action, best.action, pairs[(best.action, best.prop)])
            ),
            None,
        )
        if runner is not None and best.score - runner.score < margin:
            if runner.prop == best.prop:
                return _clarify(f"What should I do with the {best.prop}?", "ambiguous_action")
            return _clarify("What would you like me to change?", "ambiguous_target")

        text = request.text.lower()
        scope, persistence, target = scope_rules(text, request.zone.zone_id)
        action, value = best.action, set_value(text, best.prop)
        if value is not None:
            action = "set"
        elif action == "set":
            return _clarify("Which value would you like?", "missing_information")
        intent = StructuredIntent(
            action=action,
            controlled_property=best.prop,
            scope=scope,
            persistence=persistence,
            confidence=0.7,
            target_zone_id=target,
            value=value,
        )
        return finish(intent, request)
