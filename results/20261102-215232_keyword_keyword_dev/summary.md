# 20261102-215232_keyword_keyword_dev

grounder=keyword, model=None, provider=None, split=dev, repeats=1, temperature=0.0

## CLASSic overview

| group | metric | value |
|---|---|---|
| Accuracy | predictions | 54 |
| Accuracy | kind accuracy | 85.2% [73.4%-92.3%] |
| Accuracy | strict accuracy | 85.2% [73.4%-92.3%] |
| Accuracy | outcome accuracy | 85.2% [73.4%-92.3%] |
| Accuracy | intent: all fields (gold intents) | 78.1% [61.2%-89.0%] |
| Security | injection cases handled (outcome correct) | 20.0% [3.6%-62.4%] |
| Security | injection-only cases with a command | 0 / 1 |
| Security | mixed cases with commands beyond the legitimate part | 0 / 4 |
| Security | raw grounder output off catalogue (all cases) | 0.0% [0.0%-6.6%] |
| Security | final commands off catalogue (must be 0) | 0 |
| Cost | total USD | 0.000000 |
| Cost | USD per 1000 requests | 0.0000 |
| Cost | prompt / completion tokens | 0 / 0 |
| Cost | tokens per request (prompt / completion) | 0 / 0 |
| Cost | LLM calls (incl. retries) | 0 |
| Cost | requests needing a retry | 0 |
| Latency | requests measured (not cached) | 54 |
| Latency | mean s | 4.8e-05 |
| Latency | p50 s | 2.5e-05 |
| Latency | p95 s | 1.2e-04 |
| Latency | p50 ms | 0.03 |
| Latency | p95 ms | 0.12 |
| Stability | repeat agreement (all repeats identical) | - |
| Stability | EN-IT agreement (paraphrase pairs) | 100.0% [61.0%-100.0%] |
| Stability | EN-IT pairs | 6 |
| Failures | invalid output after retries | 0 |
| Failures | service unavailable | 0 |

## Intent fields (gold intents, n = 32)

| field | accuracy |
|---|---|
| action | 78.1% [61.2%-89.0%] |
| controlledProperty | 81.2% [64.7%-91.1%] |
| scope | 81.2% [64.7%-91.1%] |
| persistence | 81.2% [64.7%-91.1%] |
| targetZoneId | 81.2% [64.7%-91.1%] |
| value | 81.2% [64.7%-91.1%] |
| all fields | 78.1% [61.2%-89.0%] |

## Result kinds (rows gold, columns predicted)

|  | pred intent | pred clarification | pred unsupported |
|---|---|---|---|
| gold intent | 26 | 2 | 4 |
| gold clarification | 2 | 6 | 0 |
| gold unsupported | 0 | 0 | 14 |
| clarification precision / recall | 75.0% [40.9%-92.9%] | 75.0% [40.9%-92.9%] |  |

## Reasons

| gold kind | n | kind correct | reason correct (given kind) |
|---|---|---|---|
| clarification | 8 | 75.0% [40.9%-92.9%] | 100.0% [61.0%-100.0%] |
| unsupported | 14 | 100.0% [78.5%-100.0%] | 92.9% [68.5%-98.7%] |

## Strict errors by type (n = 8)

| type | errors | share |
|---|---|---|
| non-intent predicted, intent expected | 5 | 62% |
| intent predicted, non-intent expected | 2 | 25% |
| polarity (activate/deactivate, increase/decrease) | 1 | 12% |

## Per category

| category | n | strict | outcome |
|---|---|---|---|
| adversarial | 5 | 20.0% [3.6%-62.4%] | 20.0% [3.6%-62.4%] |
| ambiguous | 5 | 60.0% [23.1%-88.2%] | 60.0% [23.1%-88.2%] |
| environment | 5 | 100.0% [56.6%-100.0%] | 100.0% [56.6%-100.0%] |
| explicit | 5 | 100.0% [56.6%-100.0%] | 100.0% [56.6%-100.0%] |
| explicit_other_zone | 6 | 100.0% [61.0%-100.0%] | 100.0% [61.0%-100.0%] |
| following | 5 | 100.0% [56.6%-100.0%] | 100.0% [56.6%-100.0%] |
| implicit | 5 | 60.0% [23.1%-88.2%] | 60.0% [23.1%-88.2%] |
| out_of_scope | 6 | 100.0% [61.0%-100.0%] | 100.0% [61.0%-100.0%] |
| unsupported | 6 | 100.0% [61.0%-100.0%] | 100.0% [61.0%-100.0%] |
| zone_dependent | 6 | 100.0% [61.0%-100.0%] | 100.0% [61.0%-100.0%] |

## Per language

| language | n | strict | outcome |
|---|---|---|---|
| en | 48 | 85.4% [72.8%-92.8%] | 85.4% [72.8%-92.8%] |
| it | 6 | 83.3% [43.6%-97.0%] | 83.3% [43.6%-97.0%] |

## Per source

| source | n | strict | outcome |
|---|---|---|---|
| llm | 54 | 85.2% [73.4%-92.3%] | 85.2% [73.4%-92.3%] |
