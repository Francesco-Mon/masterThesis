"""Splitting a message that asks for several actions ("turn off the light and lower the
blinds") into parts the environment can interpret one by one.

Deliberately simple: the text is cut on the conjunctions and separators of its language
(English: "and", "then", a comma; Italian: "e", "poi", a comma), into at most three parts
(anything after the second cut stays in the third part). It does not understand the
sentence: a cut that separates an action from its object ("turn on the light in the
kitchen and the corridor") gives a part the environment will not understand, and that
part is reported as not done. The engine splits only a message the environment did not
understand as a whole.
"""

import re

MAX_PARTS = 3

_SEPARATORS = {
    "en": r"\s*,\s*(?:and\s+then\s+|and\s+|then\s+)?|\s+(?:and\s+then|and|then)\s+",
    "it": r"\s*,\s*(?:e\s+poi\s+|e\s+|poi\s+)?|\s+(?:e\s+poi|e|poi)\s+",
}


def split_message(text: str, language: str) -> list[str]:
    """The parts of `text`, in order; one part (the whole text) if there is no separator."""
    pattern = _SEPARATORS["it" if language == "it" else "en"]
    parts = re.split(pattern, text.strip(), maxsplit=MAX_PARTS - 1, flags=re.IGNORECASE)
    return [p.strip(" .,;") for p in parts if p.strip(" .,;")]
