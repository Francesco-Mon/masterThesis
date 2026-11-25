# 20261125-142031_llm_mistralai-mistral-large-4-0_test

grounder=llm, model=mistralai/mistral-large-4-0, provider=mistral/zdr, split=test, repeats=3, temperature=0.0

## CLASSic overview

| group | metric | value |
|---|---|---|
| Accuracy | predictions | 180 |
| Accuracy | kind accuracy | 97.8% [94.4%-99.1%] |
| Accuracy | strict accuracy | 96.1% [92.2%-98.1%] |
| Accuracy | outcome accuracy | 99.4% [96.9%-99.9%] |
| Accuracy | intent: all fields (gold intents) | 96.0% [90.1%-98.4%] |
| Security | injection cases handled (outcome correct) | 100.0% [82.4%-100.0%] |
| Security | injection-only cases with a command | 0 / 9 |
| Security | mixed cases with commands beyond the legitimate part | 0 / 9 |
| Security | raw grounder output off catalogue (all cases) | 0.0% [0.0%-2.1%] |
| Security | final commands off catalogue (must be 0) | 0 |
| Cost | total USD | 0.516010 |
| Cost | USD per 1000 requests | 2.8667 |
| Cost | prompt / completion tokens | 367044 / 194027 |
| Cost | tokens per request (prompt / completion) | 2039 / 1078 |
| Cost | LLM calls (incl. retries) | 174 |
| Cost | requests needing a retry | 0 |
| Latency | requests measured (not cached) | 174 |
| Latency | mean s | 19.08 |
| Latency | p50 s | 13.51 |
| Latency | p95 s | 47.67 |
| Latency | p50 ms | 13513.70 |
| Latency | p95 ms | 47665.50 |
| Stability | repeat agreement (all repeats identical) | 95.0% [86.3%-98.3%] |
| Stability | EN-IT agreement (paraphrase pairs) | - |
| Stability | EN-IT pairs | 0 |
| Failures | invalid output after retries | 0 |
| Failures | service unavailable | 0 |

## Intent fields (gold intents, n = 99)

| field | accuracy |
|---|---|
| action | 96.0% [90.1%-98.4%] |
| controlledProperty | 96.0% [90.1%-98.4%] |
| scope | 96.0% [90.1%-98.4%] |
| persistence | 96.0% [90.1%-98.4%] |
| targetZoneId | 96.0% [90.1%-98.4%] |
| value | 96.0% [90.1%-98.4%] |
| all fields | 96.0% [90.1%-98.4%] |

## Result kinds (rows gold, columns predicted)

|  | pred intent | pred clarification | pred unsupported |
|---|---|---|---|
| gold intent | 95 | 3 | 1 |
| gold clarification | 0 | 30 | 0 |
| gold unsupported | 0 | 0 | 51 |
| clarification precision / recall | 90.9% [76.4%-96.9%] | 100.0% [88.6%-100.0%] |  |

## Reasons

| gold kind | n | kind correct | reason correct (given kind) |
|---|---|---|---|
| clarification | 30 | 100.0% [88.6%-100.0%] | 100.0% [88.6%-100.0%] |
| unsupported | 51 | 100.0% [93.0%-100.0%] | 88.2% [76.6%-94.5%] |

## Strict errors by type (n = 7)

| type | errors | share |
|---|---|---|
| non-intent: wrong kind or reason | 6 | 86% |
| non-intent predicted, intent expected | 1 | 14% |

## Per category

| category | n | strict | outcome |
|---|---|---|---|
| adversarial | 18 | 77.8% [54.8%-91.0%] | 100.0% [82.4%-100.0%] |
| ambiguous | 18 | 100.0% [82.4%-100.0%] | 100.0% [82.4%-100.0%] |
| environment | 18 | 100.0% [82.4%-100.0%] | 100.0% [82.4%-100.0%] |
| explicit | 18 | 94.4% [74.2%-99.0%] | 94.4% [74.2%-99.0%] |
| explicit_other_zone | 18 | 100.0% [82.4%-100.0%] | 100.0% [82.4%-100.0%] |
| following | 18 | 100.0% [82.4%-100.0%] | 100.0% [82.4%-100.0%] |
| implicit | 18 | 100.0% [82.4%-100.0%] | 100.0% [82.4%-100.0%] |
| out_of_scope | 18 | 100.0% [82.4%-100.0%] | 100.0% [82.4%-100.0%] |
| unsupported | 18 | 88.9% [67.2%-96.9%] | 100.0% [82.4%-100.0%] |
| zone_dependent | 18 | 100.0% [82.4%-100.0%] | 100.0% [82.4%-100.0%] |

## Per language

| language | n | strict | outcome |
|---|---|---|---|
| en | 120 | 95.0% [89.5%-97.7%] | 100.0% [96.9%-100.0%] |
| it | 60 | 98.3% [91.1%-99.7%] | 98.3% [91.1%-99.7%] |

## Per source

| source | n | strict | outcome |
|---|---|---|---|
| llm | 180 | 96.1% [92.2%-98.1%] | 99.4% [96.9%-99.9%] |
