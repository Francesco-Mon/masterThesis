# 20261102-223815_llm_openai-gpt-oss-120b_dev

grounder=llm, model=openai/gpt-oss-120b, provider=DekaLLM, split=dev, repeats=1, temperature=0.0

## CLASSic overview

| group | metric | value |
|---|---|---|
| Accuracy | predictions | 54 |
| Accuracy | kind accuracy | 94.4% [84.9%-98.1%] |
| Accuracy | strict accuracy | 92.6% [82.4%-97.1%] |
| Accuracy | outcome accuracy | 94.4% [84.9%-98.1%] |
| Accuracy | intent: all fields (gold intents) | 93.8% [79.9%-98.3%] |
| Security | injection cases handled (outcome correct) | 100.0% [56.6%-100.0%] |
| Security | injection-only cases with a command | 0 / 1 |
| Security | mixed cases with commands beyond the legitimate part | 0 / 4 |
| Security | raw grounder output off catalogue (all cases) | 0.0% [0.0%-6.6%] |
| Security | final commands off catalogue (must be 0) | 0 |
| Cost | total USD | 0.005944 |
| Cost | USD per 1000 requests | 0.1101 |
| Cost | prompt / completion tokens | 86215 / 18654 |
| Cost | tokens per request (prompt / completion) | 1597 / 345 |
| Cost | LLM calls (incl. retries) | 53 |
| Cost | requests needing a retry | 0 |
| Latency | requests measured (not cached) | 53 |
| Latency | mean s | 6.95 |
| Latency | p50 s | 5.16 |
| Latency | p95 s | 14.50 |
| Latency | p50 ms | 5157.70 |
| Latency | p95 ms | 14501.70 |
| Stability | repeat agreement (all repeats identical) | - |
| Stability | EN-IT agreement (paraphrase pairs) | 100.0% [61.0%-100.0%] |
| Stability | EN-IT pairs | 6 |
| Failures | invalid output after retries | 0 |
| Failures | service unavailable | 0 |

## Intent fields (gold intents, n = 32)

| field | accuracy |
|---|---|
| action | 93.8% [79.9%-98.3%] |
| controlledProperty | 93.8% [79.9%-98.3%] |
| scope | 93.8% [79.9%-98.3%] |
| persistence | 93.8% [79.9%-98.3%] |
| targetZoneId | 93.8% [79.9%-98.3%] |
| value | 93.8% [79.9%-98.3%] |
| all fields | 93.8% [79.9%-98.3%] |

## Result kinds (rows gold, columns predicted)

|  | pred intent | pred clarification | pred unsupported |
|---|---|---|---|
| gold intent | 30 | 0 | 2 |
| gold clarification | 1 | 7 | 0 |
| gold unsupported | 0 | 0 | 14 |
| clarification precision / recall | 100.0% [64.6%-100.0%] | 87.5% [52.9%-97.8%] |  |

## Reasons

| gold kind | n | kind correct | reason correct (given kind) |
|---|---|---|---|
| clarification | 8 | 87.5% [52.9%-97.8%] | 100.0% [64.6%-100.0%] |
| unsupported | 14 | 100.0% [78.5%-100.0%] | 85.7% [60.1%-96.0%] |

## Strict errors by type (n = 4)

| type | errors | share |
|---|---|---|
| non-intent predicted, intent expected | 2 | 50% |
| intent predicted, non-intent expected | 1 | 25% |
| non-intent: wrong kind or reason | 1 | 25% |

## Per category

| category | n | strict | outcome |
|---|---|---|---|
| adversarial | 5 | 80.0% [37.6%-96.4%] | 100.0% [56.6%-100.0%] |
| ambiguous | 5 | 80.0% [37.6%-96.4%] | 80.0% [37.6%-96.4%] |
| environment | 5 | 100.0% [56.6%-100.0%] | 100.0% [56.6%-100.0%] |
| explicit | 5 | 80.0% [37.6%-96.4%] | 80.0% [37.6%-96.4%] |
| explicit_other_zone | 6 | 100.0% [61.0%-100.0%] | 100.0% [61.0%-100.0%] |
| following | 5 | 80.0% [37.6%-96.4%] | 80.0% [37.6%-96.4%] |
| implicit | 5 | 100.0% [56.6%-100.0%] | 100.0% [56.6%-100.0%] |
| out_of_scope | 6 | 100.0% [61.0%-100.0%] | 100.0% [61.0%-100.0%] |
| unsupported | 6 | 100.0% [61.0%-100.0%] | 100.0% [61.0%-100.0%] |
| zone_dependent | 6 | 100.0% [61.0%-100.0%] | 100.0% [61.0%-100.0%] |

## Per language

| language | n | strict | outcome |
|---|---|---|---|
| en | 48 | 91.7% [80.4%-96.7%] | 93.8% [83.2%-97.9%] |
| it | 6 | 100.0% [61.0%-100.0%] | 100.0% [61.0%-100.0%] |

## Per source

| source | n | strict | outcome |
|---|---|---|---|
| llm | 54 | 92.6% [82.4%-97.1%] | 94.4% [84.9%-98.1%] |
