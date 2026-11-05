# 20261102-215232_llm_openai-gpt-oss-120b_dev

grounder=llm, model=openai/gpt-oss-120b, provider=DekaLLM, split=dev, repeats=1, temperature=0.0

## CLASSic overview

| group | metric | value |
|---|---|---|
| Accuracy | predictions | 54 |
| Accuracy | kind accuracy | 74.1% [61.1%-83.9%] |
| Accuracy | strict accuracy | 70.4% [57.2%-80.9%] |
| Accuracy | outcome accuracy | 74.1% [61.1%-83.9%] |
| Accuracy | intent: all fields (gold intents) | 59.4% [42.3%-74.5%] |
| Security | injection cases handled (outcome correct) | 40.0% [11.8%-76.9%] |
| Security | injection-only cases with a command | 0 / 1 |
| Security | mixed cases with commands beyond the legitimate part | 0 / 4 |
| Security | raw grounder output off catalogue (all cases) | 0.0% [0.0%-6.6%] |
| Security | final commands off catalogue (must be 0) | 0 |
| Cost | total USD | 0.006046 |
| Cost | USD per 1000 requests | 0.1120 |
| Cost | prompt / completion tokens | 71905 / 21602 |
| Cost | tokens per request (prompt / completion) | 1332 / 400 |
| Cost | LLM calls (incl. retries) | 53 |
| Cost | requests needing a retry | 0 |
| Latency | requests measured (not cached) | 53 |
| Latency | mean s | 6.71 |
| Latency | p50 s | 5.90 |
| Latency | p95 s | 12.10 |
| Latency | p50 ms | 5900.60 |
| Latency | p95 ms | 12099.50 |
| Stability | repeat agreement (all repeats identical) | - |
| Stability | EN-IT agreement (paraphrase pairs) | 83.3% [43.6%-97.0%] |
| Stability | EN-IT pairs | 6 |
| Failures | invalid output after retries | 0 |
| Failures | service unavailable | 0 |

## Intent fields (gold intents, n = 32)

| field | accuracy |
|---|---|
| action | 62.5% [45.3%-77.1%] |
| controlledProperty | 62.5% [45.3%-77.1%] |
| scope | 59.4% [42.3%-74.5%] |
| persistence | 62.5% [45.3%-77.1%] |
| targetZoneId | 62.5% [45.3%-77.1%] |
| value | 62.5% [45.3%-77.1%] |
| all fields | 59.4% [42.3%-74.5%] |

## Result kinds (rows gold, columns predicted)

|  | pred intent | pred clarification | pred unsupported |
|---|---|---|---|
| gold intent | 20 | 7 | 5 |
| gold clarification | 0 | 6 | 2 |
| gold unsupported | 0 | 0 | 14 |
| clarification precision / recall | 46.2% [23.2%-70.9%] | 75.0% [40.9%-92.9%] |  |

## Reasons

| gold kind | n | kind correct | reason correct (given kind) |
|---|---|---|---|
| clarification | 8 | 75.0% [40.9%-92.9%] | 100.0% [61.0%-100.0%] |
| unsupported | 14 | 100.0% [78.5%-100.0%] | 78.6% [52.4%-92.4%] |

## Strict errors by type (n = 16)

| type | errors | share |
|---|---|---|
| non-intent predicted, intent expected | 12 | 75% |
| non-intent: wrong kind or reason | 3 | 19% |
| pair right, other field (scope, persistence, target, value) | 1 | 6% |

## Per category

| category | n | strict | outcome |
|---|---|---|---|
| adversarial | 5 | 20.0% [3.6%-62.4%] | 40.0% [11.8%-76.9%] |
| ambiguous | 5 | 100.0% [56.6%-100.0%] | 100.0% [56.6%-100.0%] |
| environment | 5 | 60.0% [23.1%-88.2%] | 60.0% [23.1%-88.2%] |
| explicit | 5 | 80.0% [37.6%-96.4%] | 80.0% [37.6%-96.4%] |
| explicit_other_zone | 6 | 100.0% [61.0%-100.0%] | 100.0% [61.0%-100.0%] |
| following | 5 | 60.0% [23.1%-88.2%] | 60.0% [23.1%-88.2%] |
| implicit | 5 | 40.0% [11.8%-76.9%] | 40.0% [11.8%-76.9%] |
| out_of_scope | 6 | 100.0% [61.0%-100.0%] | 100.0% [61.0%-100.0%] |
| unsupported | 6 | 83.3% [43.6%-97.0%] | 100.0% [61.0%-100.0%] |
| zone_dependent | 6 | 50.0% [18.8%-81.2%] | 50.0% [18.8%-81.2%] |

## Per language

| language | n | strict | outcome |
|---|---|---|---|
| en | 48 | 72.9% [59.0%-83.4%] | 77.1% [63.5%-86.7%] |
| it | 6 | 50.0% [18.8%-81.2%] | 50.0% [18.8%-81.2%] |

## Per source

| source | n | strict | outcome |
|---|---|---|---|
| llm | 54 | 70.4% [57.2%-80.9%] | 74.1% [61.1%-83.9%] |
