# 20261125-142031_llm_nvidia-nemotron-3.5-super-vl-free_test

grounder=llm, model=nvidia/nemotron-3.5-super-vl:free, provider=None, split=test, repeats=3, temperature=0.0

## CLASSic overview

| group | metric | value |
|---|---|---|
| Accuracy | predictions | 180 |
| Accuracy | kind accuracy | 97.8% [94.4%-99.1%] |
| Accuracy | strict accuracy | 96.1% [92.2%-98.1%] |
| Accuracy | outcome accuracy | 97.8% [94.4%-99.1%] |
| Accuracy | intent: all fields (gold intents) | 100.0% [96.3%-100.0%] |
| Security | injection cases handled (outcome correct) | 100.0% [82.4%-100.0%] |
| Security | injection-only cases with a command | 0 / 9 |
| Security | mixed cases with commands beyond the legitimate part | 0 / 9 |
| Security | raw grounder output off catalogue (all cases) | 0.0% [0.0%-2.1%] |
| Security | final commands off catalogue (must be 0) | 0 |
| Cost | total USD | 0.000000 |
| Cost | USD per 1000 requests | 0.0000 |
| Cost | prompt / completion tokens | 312642 / 129279 |
| Cost | tokens per request (prompt / completion) | 1737 / 718 |
| Cost | LLM calls (incl. retries) | 174 |
| Cost | requests needing a retry | 0 |
| Latency | requests measured (not cached) | 174 |
| Latency | mean s | 9.40 |
| Latency | p50 s | 6.62 |
| Latency | p95 s | 21.91 |
| Latency | p50 ms | 6622.70 |
| Latency | p95 ms | 21913.00 |
| Stability | repeat agreement (all repeats identical) | 95.0% [86.3%-98.3%] |
| Stability | EN-IT agreement (paraphrase pairs) | - |
| Stability | EN-IT pairs | 0 |
| Failures | invalid output after retries | 0 |
| Failures | service unavailable | 0 |

## Intent fields (gold intents, n = 99)

| field | accuracy |
|---|---|
| action | 100.0% [96.3%-100.0%] |
| controlledProperty | 100.0% [96.3%-100.0%] |
| scope | 100.0% [96.3%-100.0%] |
| persistence | 100.0% [96.3%-100.0%] |
| targetZoneId | 100.0% [96.3%-100.0%] |
| value | 100.0% [96.3%-100.0%] |
| all fields | 100.0% [96.3%-100.0%] |

## Result kinds (rows gold, columns predicted)

|  | pred intent | pred clarification | pred unsupported |
|---|---|---|---|
| gold intent | 99 | 0 | 0 |
| gold clarification | 0 | 30 | 0 |
| gold unsupported | 3 | 1 | 47 |
| clarification precision / recall | 96.8% [83.8%-99.4%] | 100.0% [88.6%-100.0%] |  |

## Reasons

| gold kind | n | kind correct | reason correct (given kind) |
|---|---|---|---|
| clarification | 30 | 100.0% [88.6%-100.0%] | 100.0% [88.6%-100.0%] |
| unsupported | 51 | 92.2% [81.5%-96.9%] | 93.6% [82.8%-97.8%] |

## Strict errors by type (n = 7)

| type | errors | share |
|---|---|---|
| non-intent: wrong kind or reason | 4 | 57% |
| intent predicted, non-intent expected | 3 | 43% |

## Per category

| category | n | strict | outcome |
|---|---|---|---|
| adversarial | 18 | 94.4% [74.2%-99.0%] | 100.0% [82.4%-100.0%] |
| ambiguous | 18 | 100.0% [82.4%-100.0%] | 100.0% [82.4%-100.0%] |
| environment | 18 | 100.0% [82.4%-100.0%] | 100.0% [82.4%-100.0%] |
| explicit | 18 | 100.0% [82.4%-100.0%] | 100.0% [82.4%-100.0%] |
| explicit_other_zone | 18 | 100.0% [82.4%-100.0%] | 100.0% [82.4%-100.0%] |
| following | 18 | 100.0% [82.4%-100.0%] | 100.0% [82.4%-100.0%] |
| implicit | 18 | 100.0% [82.4%-100.0%] | 100.0% [82.4%-100.0%] |
| out_of_scope | 18 | 100.0% [82.4%-100.0%] | 100.0% [82.4%-100.0%] |
| unsupported | 18 | 72.2% [49.1%-87.5%] | 83.3% [60.8%-94.2%] |
| zone_dependent | 18 | 94.4% [74.2%-99.0%] | 94.4% [74.2%-99.0%] |

## Per language

| language | n | strict | outcome |
|---|---|---|---|
| en | 120 | 94.2% [88.4%-97.1%] | 96.7% [91.7%-98.7%] |
| it | 60 | 100.0% [94.0%-100.0%] | 100.0% [94.0%-100.0%] |

## Per source

| source | n | strict | outcome |
|---|---|---|---|
| llm | 180 | 96.1% [92.2%-98.1%] | 97.8% [94.4%-99.1%] |
