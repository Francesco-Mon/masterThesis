# 20261121-152330_llm_nvidia-nemotron-3.5-super-vl-free_test

grounder=llm, model=nvidia/nemotron-3.5-super-vl:free, provider=None, split=test, repeats=3, temperature=0.0

## CLASSic overview

| group | metric | value |
|---|---|---|
| Accuracy | predictions | 468 |
| Accuracy | kind accuracy | 96.6% [94.5%-97.9%] |
| Accuracy | strict accuracy | 88.9% [85.7%-91.4%] |
| Accuracy | outcome accuracy | 94.2% [91.7%-96.0%] |
| Accuracy | intent: all fields (gold intents) | 92.9% [89.2%-95.4%] |
| Security | injection cases handled (outcome correct) | 97.8% [88.4%-99.6%] |
| Security | injection-only cases with a command | 1 / 39 |
| Security | mixed cases with commands beyond the legitimate part | 0 / 6 |
| Security | raw grounder output off catalogue (all cases) | 0.0% [0.0%-0.8%] |
| Security | final commands off catalogue (must be 0) | 0 |
| Cost | total USD | 0.000000 |
| Cost | USD per 1000 requests | 0.0000 |
| Cost | prompt / completion tokens | 816924 / 348459 |
| Cost | tokens per request (prompt / completion) | 1746 / 745 |
| Cost | LLM calls (incl. retries) | 456 |
| Cost | requests needing a retry | 0 |
| Latency | requests measured (not cached) | 456 |
| Latency | mean s | 6.85 |
| Latency | p50 s | 4.47 |
| Latency | p95 s | 17.33 |
| Latency | p50 ms | 4474.90 |
| Latency | p95 ms | 17333.00 |
| Stability | repeat agreement (all repeats identical) | 87.2% [81.0%-91.5%] |
| Stability | EN-IT agreement (paraphrase pairs) | 87.5% [69.0%-95.7%] |
| Stability | EN-IT pairs | 24 |
| Failures | invalid output after retries | 0 |
| Failures | service unavailable | 0 |

## Intent fields (gold intents, n = 267)

| field | accuracy |
|---|---|
| action | 98.9% [96.7%-99.6%] |
| controlledProperty | 98.9% [96.7%-99.6%] |
| scope | 92.9% [89.2%-95.4%] |
| persistence | 95.5% [92.3%-97.4%] |
| targetZoneId | 98.9% [96.7%-99.6%] |
| value | 98.9% [96.7%-99.6%] |
| all fields | 92.9% [89.2%-95.4%] |

## Result kinds (rows gold, columns predicted)

|  | pred intent | pred clarification | pred unsupported |
|---|---|---|---|
| gold intent | 264 | 3 | 0 |
| gold clarification | 6 | 60 | 3 |
| gold unsupported | 2 | 2 | 128 |
| clarification precision / recall | 92.3% [83.2%-96.7%] | 87.0% [77.0%-93.0%] |  |

## Reasons

| gold kind | n | kind correct | reason correct (given kind) |
|---|---|---|---|
| clarification | 69 | 87.0% [77.0%-93.0%] | 93.3% [84.1%-97.4%] |
| unsupported | 132 | 97.0% [92.5%-98.8%] | 86.7% [79.8%-91.5%] |

## Strict errors by type (n = 52)

| type | errors | share |
|---|---|---|
| non-intent: wrong kind or reason | 25 | 48% |
| pair right, other field (scope, persistence, target, value) | 16 | 31% |
| intent predicted, non-intent expected | 8 | 15% |
| non-intent predicted, intent expected | 3 | 6% |

## Per category

| category | n | strict | outcome |
|---|---|---|---|
| adversarial | 45 | 71.1% [56.6%-82.3%] | 97.8% [88.4%-99.6%] |
| ambiguous | 48 | 72.9% [59.0%-83.4%] | 81.2% [68.1%-89.8%] |
| environment | 45 | 100.0% [92.1%-100.0%] | 100.0% [92.1%-100.0%] |
| explicit | 54 | 100.0% [93.4%-100.0%] | 100.0% [93.4%-100.0%] |
| explicit_other_zone | 42 | 100.0% [91.6%-100.0%] | 100.0% [91.6%-100.0%] |
| following | 45 | 57.8% [43.3%-71.0%] | 64.4% [49.8%-76.8%] |
| implicit | 57 | 100.0% [93.7%-100.0%] | 100.0% [93.7%-100.0%] |
| out_of_scope | 42 | 100.0% [91.6%-100.0%] | 100.0% [91.6%-100.0%] |
| unsupported | 48 | 85.4% [72.8%-92.8%] | 97.9% [89.1%-99.6%] |
| zone_dependent | 42 | 100.0% [91.6%-100.0%] | 100.0% [91.6%-100.0%] |

## Per language

| language | n | strict | outcome |
|---|---|---|---|
| en | 333 | 88.9% [85.1%-91.8%] | 94.6% [91.6%-96.6%] |
| it | 135 | 88.9% [82.5%-93.2%] | 93.3% [87.8%-96.5%] |

## Per source

| source | n | strict | outcome |
|---|---|---|---|
| human | 90 | 90.0% [82.1%-94.6%] | 93.3% [86.2%-96.9%] |
| llm | 378 | 88.6% [85.0%-91.4%] | 94.4% [91.7%-96.3%] |
