# STT stt_20261104-143118_synthetic

Systran/faster-whisper-small@536b0662742c02347bc0e980a01041f333bce120, compute_type=int8, arm64 macOS 15.6.1, load 1.2 s (excluded)

WER = word-level edit distance / reference words (corpus level, after lowercasing and dropping punctuation). auto = language detected by the model; forced = reference language passed to transcribe(). Latency = wall time of transcribe(), model loading and one warm-up clip excluded; RTF = latency / audio duration.

**The audio is synthetic (macOS `say`): clean, no noise, no accent, so these figures are optimistic.**

## Per language

| group | clips | WER | exact clips | language detected | audio ms (mean) | p50 ms | p95 ms | RTF p50 | RTF p95 |
|---|---|---|---|---|---|---|---|---|---|
| auto en | 10 | 3.8% | 9/10 | 10/10 | 1902 | 2590 | 2636 | 1.30 | 2.97 |
| auto it | 10 | 40.0% | 4/10 | 8/10 | 2243 | 2660 | 2777 | 1.21 | 1.91 |
| auto all | 20 | 22.2% | 13/20 | 18/20 | 2073 | 2607 | 2714 | 1.26 | 2.84 |
| forced en | 10 | 3.8% | 9/10 | 10/10 | 1902 | 1382 | 1470 | 0.72 | 1.67 |
| forced it | 10 | 32.7% | 4/10 | 10/10 | 2243 | 1510 | 1738 | 0.66 | 1.03 |
| forced all | 20 | 18.5% | 13/20 | 20/20 | 2073 | 1424 | 1630 | 0.70 | 1.47 |

## Per voice

| group | clips | WER | exact clips | language detected | audio ms (mean) | p50 ms | p95 ms | RTF p50 | RTF p95 |
|---|---|---|---|---|---|---|---|---|---|
| auto it Alice | 2 | 0.0% | 2/2 | 2/2 | 1855 | 2567 | 2673 | 1.27 | 1.59 |
| auto it other voices | 8 | 51.2% | 2/8 | 6/8 | 2340 | 2660 | 2777 | 1.13 | 1.91 |
| auto en Daniel | 2 | 0.0% | 2/2 | 2/2 | 1285 | 2607 | 2636 | 1.95 | 2.14 |
| auto en Eddy (Inglese (USA)) | 2 | 0.0% | 2/2 | 2/2 | 2775 | 2562 | 2630 | 0.83 | 1.06 |
| auto en Flo (Inglese (UK)) | 2 | 0.0% | 2/2 | 2/2 | 1969 | 2459 | 2501 | 1.17 | 1.36 |
| auto en Reed (Inglese (USA)) | 2 | 18.2% | 1/2 | 2/2 | 2579 | 2468 | 2590 | 0.79 | 1.30 |
| auto en Samantha | 2 | 0.0% | 2/2 | 2/2 | 904 | 2620 | 2627 | 2.84 | 2.97 |
| auto it Eddy (Italiano (Italia)) | 2 | 62.5% | 1/2 | 2/2 | 1839 | 2531 | 2665 | 1.13 | 1.91 |
| auto it Flo (Italiano (Italia)) | 2 | 100.0% | 0/2 | 0/2 | 2486 | 2684 | 2714 | 0.95 | 1.26 |
| auto it Reed (Italiano (Italia)) | 2 | 9.1% | 1/2 | 2/2 | 2532 | 2595 | 2660 | 0.84 | 1.36 |
| auto it Sandy (Italiano (Italia)) | 2 | 33.3% | 0/2 | 2/2 | 2502 | 2590 | 2777 | 0.97 | 1.21 |
| forced it Alice | 2 | 0.0% | 2/2 | 2/2 | 1855 | 1446 | 1738 | 0.83 | 0.90 |
| forced it other voices | 8 | 41.9% | 2/8 | 8/8 | 2340 | 1510 | 1630 | 0.66 | 1.03 |
| forced en Daniel | 2 | 0.0% | 2/2 | 2/2 | 1285 | 1364 | 1431 | 1.06 | 1.12 |
| forced en Eddy (Inglese (USA)) | 2 | 0.0% | 2/2 | 2/2 | 2775 | 1424 | 1458 | 0.46 | 0.59 |
| forced en Flo (Inglese (UK)) | 2 | 0.0% | 2/2 | 2/2 | 1969 | 1374 | 1382 | 0.66 | 0.75 |
| forced en Reed (Inglese (USA)) | 2 | 18.2% | 1/2 | 2/2 | 2579 | 1370 | 1414 | 0.43 | 0.72 |
| forced en Samantha | 2 | 0.0% | 2/2 | 2/2 | 904 | 1360 | 1470 | 1.47 | 1.67 |
| forced it Eddy (Italiano (Italia)) | 2 | 62.5% | 1/2 | 2/2 | 1839 | 1365 | 1556 | 0.66 | 1.03 |
| forced it Flo (Italiano (Italia)) | 2 | 66.7% | 0/2 | 2/2 | 2486 | 1417 | 1561 | 0.56 | 0.66 |
| forced it Reed (Italiano (Italia)) | 2 | 9.1% | 1/2 | 2/2 | 2532 | 1346 | 1595 | 0.51 | 0.71 |
| forced it Sandy (Italiano (Italia)) | 2 | 33.3% | 0/2 | 2/2 | 2502 | 1510 | 1630 | 0.57 | 0.70 |

## Clips

| id | mode | voice | reference | transcript | errors | ms |
|---|---|---|---|---|---|---|
| stt-01 | auto | Samantha | Turn on the light | Turn on the light. | 0/4 | 2620 |
| stt-02 | auto | Daniel | Close the blinds | Close the blinds. | 0/3 | 2607 |
| stt-03 | auto | Eddy (Inglese (USA)) | Set the lights to 70 percent brightness | set the lights to 70% brightness. | 0/7 | 2562 |
| stt-04 | auto | Flo (Inglese (UK)) | Turn on the kitchen light | Turn on the kitchen light. | 0/5 | 2501 |
| stt-05 | auto | Reed (Inglese (USA)) | Dim the office lamp to 25 percent | DIME office lamp to 25% | 2/7 | 2590 |
| stt-06 | auto | Samantha | It's getting chilly | It's getting chilly. | 0/4 | 2627 |
| stt-07 | auto | Daniel | It's a bit dim in here | It's a bit dim in here. | 0/7 | 2636 |
| stt-08 | auto | Eddy (Inglese (USA)) | Light my way to the office, please | light my way to the office please | 0/7 | 2630 |
| stt-09 | auto | Flo (Inglese (UK)) | Turn the heating up everywhere | Turn the heating up everywhere. | 0/5 | 2459 |
| stt-10 | auto | Reed (Inglese (USA)) | Turn on the ventilation | turn on the ventilation. | 0/4 | 2468 |
| stt-11 | auto | Alice | Accendi la luce della cucina | Accendi la luce della cucina | 0/5 | 2567 |
| stt-12 | auto | Eddy (Italiano (Italia)) | Fai più caldo | fai più caldo | 0/3 | 2531 |
| stt-13 | auto | Flo (Italiano (Italia)) | Alza il riscaldamento ovunque | ¡Alzá en mi escandamento! | 4/4 | 2714 |
| stt-14 | auto | Reed (Italiano (Italia)) | Accendi la ventilazione | accendi la ventilazione | 0/3 | 2595 |
| stt-15 | auto | Sandy (Italiano (Italia)) | Accendi le luci del giardino | Facceli le luci del giardino! | 1/5 | 2590 |
| stt-16 | auto | Alice | Metti la lampada dell'atrio al minimo | Metti la lampada dell'atrio al minimo. | 0/7 | 2673 |
| stt-17 | auto | Eddy (Italiano (Italia)) | Abbassa le tapparelle dell'ufficio | abbassarne tapparenne del nufficio | 5/5 | 2665 |
| stt-18 | auto | Flo (Italiano (Italia)) | Non riesco a leggere, c'è poca luce | No nie jest koalegiory, się pokalusi. | 8/8 | 2684 |
| stt-19 | auto | Reed (Italiano (Italia)) | Porta il termostato della cucina a 21 gradi | e porta il termostato della cucina a 21 gradi. | 1/8 | 2660 |
| stt-20 | auto | Sandy (Italiano (Italia)) | Illuminami la strada fino alla sala riunioni | Umina milla strada fino alla scena riunioni. | 3/7 | 2777 |
| stt-01 | forced | Samantha | Turn on the light | Turn on the light. | 0/4 | 1470 |
| stt-02 | forced | Daniel | Close the blinds | Close the blinds. | 0/3 | 1364 |
| stt-03 | forced | Eddy (Inglese (USA)) | Set the lights to 70 percent brightness | set the lights to 70% brightness. | 0/7 | 1424 |
| stt-04 | forced | Flo (Inglese (UK)) | Turn on the kitchen light | Turn on the kitchen light. | 0/5 | 1374 |
| stt-05 | forced | Reed (Inglese (USA)) | Dim the office lamp to 25 percent | DIME office lamp to 25% | 2/7 | 1414 |
| stt-06 | forced | Samantha | It's getting chilly | It's getting chilly. | 0/4 | 1360 |
| stt-07 | forced | Daniel | It's a bit dim in here | It's a bit dim in here. | 0/7 | 1431 |
| stt-08 | forced | Eddy (Inglese (USA)) | Light my way to the office, please | light my way to the office please | 0/7 | 1458 |
| stt-09 | forced | Flo (Inglese (UK)) | Turn the heating up everywhere | Turn the heating up everywhere. | 0/5 | 1382 |
| stt-10 | forced | Reed (Inglese (USA)) | Turn on the ventilation | turn on the ventilation. | 0/4 | 1370 |
| stt-11 | forced | Alice | Accendi la luce della cucina | Accendi la luce della cucina | 0/5 | 1446 |
| stt-12 | forced | Eddy (Italiano (Italia)) | Fai più caldo | fai più caldo | 0/3 | 1365 |
| stt-13 | forced | Flo (Italiano (Italia)) | Alza il riscaldamento ovunque | e mi scandamento vuoi | 4/4 | 1417 |
| stt-14 | forced | Reed (Italiano (Italia)) | Accendi la ventilazione | accendi la ventilazione | 0/3 | 1346 |
| stt-15 | forced | Sandy (Italiano (Italia)) | Accendi le luci del giardino | Facceli le luci del giardino! | 1/5 | 1510 |
| stt-16 | forced | Alice | Metti la lampada dell'atrio al minimo | Metti la lampada dell'atrio al minimo. | 0/7 | 1738 |
| stt-17 | forced | Eddy (Italiano (Italia)) | Abbassa le tapparelle dell'ufficio | abbassarne tapparenne del nufficio | 5/5 | 1556 |
| stt-18 | forced | Flo (Italiano (Italia)) | Non riesco a leggere, c'è poca luce | Non riesco a leggere si poco a luci. | 4/8 | 1561 |
| stt-19 | forced | Reed (Italiano (Italia)) | Porta il termostato della cucina a 21 gradi | e porta il termostato della cucina a 21 gradi. | 1/8 | 1595 |
| stt-20 | forced | Sandy (Italiano (Italia)) | Illuminami la strada fino alla sala riunioni | Umina milla strada fino alla scena riunioni. | 3/7 | 1630 |
