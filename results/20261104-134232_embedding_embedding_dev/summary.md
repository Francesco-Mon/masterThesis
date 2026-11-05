# 20261104-134232_embedding_embedding_dev

grounder=embedding, model=None, provider=None, split=dev, repeats=1, temperature=0.0

## CLASSic overview

| group | metric | value |
|---|---|---|
| Accuracy | predictions | 54 |
| Accuracy | kind accuracy | 77.8% [65.1%-86.8%] |
| Accuracy | strict accuracy | 72.2% [59.1%-82.4%] |
| Accuracy | outcome accuracy | 72.2% [59.1%-82.4%] |
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
| Latency | mean s | 0.02 |
| Latency | p50 s | 0.01 |
| Latency | p95 s | 0.02 |
| Latency | p50 ms | 13.87 |
| Latency | p95 ms | 18.84 |
| Stability | repeat agreement (all repeats identical) | - |
| Stability | EN-IT agreement (paraphrase pairs) | 83.3% [43.6%-97.0%] |
| Stability | EN-IT pairs | 6 |
| Failures | invalid output after retries | 0 |
| Failures | service unavailable | 0 |

## Intent fields (gold intents, n = 32)

| field | accuracy |
|---|---|
| action | 78.1% [61.2%-89.0%] |
| controlledProperty | 87.5% [71.9%-95.0%] |
| scope | 87.5% [71.9%-95.0%] |
| persistence | 87.5% [71.9%-95.0%] |
| targetZoneId | 87.5% [71.9%-95.0%] |
| value | 87.5% [71.9%-95.0%] |
| all fields | 78.1% [61.2%-89.0%] |

## Result kinds (rows gold, columns predicted)

|  | pred intent | pred clarification | pred unsupported |
|---|---|---|---|
| gold intent | 28 | 0 | 4 |
| gold clarification | 3 | 4 | 1 |
| gold unsupported | 3 | 1 | 10 |
| clarification precision / recall | 80.0% [37.6%-96.4%] | 50.0% [21.5%-78.5%] |  |

## Reasons

| gold kind | n | kind correct | reason correct (given kind) |
|---|---|---|---|
| clarification | 8 | 50.0% [21.5%-78.5%] | 100.0% [51.0%-100.0%] |
| unsupported | 14 | 71.4% [45.4%-88.3%] | 100.0% [72.2%-100.0%] |

## Strict errors by type (n = 15)

| type | errors | share |
|---|---|---|
| intent predicted, non-intent expected | 6 | 40% |
| non-intent predicted, intent expected | 4 | 27% |
| polarity (activate/deactivate, increase/decrease) | 3 | 20% |
| non-intent: wrong kind or reason | 2 | 13% |

## Per category

| category | n | strict | outcome |
|---|---|---|---|
| adversarial | 5 | 20.0% [3.6%-62.4%] | 20.0% [3.6%-62.4%] |
| ambiguous | 5 | 20.0% [3.6%-62.4%] | 20.0% [3.6%-62.4%] |
| environment | 5 | 100.0% [56.6%-100.0%] | 100.0% [56.6%-100.0%] |
| explicit | 5 | 100.0% [56.6%-100.0%] | 100.0% [56.6%-100.0%] |
| explicit_other_zone | 6 | 100.0% [61.0%-100.0%] | 100.0% [61.0%-100.0%] |
| following | 5 | 80.0% [37.6%-96.4%] | 80.0% [37.6%-96.4%] |
| implicit | 5 | 60.0% [23.1%-88.2%] | 60.0% [23.1%-88.2%] |
| out_of_scope | 6 | 100.0% [61.0%-100.0%] | 100.0% [61.0%-100.0%] |
| unsupported | 6 | 33.3% [9.7%-70.0%] | 33.3% [9.7%-70.0%] |
| zone_dependent | 6 | 100.0% [61.0%-100.0%] | 100.0% [61.0%-100.0%] |

## Per language

| language | n | strict | outcome |
|---|---|---|---|
| en | 48 | 72.9% [59.0%-83.4%] | 72.9% [59.0%-83.4%] |
| it | 6 | 66.7% [30.0%-90.3%] | 66.7% [30.0%-90.3%] |

## Per source

| source | n | strict | outcome |
|---|---|---|---|
| llm | 54 | 72.2% [59.1%-82.4%] | 72.2% [59.1%-82.4%] |
