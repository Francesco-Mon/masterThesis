"""What the engine tells the user (R3): fixed replies in the language of the request, and a
readable explanation for every reason a request was not carried out.

Only English and Italian are supported; any other language gets English. Questions asked by
the environment's interpreter (clarifications) are passed on as they are.
"""

from cpsagent.contracts import StructuredIntent

FIXED = {
    "not_bound": {
        "en": "No environment session is bound.",
        "it": "Nessuna sessione con l'ambiente è attiva.",
    },
    "following": {
        "en": "Done. I will keep doing it as you move.",
        "it": "Fatto. Continuerò a farlo mentre ti sposti.",
    },
    "done": {"en": "Done.", "it": "Fatto."},
    "unintelligible": {
        "en": "Sorry, I did not catch that. Could you say it again?",
        "it": "Scusa, non ho capito. Puoi ripetere?",
    },
    "zone_unknown": {
        "en": "I am not sure where you are. Which room are you in?",
        "it": "Non sono sicuro di dove ti trovi. In quale stanza sei?",
    },
    "following_alone": {
        "en": 'I can follow you with one request at a time: please ask "{part}" on its own.',
        "it": 'Posso seguirti con una sola richiesta alla volta: chiedi "{part}" da sola.',
    },
    "part_done": {"en": 'Done: "{part}".', "it": 'Fatto: "{part}".'},
    "part_not_done": {"en": '"{part}": {why}', "it": '"{part}": {why}'},
}

_PROPERTY = {
    "light": {"en": "the light", "it": "la luce"},
    "shading": {"en": "the blinds", "it": "le tapparelle"},
    "temperature": {"en": "the temperature", "it": "la temperatura"},
}

_REASONS = {
    "capability_absent": {
        "en": "I can't do that: there is no device for {what} {where}.",
        "it": "Non posso farlo: non c'è nessun dispositivo per {what} {where}.",
    },
    "command_absent": {
        "en": "I can't do that: the devices for {what} {where} cannot do it.",
        "it": "Non posso farlo: i dispositivi per {what} {where} non lo permettono.",
    },
    "unsupported:capability_absent": {
        "en": "I can't do that: no device in this building offers it.",
        "it": "Non posso farlo: nessun dispositivo dell'edificio lo offre.",
    },
    "unsupported:command_absent": {
        "en": "I can't do that: the devices here cannot do it.",
        "it": "Non posso farlo: i dispositivi qui non lo permettono.",
    },
    "unsupported:out_of_scope": {
        "en": "I can't do that: it is not something I may do in this building.",
        "it": "Non posso farlo: non è qualcosa che posso fare in questo edificio.",
    },
    "interpretation_refused:out_of_scope": {
        "en": "I can't help here: this zone is outside the ones I may use.",
        "it": "Qui non posso aiutarti: questa zona è fuori da quelle che posso usare.",
    },
    "intent_confidence_low": {
        "en": "I am not sure what you mean. Could you say it differently?",
        "it": "Non sono sicuro di cosa intendi. Puoi dirlo in un altro modo?",
    },
    "step_limit_reached": {
        "en": "I stopped: that would take too many commands.",
        "it": "Mi sono fermato: servirebbero troppi comandi.",
    },
    "retry_limit_reached": {
        "en": "I could not finish: a device did not respond.",
        "it": "Non ho potuto finire: un dispositivo non ha risposto.",
    },
    "clarification": {
        "en": "I did not understand which device or action you mean.",
        "it": "Non ho capito quale dispositivo o azione intendi.",
    },
}


def lang(language: str) -> str:
    return "it" if language == "it" else "en"


def fixed(key: str, language: str, **values: str) -> str:
    return FIXED[key][lang(language)].format(**values)


def explain(
    reason: str,
    language: str,
    intent: StructuredIntent | None = None,
    zone_id: str | None = None,
) -> str:
    """A sentence for the user instead of a reason code (e.g. unsupported:out_of_scope)."""
    code = lang(language)
    key = reason.split(":")[0] if reason.startswith(("retry_limit", "clarification")) else reason
    template = _REASONS.get(key)
    if template is None:
        fallback = {"en": "I could not do that ({r}).", "it": "Non ho potuto farlo ({r})."}
        return fallback[code].format(r=reason)
    what = where = ""
    if intent is not None:
        prop = intent.controlled_property
        what = _PROPERTY.get(prop, {}).get(code, prop)
        zone = intent.target_zone_id or zone_id
        if zone:
            where = ("in " if code == "en" else "in zona ") + zone.replace("_", " ")
    return template[code].format(what=what, where=where).replace(" .", ".")
