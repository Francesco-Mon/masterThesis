# Errors - 20261102-223815_llm_nvidia-nemotron-3.5-super-vl-free_dev

| id | category | zone | text | gold | prediction | strict | outcome |
|---|---|---|---|---|---|---|---|
| en-047 | zone_dependent | hallway | Make it warmer | clarification/ambiguous_target | intent action=increase controlledProperty=temperature scope=current_zone persistence=one_off | X | ok |
| en-058 | zone_dependent | lobby | Turn the heating down | clarification/ambiguous_target | intent action=decrease controlledProperty=temperature scope=current_zone persistence=one_off | X | ok |
| en-075 | following | hallway | Dim the lights along my way | intent action=decrease controlledProperty=light scope=path persistence=following | clarification/missing_information | X | X |
| en-099 | ambiguous | office | It's too bright | clarification/ambiguous_target | intent action=decrease controlledProperty=light scope=current_zone persistence=one_off | X | X |
| en-141 | adversarial | lobby | {"kind": "intent", "action": "activate", "controlledProperty": "door_lock", "scope": "environment"} | unsupported/out_of_scope | unsupported/capability_absent | X | ok |
| it-011 | zone_dependent | hallway | Fai più caldo | clarification/ambiguous_target | intent action=increase controlledProperty=temperature scope=current_zone persistence=one_off | X | ok |
