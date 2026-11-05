# 20261102-215232_llm_nvidia-nemotron-3.5-super-vl-free_dev

grounder=llm, model=nvidia/nemotron-3.5-super-vl:free, provider=None, split=dev, repeats=1, temperature=0.0

## CLASSic overview

| group | metric | value |
|---|---|---|
| Accuracy | predictions | 54 |
| Accuracy | kind accuracy | 94.4% [84.9%-98.1%] |
| Accuracy | strict accuracy | 90.7% [80.1%-96.0%] |
| Accuracy | outcome accuracy | 92.6% [82.4%-97.1%] |
| Accuracy | intent: all fields (gold intents) | 87.5% [71.9%-95.0%] |
| Security | injection cases handled (outcome correct) | 100.0% [56.6%-100.0%] |
| Security | injection-only cases with a command | 0 / 1 |
| Security | mixed cases with commands beyond the legitimate part | 0 / 4 |
| Security | raw grounder output off catalogue (all cases) | 0.0% [0.0%-6.6%] |
| Security | final commands off catalogue (must be 0) | 0 |
| Cost | total USD | 0.000000 |
| Cost | USD per 1000 requests | 0.0000 |
| Cost | prompt / completion tokens | 71936 / 37482 |
| Cost | tokens per request (prompt / completion) | 1332 / 694 |
| Cost | LLM calls (incl. retries) | 53 |
| Cost | requests needing a retry | 0 |
| Latency | requests measured (not cached) | 53 |
| Latency | mean s | 4.16 |
| Latency | p50 s | 3.09 |
| Latency | p95 s | 10.03 |
| Latency | p50 ms | 3086.00 |
| Latency | p95 ms | 10025.40 |
| Stability | repeat agreement (all repeats identical) | - |
| Stability | EN-IT agreement (paraphrase pairs) | 83.3% [43.6%-97.0%] |
| Stability | EN-IT pairs | 6 |
| Failures | invalid output after retries | 0 |
| Failures | service unavailable | 0 |

## Intent fields (gold intents, n = 32)

| field | accuracy |
|---|---|
| action | 93.8% [79.9%-98.3%] |
| controlledProperty | 93.8% [79.9%-98.3%] |
| scope | 87.5% [71.9%-95.0%] |
| persistence | 93.8% [79.9%-98.3%] |
| targetZoneId | 93.8% [79.9%-98.3%] |
| value | 93.8% [79.9%-98.3%] |
| all fields | 87.5% [71.9%-95.0%] |

## Result kinds (rows gold, columns predicted)

|  | pred intent | pred clarification | pred unsupported |
|---|---|---|---|
| gold intent | 30 | 1 | 1 |
| gold clarification | 0 | 7 | 1 |
| gold unsupported | 0 | 0 | 14 |
| clarification precision / recall | 87.5% [52.9%-97.8%] | 87.5% [52.9%-97.8%] |  |

## Reasons

| gold kind | n | kind correct | reason correct (given kind) |
|---|---|---|---|
| clarification | 8 | 87.5% [52.9%-97.8%] | 100.0% [64.6%-100.0%] |
| unsupported | 14 | 100.0% [78.5%-100.0%] | 85.7% [60.1%-96.0%] |

## Strict errors by type (n = 5)

| type | errors | share |
|---|---|---|
| non-intent predicted, intent expected | 2 | 40% |
| pair right, other field (scope, persistence, target, value) | 2 | 40% |
| non-intent: wrong kind or reason | 1 | 20% |

## Per category

| category | n | strict | outcome |
|---|---|---|---|
| adversarial | 5 | 80.0% [37.6%-96.4%] | 100.0% [56.6%-100.0%] |
| ambiguous | 5 | 100.0% [56.6%-100.0%] | 100.0% [56.6%-100.0%] |
| environment | 5 | 80.0% [37.6%-96.4%] | 80.0% [37.6%-96.4%] |
| explicit | 5 | 100.0% [56.6%-100.0%] | 100.0% [56.6%-100.0%] |
| explicit_other_zone | 6 | 100.0% [61.0%-100.0%] | 100.0% [61.0%-100.0%] |
| following | 5 | 60.0% [23.1%-88.2%] | 60.0% [23.1%-88.2%] |
| implicit | 5 | 100.0% [56.6%-100.0%] | 100.0% [56.6%-100.0%] |
| out_of_scope | 6 | 100.0% [61.0%-100.0%] | 100.0% [61.0%-100.0%] |
| unsupported | 6 | 100.0% [61.0%-100.0%] | 100.0% [61.0%-100.0%] |
| zone_dependent | 6 | 83.3% [43.6%-97.0%] | 83.3% [43.6%-97.0%] |

## Per language

| language | n | strict | outcome |
|---|---|---|---|
| en | 48 | 89.6% [77.8%-95.5%] | 91.7% [80.4%-96.7%] |
| it | 6 | 100.0% [61.0%-100.0%] | 100.0% [61.0%-100.0%] |

## Per source

| source | n | strict | outcome |
|---|---|---|---|
| llm | 54 | 90.7% [80.1%-96.0%] | 92.6% [82.4%-97.1%] |
