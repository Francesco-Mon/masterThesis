# 20261121-155508_llm_mistralai-mistral-large-4-0_test

grounder=llm, model=mistralai/mistral-large-4-0, provider=mistral/zdr, split=test, repeats=3, temperature=0.0

## CLASSic overview

| group | metric | value |
|---|---|---|
| Accuracy | predictions | 468 |
| Accuracy | kind accuracy | 97.0% [95.0%-98.2%] |
| Accuracy | strict accuracy | 90.2% [87.1%-92.5%] |
| Accuracy | outcome accuracy | 95.7% [93.5%-97.2%] |
| Accuracy | intent: all fields (gold intents) | 96.6% [93.7%-98.2%] |
| Security | injection cases handled (outcome correct) | 93.3% [82.1%-97.7%] |
| Security | injection-only cases with a command | 3 / 39 |
| Security | mixed cases with commands beyond the legitimate part | 0 / 6 |
| Security | raw grounder output off catalogue (all cases) | 0.0% [0.0%-0.8%] |
| Security | final commands off catalogue (must be 0) | 0 |
| Cost | total USD | 1.329821 |
| Cost | USD per 1000 requests | 2.8415 |
| Cost | prompt / completion tokens | 957658 / 456723 |
| Cost | tokens per request (prompt / completion) | 2046 / 976 |
| Cost | LLM calls (incl. retries) | 456 |
| Cost | requests needing a retry | 0 |
| Latency | requests measured (not cached) | 456 |
| Latency | mean s | 17.93 |
| Latency | p50 s | 11.75 |
| Latency | p95 s | 50.83 |
| Latency | p50 ms | 11748.80 |
| Latency | p95 ms | 50828.00 |
| Stability | repeat agreement (all repeats identical) | 94.9% [90.2%-97.4%] |
| Stability | EN-IT agreement (paraphrase pairs) | 95.8% [79.8%-99.3%] |
| Stability | EN-IT pairs | 24 |
| Failures | invalid output after retries | 0 |
| Failures | service unavailable | 1 |

## Intent fields (gold intents, n = 267)

| field | accuracy |
|---|---|
| action | 99.6% [97.9%-99.9%] |
| controlledProperty | 99.6% [97.9%-99.9%] |
| scope | 96.6% [93.7%-98.2%] |
| persistence | 99.6% [97.9%-99.9%] |
| targetZoneId | 99.6% [97.9%-99.9%] |
| value | 99.6% [97.9%-99.9%] |
| all fields | 96.6% [93.7%-98.2%] |

## Result kinds (rows gold, columns predicted)

|  | pred intent | pred clarification | pred unsupported |
|---|---|---|---|
| gold intent | 266 | 1 | 0 |
| gold clarification | 7 | 59 | 3 |
| gold unsupported | 3 | 0 | 129 |
| clarification precision / recall | 98.3% [91.1%-99.7%] | 85.5% [75.3%-91.9%] |  |

## Reasons

| gold kind | n | kind correct | reason correct (given kind) |
|---|---|---|---|
| clarification | 69 | 85.5% [75.3%-91.9%] | 93.2% [83.8%-97.3%] |
| unsupported | 132 | 97.7% [93.5%-99.2%] | 84.5% [77.3%-89.7%] |

## Strict errors by type (n = 46)

| type | errors | share |
|---|---|---|
| non-intent: wrong kind or reason | 27 | 59% |
| intent predicted, non-intent expected | 10 | 22% |
| pair right, other field (scope, persistence, target, value) | 8 | 17% |
| non-intent predicted, intent expected | 1 | 2% |

## Per category

| category | n | strict | outcome |
|---|---|---|---|
| adversarial | 45 | 64.4% [49.8%-76.8%] | 93.3% [82.1%-97.7%] |
| ambiguous | 48 | 70.8% [56.8%-81.8%] | 79.2% [65.7%-88.3%] |
| environment | 45 | 100.0% [92.1%-100.0%] | 100.0% [92.1%-100.0%] |
| explicit | 54 | 100.0% [93.4%-100.0%] | 100.0% [93.4%-100.0%] |
| explicit_other_zone | 42 | 100.0% [91.6%-100.0%] | 100.0% [91.6%-100.0%] |
| following | 45 | 80.0% [66.2%-89.1%] | 84.4% [71.2%-92.3%] |
| implicit | 57 | 100.0% [93.7%-100.0%] | 100.0% [93.7%-100.0%] |
| out_of_scope | 42 | 100.0% [91.6%-100.0%] | 100.0% [91.6%-100.0%] |
| unsupported | 48 | 85.4% [72.8%-92.8%] | 100.0% [92.6%-100.0%] |
| zone_dependent | 42 | 100.0% [91.6%-100.0%] | 100.0% [91.6%-100.0%] |

## Per language

| language | n | strict | outcome |
|---|---|---|---|
| en | 333 | 89.5% [85.7%-92.3%] | 96.4% [93.8%-97.9%] |
| it | 135 | 91.9% [86.0%-95.4%] | 94.1% [88.7%-97.0%] |

## Per source

| source | n | strict | outcome |
|---|---|---|---|
| human | 90 | 92.2% [84.8%-96.2%] | 95.6% [89.1%-98.3%] |
| llm | 378 | 89.7% [86.2%-92.4%] | 95.8% [93.2%-97.4%] |
