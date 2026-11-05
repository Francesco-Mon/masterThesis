# 20261102-225046_llm_openai-gpt-oss-120b_dev

grounder=llm, model=openai/gpt-oss-120b, provider=DekaLLM, split=dev, repeats=1, temperature=0.0

## CLASSic overview

| group | metric | value |
|---|---|---|
| Accuracy | predictions | 54 |
| Accuracy | kind accuracy | 96.3% [87.5%-99.0%] |
| Accuracy | strict accuracy | 88.9% [77.8%-94.8%] |
| Accuracy | outcome accuracy | 96.3% [87.5%-99.0%] |
| Accuracy | intent: all fields (gold intents) | 90.6% [75.8%-96.8%] |
| Security | injection cases handled (outcome correct) | 100.0% [56.6%-100.0%] |
| Security | injection-only cases with a command | 0 / 1 |
| Security | mixed cases with commands beyond the legitimate part | 0 / 4 |
| Security | raw grounder output off catalogue (all cases) | 0.0% [0.0%-6.6%] |
| Security | final commands off catalogue (must be 0) | 0 |
| Cost | total USD | 0.006355 |
| Cost | USD per 1000 requests | 0.1177 |
| Cost | prompt / completion tokens | 94536 / 19550 |
| Cost | tokens per request (prompt / completion) | 1751 / 362 |
| Cost | LLM calls (incl. retries) | 53 |
| Cost | requests needing a retry | 0 |
| Latency | requests measured (not cached) | 53 |
| Latency | mean s | 4.24 |
| Latency | p50 s | 3.84 |
| Latency | p95 s | 7.51 |
| Latency | p50 ms | 3843.00 |
| Latency | p95 ms | 7513.50 |
| Stability | repeat agreement (all repeats identical) | - |
| Stability | EN-IT agreement (paraphrase pairs) | 100.0% [61.0%-100.0%] |
| Stability | EN-IT pairs | 6 |
| Failures | invalid output after retries | 0 |
| Failures | service unavailable | 0 |

## Intent fields (gold intents, n = 32)

| field | accuracy |
|---|---|
| action | 96.9% [84.3%-99.4%] |
| controlledProperty | 96.9% [84.3%-99.4%] |
| scope | 93.8% [79.9%-98.3%] |
| persistence | 93.8% [79.9%-98.3%] |
| targetZoneId | 96.9% [84.3%-99.4%] |
| value | 96.9% [84.3%-99.4%] |
| all fields | 90.6% [75.8%-96.8%] |

## Result kinds (rows gold, columns predicted)

|  | pred intent | pred clarification | pred unsupported |
|---|---|---|---|
| gold intent | 31 | 0 | 1 |
| gold clarification | 1 | 7 | 0 |
| gold unsupported | 0 | 0 | 14 |
| clarification precision / recall | 100.0% [64.6%-100.0%] | 87.5% [52.9%-97.8%] |  |

## Reasons

| gold kind | n | kind correct | reason correct (given kind) |
|---|---|---|---|
| clarification | 8 | 87.5% [52.9%-97.8%] | 100.0% [64.6%-100.0%] |
| unsupported | 14 | 100.0% [78.5%-100.0%] | 78.6% [52.4%-92.4%] |

## Strict errors by type (n = 6)

| type | errors | share |
|---|---|---|
| pair right, other field (scope, persistence, target, value) | 2 | 33% |
| non-intent: wrong kind or reason | 2 | 33% |
| non-intent predicted, intent expected | 1 | 17% |
| intent predicted, non-intent expected | 1 | 17% |

## Per category

| category | n | strict | outcome |
|---|---|---|---|
| adversarial | 5 | 80.0% [37.6%-96.4%] | 100.0% [56.6%-100.0%] |
| ambiguous | 5 | 80.0% [37.6%-96.4%] | 80.0% [37.6%-96.4%] |
| environment | 5 | 100.0% [56.6%-100.0%] | 100.0% [56.6%-100.0%] |
| explicit | 5 | 80.0% [37.6%-96.4%] | 80.0% [37.6%-96.4%] |
| explicit_other_zone | 6 | 100.0% [61.0%-100.0%] | 100.0% [61.0%-100.0%] |
| following | 5 | 60.0% [23.1%-88.2%] | 100.0% [56.6%-100.0%] |
| implicit | 5 | 100.0% [56.6%-100.0%] | 100.0% [56.6%-100.0%] |
| out_of_scope | 6 | 100.0% [61.0%-100.0%] | 100.0% [61.0%-100.0%] |
| unsupported | 6 | 83.3% [43.6%-97.0%] | 100.0% [61.0%-100.0%] |
| zone_dependent | 6 | 100.0% [61.0%-100.0%] | 100.0% [61.0%-100.0%] |

## Per language

| language | n | strict | outcome |
|---|---|---|---|
| en | 48 | 87.5% [75.3%-94.1%] | 95.8% [86.0%-98.8%] |
| it | 6 | 100.0% [61.0%-100.0%] | 100.0% [61.0%-100.0%] |

## Per source

| source | n | strict | outcome |
|---|---|---|---|
| llm | 54 | 88.9% [77.8%-94.8%] | 96.3% [87.5%-99.0%] |
