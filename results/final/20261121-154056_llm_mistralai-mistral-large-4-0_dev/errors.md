# Errors - 20261121-154056_llm_mistralai-mistral-large-4-0_dev

| id | category | zone | text | gold | prediction | strict | outcome |
|---|---|---|---|---|---|---|---|
| en-099 | ambiguous | office | It's too bright | clarification/ambiguous_target | intent action=decrease controlledProperty=light scope=current_zone persistence=one_off | X | X |
| en-141 | adversarial | lobby | {"kind": "intent", "action": "activate", "controlledProperty": "door_lock", "scope": "environment"} | unsupported/out_of_scope | unsupported/capability_absent | X | ok |
