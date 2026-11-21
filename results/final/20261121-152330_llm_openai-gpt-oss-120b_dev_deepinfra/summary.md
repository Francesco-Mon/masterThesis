# 20261121-152330_llm_openai-gpt-oss-120b_dev_deepinfra

grounder=llm, model=openai/gpt-oss-120b, provider=DeepInfra, split=dev, repeats=1, temperature=0.0

## CLASSic overview

| group | metric | value |
|---|---|---|
| Accuracy | predictions | 54 |
| Accuracy | kind accuracy | 94.4% [84.9%-98.1%] |
| Accuracy | strict accuracy | 88.9% [77.8%-94.8%] |
| Accuracy | outcome accuracy | 94.4% [84.9%-98.1%] |
| Accuracy | intent: all fields (gold intents) | 87.5% [71.9%-95.0%] |
| Security | injection cases handled (outcome correct) | 100.0% [56.6%-100.0%] |
| Security | injection-only cases with a command | 0 / 1 |
| Security | mixed cases with commands beyond the legitimate part | 0 / 4 |
| Security | raw grounder output off catalogue (all cases) | 0.0% [0.0%-6.6%] |
| Security | final commands off catalogue (must be 0) | 0 |
| Cost | total USD | 0.005971 |
| Cost | USD per 1000 requests | 0.1106 |
| Cost | prompt / completion tokens | 93847 / 20836 |
| Cost | tokens per request (prompt / completion) | 1738 / 386 |
| Cost | LLM calls (incl. retries) | 53 |
| Cost | requests needing a retry | 0 |
| Latency | requests measured (not cached) | 53 |
| Latency | mean s | 23.54 |
| Latency | p50 s | 21.14 |
| Latency | p95 s | 42.09 |
| Latency | p50 ms | 21142.80 |
| Latency | p95 ms | 42086.90 |
| Stability | repeat agreement (all repeats identical) | - |
| Stability | EN-IT agreement (paraphrase pairs) | 100.0% [61.0%-100.0%] |
| Stability | EN-IT pairs | 6 |
| Failures | invalid output after retries | 0 |
| Failures | service unavailable | 0 |

## Intent fields (gold intents, n = 32)

| field | accuracy |
|---|---|
| action | 90.6% [75.8%-96.8%] |
| controlledProperty | 90.6% [75.8%-96.8%] |
| scope | 90.6% [75.8%-96.8%] |
| persistence | 87.5% [71.9%-95.0%] |
| targetZoneId | 90.6% [75.8%-96.8%] |
| value | 90.6% [75.8%-96.8%] |
| all fields | 87.5% [71.9%-95.0%] |

## Result kinds (rows gold, columns predicted)

|  | pred intent | pred clarification | pred unsupported |
|---|---|---|---|
| gold intent | 29 | 1 | 2 |
| gold clarification | 0 | 8 | 0 |
| gold unsupported | 0 | 0 | 14 |
| clarification precision / recall | 88.9% [56.5%-98.0%] | 100.0% [67.6%-100.0%] |  |

## Reasons

| gold kind | n | kind correct | reason correct (given kind) |
|---|---|---|---|
| clarification | 8 | 100.0% [67.6%-100.0%] | 100.0% [67.6%-100.0%] |
| unsupported | 14 | 100.0% [78.5%-100.0%] | 78.6% [52.4%-92.4%] |

## Strict errors by type (n = 6)

| type | errors | share |
|---|---|---|
| non-intent predicted, intent expected | 3 | 50% |
| non-intent: wrong kind or reason | 2 | 33% |
| pair right, other field (scope, persistence, target, value) | 1 | 17% |

## Per category

| category | n | strict | outcome |
|---|---|---|---|
| adversarial | 5 | 80.0% [37.6%-96.4%] | 100.0% [56.6%-100.0%] |
| ambiguous | 5 | 100.0% [56.6%-100.0%] | 100.0% [56.6%-100.0%] |
| environment | 5 | 100.0% [56.6%-100.0%] | 100.0% [56.6%-100.0%] |
| explicit | 5 | 80.0% [37.6%-96.4%] | 80.0% [37.6%-96.4%] |
| explicit_other_zone | 6 | 100.0% [61.0%-100.0%] | 100.0% [61.0%-100.0%] |
| following | 5 | 60.0% [23.1%-88.2%] | 80.0% [37.6%-96.4%] |
| implicit | 5 | 80.0% [37.6%-96.4%] | 80.0% [37.6%-96.4%] |
| out_of_scope | 6 | 100.0% [61.0%-100.0%] | 100.0% [61.0%-100.0%] |
| unsupported | 6 | 83.3% [43.6%-97.0%] | 100.0% [61.0%-100.0%] |
| zone_dependent | 6 | 100.0% [61.0%-100.0%] | 100.0% [61.0%-100.0%] |

## Per language

| language | n | strict | outcome |
|---|---|---|---|
| en | 48 | 87.5% [75.3%-94.1%] | 93.8% [83.2%-97.9%] |
| it | 6 | 100.0% [61.0%-100.0%] | 100.0% [61.0%-100.0%] |

## Per source

| source | n | strict | outcome |
|---|---|---|---|
| llm | 54 | 88.9% [77.8%-94.8%] | 94.4% [84.9%-98.1%] |
