# 20261121-131024_embedding_embedding_test

grounder=embedding, model=None, provider=None, split=test, repeats=1, temperature=0.0

## CLASSic overview

| group | metric | value |
|---|---|---|
| Accuracy | predictions | 156 |
| Accuracy | kind accuracy | 89.1% [83.2%-93.1%] |
| Accuracy | strict accuracy | 78.2% [71.1%-84.0%] |
| Accuracy | outcome accuracy | 80.8% [73.9%-86.2%] |
| Accuracy | intent: all fields (gold intents) | 80.9% [71.5%-87.7%] |
| Security | injection cases handled (outcome correct) | 93.3% [70.2%-98.8%] |
| Security | injection-only cases with a command | 0 / 13 |
| Security | mixed cases with commands beyond the legitimate part | 0 / 2 |
| Security | raw grounder output off catalogue (all cases) | 0.0% [0.0%-2.4%] |
| Security | final commands off catalogue (must be 0) | 0 |
| Cost | total USD | 0.000000 |
| Cost | USD per 1000 requests | 0.0000 |
| Cost | prompt / completion tokens | 0 / 0 |
| Cost | tokens per request (prompt / completion) | 0 / 0 |
| Cost | LLM calls (incl. retries) | 0 |
| Cost | requests needing a retry | 0 |
| Latency | requests measured (not cached) | 156 |
| Latency | mean s | 0.01 |
| Latency | p50 s | 9.7e-03 |
| Latency | p95 s | 0.01 |
| Latency | p50 ms | 9.73 |
| Latency | p95 ms | 11.84 |
| Stability | repeat agreement (all repeats identical) | - |
| Stability | EN-IT agreement (paraphrase pairs) | 70.8% [50.8%-85.1%] |
| Stability | EN-IT pairs | 24 |
| Failures | invalid output after retries | 0 |
| Failures | service unavailable | 0 |

## Intent fields (gold intents, n = 89)

| field | accuracy |
|---|---|
| action | 80.9% [71.5%-87.7%] |
| controlledProperty | 91.0% [83.3%-95.4%] |
| scope | 94.4% [87.5%-97.6%] |
| persistence | 94.4% [87.5%-97.6%] |
| targetZoneId | 95.5% [89.0%-98.2%] |
| value | 95.5% [89.0%-98.2%] |
| all fields | 80.9% [71.5%-87.7%] |

## Result kinds (rows gold, columns predicted)

|  | pred intent | pred clarification | pred unsupported |
|---|---|---|---|
| gold intent | 85 | 2 | 2 |
| gold clarification | 7 | 16 | 0 |
| gold unsupported | 4 | 2 | 38 |
| clarification precision / recall | 80.0% [58.4%-91.9%] | 69.6% [49.1%-84.4%] |  |

## Reasons

| gold kind | n | kind correct | reason correct (given kind) |
|---|---|---|---|
| clarification | 23 | 69.6% [49.1%-84.4%] | 87.5% [64.0%-96.5%] |
| unsupported | 44 | 86.4% [73.3%-93.6%] | 94.7% [82.7%-98.5%] |

## Strict errors by type (n = 34)

| type | errors | share |
|---|---|---|
| intent predicted, non-intent expected | 11 | 32% |
| polarity (activate/deactivate, increase/decrease) | 8 | 24% |
| non-intent: wrong kind or reason | 6 | 18% |
| property (e.g. light vs shading) | 4 | 12% |
| non-intent predicted, intent expected | 4 | 12% |
| other action, same property | 1 | 3% |

## Per category

| category | n | strict | outcome |
|---|---|---|---|
| adversarial | 15 | 86.7% [62.1%-96.3%] | 93.3% [70.2%-98.8%] |
| ambiguous | 16 | 43.8% [23.1%-66.8%] | 56.2% [33.2%-76.9%] |
| environment | 15 | 86.7% [62.1%-96.3%] | 86.7% [62.1%-96.3%] |
| explicit | 18 | 94.4% [74.2%-99.0%] | 94.4% [74.2%-99.0%] |
| explicit_other_zone | 14 | 78.6% [52.4%-92.4%] | 78.6% [52.4%-92.4%] |
| following | 15 | 80.0% [54.8%-93.0%] | 80.0% [54.8%-93.0%] |
| implicit | 19 | 63.2% [41.0%-80.9%] | 63.2% [41.0%-80.9%] |
| out_of_scope | 14 | 100.0% [78.5%-100.0%] | 100.0% [78.5%-100.0%] |
| unsupported | 16 | 56.2% [33.2%-76.9%] | 62.5% [38.6%-81.5%] |
| zone_dependent | 14 | 100.0% [78.5%-100.0%] | 100.0% [78.5%-100.0%] |

## Per language

| language | n | strict | outcome |
|---|---|---|---|
| en | 111 | 79.3% [70.8%-85.8%] | 81.1% [72.8%-87.3%] |
| it | 45 | 75.6% [61.3%-85.8%] | 80.0% [66.2%-89.1%] |

## Per source

| source | n | strict | outcome |
|---|---|---|---|
| human | 30 | 83.3% [66.4%-92.7%] | 90.0% [74.4%-96.5%] |
| llm | 126 | 77.0% [68.9%-83.5%] | 78.6% [70.6%-84.8%] |
