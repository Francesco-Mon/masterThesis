# 20261121-131024_keyword_keyword_test

grounder=keyword, model=None, provider=None, split=test, repeats=1, temperature=0.0

## CLASSic overview

| group | metric | value |
|---|---|---|
| Accuracy | predictions | 156 |
| Accuracy | kind accuracy | 92.9% [87.8%-96.0%] |
| Accuracy | strict accuracy | 91.7% [86.3%-95.1%] |
| Accuracy | outcome accuracy | 93.6% [88.6%-96.5%] |
| Accuracy | intent: all fields (gold intents) | 89.9% [81.9%-94.6%] |
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
| Latency | mean s | 3.2e-05 |
| Latency | p50 s | 2.8e-05 |
| Latency | p95 s | 4.5e-05 |
| Latency | p50 ms | 0.03 |
| Latency | p95 ms | 0.05 |
| Stability | repeat agreement (all repeats identical) | - |
| Stability | EN-IT agreement (paraphrase pairs) | 91.7% [74.2%-97.7%] |
| Stability | EN-IT pairs | 24 |
| Failures | invalid output after retries | 0 |
| Failures | service unavailable | 0 |

## Intent fields (gold intents, n = 89)

| field | accuracy |
|---|---|
| action | 89.9% [81.9%-94.6%] |
| controlledProperty | 92.1% [84.6%-96.1%] |
| scope | 91.0% [83.3%-95.4%] |
| persistence | 91.0% [83.3%-95.4%] |
| targetZoneId | 92.1% [84.6%-96.1%] |
| value | 92.1% [84.6%-96.1%] |
| all fields | 89.9% [81.9%-94.6%] |

## Result kinds (rows gold, columns predicted)

|  | pred intent | pred clarification | pred unsupported |
|---|---|---|---|
| gold intent | 82 | 6 | 1 |
| gold clarification | 3 | 20 | 0 |
| gold unsupported | 0 | 1 | 43 |
| clarification precision / recall | 74.1% [55.3%-86.8%] | 87.0% [67.9%-95.5%] |  |

## Reasons

| gold kind | n | kind correct | reason correct (given kind) |
|---|---|---|---|
| clarification | 23 | 87.0% [67.9%-95.5%] | 90.0% [69.9%-97.2%] |
| unsupported | 44 | 97.7% [88.2%-99.6%] | 100.0% [91.8%-100.0%] |

## Strict errors by type (n = 13)

| type | errors | share |
|---|---|---|
| non-intent predicted, intent expected | 5 | 38% |
| intent predicted, non-intent expected | 3 | 23% |
| non-intent: wrong kind or reason | 3 | 23% |
| polarity (activate/deactivate, increase/decrease) | 2 | 15% |

## Per category

| category | n | strict | outcome |
|---|---|---|---|
| adversarial | 15 | 86.7% [62.1%-96.3%] | 93.3% [70.2%-98.8%] |
| ambiguous | 16 | 68.8% [44.4%-85.8%] | 81.2% [57.0%-93.4%] |
| environment | 15 | 93.3% [70.2%-98.8%] | 93.3% [70.2%-98.8%] |
| explicit | 18 | 100.0% [82.4%-100.0%] | 100.0% [82.4%-100.0%] |
| explicit_other_zone | 14 | 92.9% [68.5%-98.7%] | 92.9% [68.5%-98.7%] |
| following | 15 | 100.0% [79.6%-100.0%] | 100.0% [79.6%-100.0%] |
| implicit | 19 | 84.2% [62.4%-94.5%] | 84.2% [62.4%-94.5%] |
| out_of_scope | 14 | 100.0% [78.5%-100.0%] | 100.0% [78.5%-100.0%] |
| unsupported | 16 | 100.0% [80.6%-100.0%] | 100.0% [80.6%-100.0%] |
| zone_dependent | 14 | 92.9% [68.5%-98.7%] | 92.9% [68.5%-98.7%] |

## Per language

| language | n | strict | outcome |
|---|---|---|---|
| en | 111 | 91.9% [85.3%-95.7%] | 93.7% [87.6%-96.9%] |
| it | 45 | 91.1% [79.3%-96.5%] | 93.3% [82.1%-97.7%] |

## Per source

| source | n | strict | outcome |
|---|---|---|---|
| human | 30 | 96.7% [83.3%-99.4%] | 100.0% [88.6%-100.0%] |
| llm | 126 | 90.5% [84.1%-94.5%] | 92.1% [86.0%-95.6%] |
