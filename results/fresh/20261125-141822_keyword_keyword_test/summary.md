# 20261125-141822_keyword_keyword_test

grounder=keyword, model=None, provider=None, split=test, repeats=1, temperature=0.0

## CLASSic overview

| group | metric | value |
|---|---|---|
| Accuracy | predictions | 60 |
| Accuracy | kind accuracy | 78.3% [66.4%-86.9%] |
| Accuracy | strict accuracy | 73.3% [61.0%-82.9%] |
| Accuracy | outcome accuracy | 76.7% [64.6%-85.6%] |
| Accuracy | intent: all fields (gold intents) | 69.7% [52.7%-82.6%] |
| Security | injection cases handled (outcome correct) | 50.0% [18.8%-81.2%] |
| Security | injection-only cases with a command | 0 / 3 |
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
| Latency | mean s | 5.6e-05 |
| Latency | p50 s | 3.3e-05 |
| Latency | p95 s | 1.0e-04 |
| Latency | p50 ms | 0.03 |
| Latency | p95 ms | 0.10 |
| Stability | repeat agreement (all repeats identical) | - |
| Stability | EN-IT agreement (paraphrase pairs) | - |
| Stability | EN-IT pairs | 0 |
| Failures | invalid output after retries | 0 |
| Failures | service unavailable | 0 |

## Intent fields (gold intents, n = 33)

| field | accuracy |
|---|---|
| action | 81.8% [65.6%-91.4%] |
| controlledProperty | 81.8% [65.6%-91.4%] |
| scope | 69.7% [52.7%-82.6%] |
| persistence | 69.7% [52.7%-82.6%] |
| targetZoneId | 75.8% [59.0%-87.2%] |
| value | 81.8% [65.6%-91.4%] |
| all fields | 69.7% [52.7%-82.6%] |

## Result kinds (rows gold, columns predicted)

|  | pred intent | pred clarification | pred unsupported |
|---|---|---|---|
| gold intent | 27 | 3 | 3 |
| gold clarification | 1 | 7 | 2 |
| gold unsupported | 2 | 2 | 13 |
| clarification precision / recall | 58.3% [32.0%-80.7%] | 70.0% [39.7%-89.2%] |  |

## Reasons

| gold kind | n | kind correct | reason correct (given kind) |
|---|---|---|---|
| clarification | 10 | 70.0% [39.7%-89.2%] | 85.7% [48.7%-97.4%] |
| unsupported | 17 | 76.5% [52.7%-90.4%] | 100.0% [77.2%-100.0%] |

## Strict errors by type (n = 16)

| type | errors | share |
|---|---|---|
| non-intent predicted, intent expected | 5 | 31% |
| pair right, other field (scope, persistence, target, value) | 4 | 25% |
| non-intent: wrong kind or reason | 4 | 25% |
| intent predicted, non-intent expected | 3 | 19% |

## Per category

| category | n | strict | outcome |
|---|---|---|---|
| adversarial | 6 | 33.3% [9.7%-70.0%] | 50.0% [18.8%-81.2%] |
| ambiguous | 6 | 50.0% [18.8%-81.2%] | 50.0% [18.8%-81.2%] |
| environment | 6 | 100.0% [61.0%-100.0%] | 100.0% [61.0%-100.0%] |
| explicit | 6 | 100.0% [61.0%-100.0%] | 100.0% [61.0%-100.0%] |
| explicit_other_zone | 6 | 83.3% [43.6%-97.0%] | 83.3% [43.6%-97.0%] |
| following | 6 | 50.0% [18.8%-81.2%] | 50.0% [18.8%-81.2%] |
| implicit | 6 | 66.7% [30.0%-90.3%] | 83.3% [43.6%-97.0%] |
| out_of_scope | 6 | 50.0% [18.8%-81.2%] | 50.0% [18.8%-81.2%] |
| unsupported | 6 | 100.0% [61.0%-100.0%] | 100.0% [61.0%-100.0%] |
| zone_dependent | 6 | 100.0% [61.0%-100.0%] | 100.0% [61.0%-100.0%] |

## Per language

| language | n | strict | outcome |
|---|---|---|---|
| en | 40 | 75.0% [59.8%-85.8%] | 80.0% [65.2%-89.5%] |
| it | 20 | 70.0% [48.1%-85.5%] | 70.0% [48.1%-85.5%] |

## Per source

| source | n | strict | outcome |
|---|---|---|---|
| llm | 60 | 73.3% [61.0%-82.9%] | 76.7% [64.6%-85.6%] |
