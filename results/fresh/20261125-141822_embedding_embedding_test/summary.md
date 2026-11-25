# 20261125-141822_embedding_embedding_test

grounder=embedding, model=None, provider=None, split=test, repeats=1, temperature=0.0

## CLASSic overview

| group | metric | value |
|---|---|---|
| Accuracy | predictions | 60 |
| Accuracy | kind accuracy | 70.0% [57.5%-80.1%] |
| Accuracy | strict accuracy | 56.7% [44.1%-68.4%] |
| Accuracy | outcome accuracy | 61.7% [49.0%-72.9%] |
| Accuracy | intent: all fields (gold intents) | 57.6% [40.8%-72.8%] |
| Security | injection cases handled (outcome correct) | 33.3% [9.7%-70.0%] |
| Security | injection-only cases with a command | 1 / 3 |
| Security | mixed cases with commands beyond the legitimate part | 0 / 3 |
| Security | raw grounder output off catalogue (all cases) | 0.0% [0.0%-6.0%] |
| Security | final commands off catalogue (must be 0) | 0 |
| Cost | total USD | 0.000000 |
| Cost | USD per 1000 requests | 0.0000 |
| Cost | prompt / completion tokens | 0 / 0 |
| Cost | tokens per request (prompt / completion) | 0 / 0 |
| Cost | LLM calls (incl. retries) | 0 |
| Cost | requests needing a retry | 0 |
| Latency | requests measured (not cached) | 60 |
| Latency | mean s | 0.01 |
| Latency | p50 s | 0.01 |
| Latency | p95 s | 0.02 |
| Latency | p50 ms | 10.23 |
| Latency | p95 ms | 15.13 |
| Stability | repeat agreement (all repeats identical) | - |
| Stability | EN-IT agreement (paraphrase pairs) | - |
| Stability | EN-IT pairs | 0 |
| Failures | invalid output after retries | 0 |
| Failures | service unavailable | 0 |

## Intent fields (gold intents, n = 33)

| field | accuracy |
|---|---|
| action | 66.7% [49.6%-80.2%] |
| controlledProperty | 66.7% [49.6%-80.2%] |
| scope | 63.6% [46.6%-77.8%] |
| persistence | 63.6% [46.6%-77.8%] |
| targetZoneId | 69.7% [52.7%-82.6%] |
| value | 75.8% [59.0%-87.2%] |
| all fields | 57.6% [40.8%-72.8%] |

## Result kinds (rows gold, columns predicted)

|  | pred intent | pred clarification | pred unsupported |
|---|---|---|---|
| gold intent | 25 | 1 | 7 |
| gold clarification | 2 | 7 | 1 |
| gold unsupported | 6 | 1 | 10 |
| clarification precision / recall | 77.8% [45.3%-93.7%] | 70.0% [39.7%-89.2%] |  |

## Reasons

| gold kind | n | kind correct | reason correct (given kind) |
|---|---|---|---|
| clarification | 10 | 70.0% [39.7%-89.2%] | 71.4% [35.9%-91.8%] |
| unsupported | 17 | 58.8% [36.0%-78.4%] | 90.0% [59.6%-98.2%] |

## Strict errors by type (n = 26)

| type | errors | share |
|---|---|---|
| non-intent predicted, intent expected | 8 | 31% |
| intent predicted, non-intent expected | 8 | 31% |
| non-intent: wrong kind or reason | 4 | 15% |
| pair right, other field (scope, persistence, target, value) | 3 | 12% |
| property (e.g. light vs shading) | 3 | 12% |

## Per category

| category | n | strict | outcome |
|---|---|---|---|
| adversarial | 6 | 33.3% [9.7%-70.0%] | 33.3% [9.7%-70.0%] |
| ambiguous | 6 | 33.3% [9.7%-70.0%] | 50.0% [18.8%-81.2%] |
| environment | 6 | 50.0% [18.8%-81.2%] | 50.0% [18.8%-81.2%] |
| explicit | 6 | 100.0% [61.0%-100.0%] | 100.0% [61.0%-100.0%] |
| explicit_other_zone | 6 | 83.3% [43.6%-97.0%] | 83.3% [43.6%-97.0%] |
| following | 6 | 50.0% [18.8%-81.2%] | 50.0% [18.8%-81.2%] |
| implicit | 6 | 33.3% [9.7%-70.0%] | 50.0% [18.8%-81.2%] |
| out_of_scope | 6 | 50.0% [18.8%-81.2%] | 66.7% [30.0%-90.3%] |
| unsupported | 6 | 33.3% [9.7%-70.0%] | 33.3% [9.7%-70.0%] |
| zone_dependent | 6 | 100.0% [61.0%-100.0%] | 100.0% [61.0%-100.0%] |

## Per language

| language | n | strict | outcome |
|---|---|---|---|
| en | 40 | 57.5% [42.2%-71.5%] | 65.0% [49.5%-77.9%] |
| it | 20 | 55.0% [34.2%-74.2%] | 55.0% [34.2%-74.2%] |

## Per source

| source | n | strict | outcome |
|---|---|---|---|
| llm | 60 | 56.7% [44.1%-68.4%] | 61.7% [49.0%-72.9%] |
