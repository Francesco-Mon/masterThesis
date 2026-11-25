# 20261125-141858_llm_openai-gpt-oss-120b_test_deepinfra

grounder=llm, model=openai/gpt-oss-120b, provider=DeepInfra, split=test, repeats=3, temperature=0.0

## CLASSic overview

| group | metric | value |
|---|---|---|
| Accuracy | predictions | 180 |
| Accuracy | kind accuracy | 97.8% [94.4%-99.1%] |
| Accuracy | strict accuracy | 90.6% [85.4%-94.0%] |
| Accuracy | outcome accuracy | 98.9% [96.0%-99.7%] |
| Accuracy | intent: all fields (gold intents) | 91.9% [84.9%-95.8%] |
| Security | injection cases handled (outcome correct) | 100.0% [82.4%-100.0%] |
| Security | injection-only cases with a command | 0 / 9 |
| Security | mixed cases with commands beyond the legitimate part | 0 / 9 |
| Security | raw grounder output off catalogue (all cases) | 0.0% [0.0%-2.1%] |
| Security | final commands off catalogue (must be 0) | 0 |
| Cost | total USD | 0.019900 |
| Cost | USD per 1000 requests | 0.1106 |
| Cost | prompt / completion tokens | 308823 / 70185 |
| Cost | tokens per request (prompt / completion) | 1716 / 390 |
| Cost | LLM calls (incl. retries) | 174 |
| Cost | requests needing a retry | 0 |
| Latency | requests measured (not cached) | 174 |
| Latency | mean s | 21.03 |
| Latency | p50 s | 18.63 |
| Latency | p95 s | 40.45 |
| Latency | p50 ms | 18630.60 |
| Latency | p95 ms | 40450.40 |
| Stability | repeat agreement (all repeats identical) | 91.7% [81.9%-96.4%] |
| Stability | EN-IT agreement (paraphrase pairs) | - |
| Stability | EN-IT pairs | 0 |
| Failures | invalid output after retries | 0 |
| Failures | service unavailable | 0 |

## Intent fields (gold intents, n = 99)

| field | accuracy |
|---|---|
| action | 94.9% [88.7%-97.8%] |
| controlledProperty | 96.0% [90.1%-98.4%] |
| scope | 96.0% [90.1%-98.4%] |
| persistence | 92.9% [86.1%-96.5%] |
| targetZoneId | 96.0% [90.1%-98.4%] |
| value | 96.0% [90.1%-98.4%] |
| all fields | 91.9% [84.9%-95.8%] |

## Result kinds (rows gold, columns predicted)

|  | pred intent | pred clarification | pred unsupported |
|---|---|---|---|
| gold intent | 95 | 3 | 1 |
| gold clarification | 0 | 30 | 0 |
| gold unsupported | 0 | 0 | 51 |
| clarification precision / recall | 90.9% [76.4%-96.9%] | 100.0% [88.6%-100.0%] |  |

## Reasons

| gold kind | n | kind correct | reason correct (given kind) |
|---|---|---|---|
| clarification | 30 | 100.0% [88.6%-100.0%] | 100.0% [88.6%-100.0%] |
| unsupported | 51 | 100.0% [93.0%-100.0%] | 76.5% [63.2%-86.0%] |

## Strict errors by type (n = 17)

| type | errors | share |
|---|---|---|
| non-intent: wrong kind or reason | 12 | 71% |
| pair right, other field (scope, persistence, target, value) | 3 | 18% |
| non-intent predicted, intent expected | 1 | 6% |
| polarity (activate/deactivate, increase/decrease) | 1 | 6% |

## Per category

| category | n | strict | outcome |
|---|---|---|---|
| adversarial | 18 | 66.7% [43.7%-83.7%] | 100.0% [82.4%-100.0%] |
| ambiguous | 18 | 100.0% [82.4%-100.0%] | 100.0% [82.4%-100.0%] |
| environment | 18 | 100.0% [82.4%-100.0%] | 100.0% [82.4%-100.0%] |
| explicit | 18 | 94.4% [74.2%-99.0%] | 94.4% [74.2%-99.0%] |
| explicit_other_zone | 18 | 94.4% [74.2%-99.0%] | 94.4% [74.2%-99.0%] |
| following | 18 | 83.3% [60.8%-94.2%] | 100.0% [82.4%-100.0%] |
| implicit | 18 | 100.0% [82.4%-100.0%] | 100.0% [82.4%-100.0%] |
| out_of_scope | 18 | 100.0% [82.4%-100.0%] | 100.0% [82.4%-100.0%] |
| unsupported | 18 | 66.7% [43.7%-83.7%] | 100.0% [82.4%-100.0%] |
| zone_dependent | 18 | 100.0% [82.4%-100.0%] | 100.0% [82.4%-100.0%] |

## Per language

| language | n | strict | outcome |
|---|---|---|---|
| en | 120 | 88.3% [81.4%-92.9%] | 99.2% [95.4%-99.9%] |
| it | 60 | 95.0% [86.3%-98.3%] | 98.3% [91.1%-99.7%] |

## Per source

| source | n | strict | outcome |
|---|---|---|---|
| llm | 180 | 90.6% [85.4%-94.0%] | 98.9% [96.0%-99.7%] |
