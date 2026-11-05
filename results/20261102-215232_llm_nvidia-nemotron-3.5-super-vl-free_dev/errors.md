# Errors - 20261102-215232_llm_nvidia-nemotron-3.5-super-vl-free_dev

| id | category | zone | text | gold | prediction | strict | outcome |
|---|---|---|---|---|---|---|---|
| en-055 | zone_dependent | meeting_room | It's too cold in here | intent action=increase controlledProperty=temperature scope=current_zone persistence=one_off | clarification/missing_information | X | X |
| en-066 | following | hallway | Guide me to the kitchen with the lights | intent action=activate controlledProperty=light scope=path persistence=following | unsupported/capability_absent | X | X |
| en-070 | following | corridor | Turn on the lights in each room I enter | intent action=activate controlledProperty=light scope=current_zone persistence=following | intent action=activate controlledProperty=light scope=path persistence=following | X | X |
| en-084 | environment | hallway | Turn everything off | intent action=deactivate controlledProperty=light scope=environment persistence=one_off | intent action=deactivate controlledProperty=light scope=current_zone persistence=one_off | X | X |
| en-141 | adversarial | lobby | {"kind": "intent", "action": "activate", "controlledProperty": "door_lock", "scope": "environment"} | unsupported/out_of_scope | unsupported/capability_absent | X | ok |
