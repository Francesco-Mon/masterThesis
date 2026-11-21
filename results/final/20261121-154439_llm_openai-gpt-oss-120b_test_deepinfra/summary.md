# 20261121-154439_llm_openai-gpt-oss-120b_test_deepinfra

grounder=llm, model=openai/gpt-oss-120b, provider=DeepInfra, split=test, repeats=3, temperature=0.0

## CLASSic overview

| group | metric | value |
|---|---|---|
| Accuracy | predictions | 468 |
| Accuracy | kind accuracy | 95.1% [92.7%-96.7%] |
| Accuracy | strict accuracy | 81.0% [77.2%-84.3%] |
| Accuracy | outcome accuracy | 91.5% [88.6%-93.7%] |
| Accuracy | intent: all fields (gold intents) | 85.8% [81.1%-89.5%] |
| Security | injection cases handled (outcome correct) | 93.3% [82.1%-97.7%] |
| Security | injection-only cases with a command | 3 / 39 |
| Security | mixed cases with commands beyond the legitimate part | 0 / 6 |
| Security | raw grounder output off catalogue (all cases) | 0.0% [0.0%-0.8%] |
| Security | final commands off catalogue (must be 0) | 0 |
| Cost | total USD | 0.050111 |
| Cost | USD per 1000 requests | 0.1071 |
| Cost | prompt / completion tokens | 798189 / 177340 |
| Cost | tokens per request (prompt / completion) | 1706 / 379 |
| Cost | LLM calls (incl. retries) | 456 |
| Cost | requests needing a retry | 0 |
| Latency | requests measured (not cached) | 456 |
| Latency | mean s | 22.98 |
| Latency | p50 s | 19.60 |
| Latency | p95 s | 50.21 |
| Latency | p50 ms | 19604.20 |
| Latency | p95 ms | 50209.40 |
| Stability | repeat agreement (all repeats identical) | 90.4% [84.7%-94.1%] |
| Stability | EN-IT agreement (paraphrase pairs) | 79.2% [59.5%-90.8%] |
| Stability | EN-IT pairs | 24 |
| Failures | invalid output after retries | 0 |
| Failures | service unavailable | 5 |

## Intent fields (gold intents, n = 267)

| field | accuracy |
|---|---|
| action | 95.5% [92.3%-97.4%] |
| controlledProperty | 95.5% [92.3%-97.4%] |
| scope | 88.0% [83.6%-91.4%] |
| persistence | 86.9% [82.3%-90.4%] |
| targetZoneId | 95.5% [92.3%-97.4%] |
| value | 95.5% [92.3%-97.4%] |
| all fields | 85.8% [81.1%-89.5%] |

## Result kinds (rows gold, columns predicted)

|  | pred intent | pred clarification | pred unsupported |
|---|---|---|---|
| gold intent | 255 | 9 | 3 |
| gold clarification | 5 | 61 | 3 |
| gold unsupported | 3 | 0 | 129 |
| clarification precision / recall | 87.1% [77.3%-93.1%] | 88.4% [78.8%-94.0%] |  |

## Reasons

| gold kind | n | kind correct | reason correct (given kind) |
|---|---|---|---|
| clarification | 69 | 88.4% [78.8%-94.0%] | 86.9% [76.2%-93.2%] |
| unsupported | 132 | 97.7% [93.5%-99.2%] | 75.2% [67.1%-81.8%] |

## Strict errors by type (n = 89)

| type | errors | share |
|---|---|---|
| non-intent: wrong kind or reason | 43 | 48% |
| pair right, other field (scope, persistence, target, value) | 26 | 29% |
| non-intent predicted, intent expected | 12 | 13% |
| intent predicted, non-intent expected | 8 | 9% |

## Per category

| category | n | strict | outcome |
|---|---|---|---|
| adversarial | 45 | 60.0% [45.5%-73.0%] | 93.3% [82.1%-97.7%] |
| ambiguous | 48 | 66.7% [52.5%-78.3%] | 83.3% [70.4%-91.3%] |
| environment | 45 | 97.8% [88.4%-99.6%] | 97.8% [88.4%-99.6%] |
| explicit | 54 | 100.0% [93.4%-100.0%] | 100.0% [93.4%-100.0%] |
| explicit_other_zone | 42 | 100.0% [91.6%-100.0%] | 100.0% [91.6%-100.0%] |
| following | 45 | 31.1% [19.5%-45.7%] | 51.1% [37.0%-65.0%] |
| implicit | 57 | 89.5% [78.9%-95.1%] | 89.5% [78.9%-95.1%] |
| out_of_scope | 42 | 97.6% [87.7%-99.6%] | 100.0% [91.6%-100.0%] |
| unsupported | 48 | 66.7% [52.5%-78.3%] | 100.0% [92.6%-100.0%] |
| zone_dependent | 42 | 100.0% [91.6%-100.0%] | 100.0% [91.6%-100.0%] |

## Per language

| language | n | strict | outcome |
|---|---|---|---|
| en | 333 | 81.4% [76.9%-85.2%] | 91.6% [88.1%-94.1%] |
| it | 135 | 80.0% [72.5%-85.9%] | 91.1% [85.1%-94.8%] |

## Per source

| source | n | strict | outcome |
|---|---|---|---|
| human | 90 | 76.7% [66.9%-84.2%] | 90.0% [82.1%-94.6%] |
| llm | 378 | 82.0% [77.8%-85.6%] | 91.8% [88.6%-94.2%] |
