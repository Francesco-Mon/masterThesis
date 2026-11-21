# 20261121-154056_llm_mistralai-mistral-large-4-0_dev

grounder=llm, model=mistralai/mistral-large-4-0, provider=mistral/zdr, split=dev, repeats=1, temperature=0.0

## CLASSic overview

| group | metric | value |
|---|---|---|
| Accuracy | predictions | 54 |
| Accuracy | kind accuracy | 98.1% [90.2%-99.7%] |
| Accuracy | strict accuracy | 96.3% [87.5%-99.0%] |
| Accuracy | outcome accuracy | 98.1% [90.2%-99.7%] |
| Accuracy | intent: all fields (gold intents) | 100.0% [89.3%-100.0%] |
| Security | injection cases handled (outcome correct) | 100.0% [56.6%-100.0%] |
| Security | injection-only cases with a command | 0 / 1 |
| Security | mixed cases with commands beyond the legitimate part | 0 / 4 |
| Security | raw grounder output off catalogue (all cases) | 0.0% [0.0%-6.6%] |
| Security | final commands off catalogue (must be 0) | 0 |
| Cost | total USD | 0.147993 |
| Cost | USD per 1000 requests | 2.7406 |
| Cost | prompt / completion tokens | 111588 / 49405 |
| Cost | tokens per request (prompt / completion) | 2066 / 915 |
| Cost | LLM calls (incl. retries) | 53 |
| Cost | requests needing a retry | 0 |
| Latency | requests measured (not cached) | 53 |
| Latency | mean s | 15.50 |
| Latency | p50 s | 9.24 |
| Latency | p95 s | 45.57 |
| Latency | p50 ms | 9238.20 |
| Latency | p95 ms | 45574.80 |
| Stability | repeat agreement (all repeats identical) | - |
| Stability | EN-IT agreement (paraphrase pairs) | 100.0% [61.0%-100.0%] |
| Stability | EN-IT pairs | 6 |
| Failures | invalid output after retries | 0 |
| Failures | service unavailable | 0 |

## Intent fields (gold intents, n = 32)

| field | accuracy |
|---|---|
| action | 100.0% [89.3%-100.0%] |
| controlledProperty | 100.0% [89.3%-100.0%] |
| scope | 100.0% [89.3%-100.0%] |
| persistence | 100.0% [89.3%-100.0%] |
| targetZoneId | 100.0% [89.3%-100.0%] |
| value | 100.0% [89.3%-100.0%] |
| all fields | 100.0% [89.3%-100.0%] |

## Result kinds (rows gold, columns predicted)

|  | pred intent | pred clarification | pred unsupported |
|---|---|---|---|
| gold intent | 32 | 0 | 0 |
| gold clarification | 1 | 7 | 0 |
| gold unsupported | 0 | 0 | 14 |
| clarification precision / recall | 100.0% [64.6%-100.0%] | 87.5% [52.9%-97.8%] |  |

## Reasons

| gold kind | n | kind correct | reason correct (given kind) |
|---|---|---|---|
| clarification | 8 | 87.5% [52.9%-97.8%] | 100.0% [64.6%-100.0%] |
| unsupported | 14 | 100.0% [78.5%-100.0%] | 85.7% [60.1%-96.0%] |

## Strict errors by type (n = 2)

| type | errors | share |
|---|---|---|
| intent predicted, non-intent expected | 1 | 50% |
| non-intent: wrong kind or reason | 1 | 50% |

## Per category

| category | n | strict | outcome |
|---|---|---|---|
| adversarial | 5 | 80.0% [37.6%-96.4%] | 100.0% [56.6%-100.0%] |
| ambiguous | 5 | 80.0% [37.6%-96.4%] | 80.0% [37.6%-96.4%] |
| environment | 5 | 100.0% [56.6%-100.0%] | 100.0% [56.6%-100.0%] |
| explicit | 5 | 100.0% [56.6%-100.0%] | 100.0% [56.6%-100.0%] |
| explicit_other_zone | 6 | 100.0% [61.0%-100.0%] | 100.0% [61.0%-100.0%] |
| following | 5 | 100.0% [56.6%-100.0%] | 100.0% [56.6%-100.0%] |
| implicit | 5 | 100.0% [56.6%-100.0%] | 100.0% [56.6%-100.0%] |
| out_of_scope | 6 | 100.0% [61.0%-100.0%] | 100.0% [61.0%-100.0%] |
| unsupported | 6 | 100.0% [61.0%-100.0%] | 100.0% [61.0%-100.0%] |
| zone_dependent | 6 | 100.0% [61.0%-100.0%] | 100.0% [61.0%-100.0%] |

## Per language

| language | n | strict | outcome |
|---|---|---|---|
| en | 48 | 95.8% [86.0%-98.8%] | 97.9% [89.1%-99.6%] |
| it | 6 | 100.0% [61.0%-100.0%] | 100.0% [61.0%-100.0%] |

## Per source

| source | n | strict | outcome |
|---|---|---|---|
| llm | 54 | 96.3% [87.5%-99.0%] | 98.1% [90.2%-99.7%] |
