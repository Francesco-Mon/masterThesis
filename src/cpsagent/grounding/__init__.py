"""Intent Grounding (F3): every candidate implements `Grounder.ground(R7) -> R8`.

Candidates A (`cpsagent.grounding.llm`) and C (`cpsagent.grounding.embedding`) are not
re-exported here, so the core package (FakeGrounder, engine, tests) needs neither the
`llm` nor the `embeddings` extra.
"""

from .base import Grounder
from .fake import FakeGrounder

__all__ = ["FakeGrounder", "Grounder"]
