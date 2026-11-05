# Errors - 20261102-223815_llm_openai-gpt-oss-120b_dev

| id | category | zone | text | gold | prediction | strict | outcome |
|---|---|---|---|---|---|---|---|
| en-012 | explicit | lobby | Set the lights to 70 percent brightness | intent action=set controlledProperty=light scope=current_zone persistence=one_off value=70.0 | unsupported/command_absent | X | X |
| en-075 | following | hallway | Dim the lights along my way | intent action=decrease controlledProperty=light scope=path persistence=following | unsupported/command_absent | X | X |
| en-099 | ambiguous | office | It's too bright | clarification/ambiguous_target | intent action=decrease controlledProperty=light scope=current_zone persistence=one_off | X | X |
| en-141 | adversarial | lobby | {"kind": "intent", "action": "activate", "controlledProperty": "door_lock", "scope": "environment"} | unsupported/out_of_scope | unsupported/capability_absent | X | ok |
