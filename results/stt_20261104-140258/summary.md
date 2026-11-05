# STT stt_20261104-140258

Systran/faster-whisper-small@536b0662742c02347bc0e980a01041f333bce120, compute_type=int8, arm64 macOS 15.6.1, load 1.3 s (excluded)

WER = word-level edit distance / reference words (corpus level, after lowercasing and dropping punctuation). auto = language detected by the model; forced = reference language passed to transcribe(). Latency = wall time of transcribe(), model loading and one warm-up clip excluded; RTF = latency / audio duration.

**The audio is synthetic (macOS `say`): clean, no noise, no accent, so these figures are optimistic.**

## Per language

| group | clips | WER | exact clips | language detected | audio ms (mean) | p50 ms | p95 ms | RTF p50 | RTF p95 |
|---|---|---|---|---|---|---|---|---|---|
| auto en | 10 | 3.8% | 9/10 | 10/10 | 1902 | 2796 | 4817 | 1.54 | 3.02 |
| auto it | 10 | 40.0% | 4/10 | 8/10 | 2243 | 2979 | 3633 | 1.30 | 2.27 |
| auto all | 20 | 22.2% | 13/20 | 18/20 | 2073 | 2830 | 3633 | 1.38 | 2.93 |

## Per voice

| group | clips | WER | exact clips | language detected | audio ms (mean) | p50 ms | p95 ms | RTF p50 | RTF p95 |
|---|---|---|---|---|---|---|---|---|---|
| auto it Alice | 2 | 0.0% | 2/2 | 2/2 | 1855 | 3197 | 3633 | 1.52 | 2.25 |
| auto it other voices | 8 | 51.2% | 2/8 | 6/8 | 2340 | 2882 | 3100 | 1.27 | 2.27 |
| auto en Daniel | 2 | 0.0% | 2/2 | 2/2 | 1285 | 2515 | 2867 | 2.06 | 2.12 |
| auto en Eddy (Inglese (USA)) | 2 | 0.0% | 2/2 | 2/2 | 2775 | 2620 | 2820 | 0.92 | 1.06 |
| auto en Flo (Inglese (UK)) | 2 | 0.0% | 2/2 | 2/2 | 1969 | 2579 | 2830 | 1.23 | 1.54 |
| auto en Reed (Inglese (USA)) | 2 | 18.2% | 1/2 | 2/2 | 2579 | 2998 | 4817 | 0.92 | 2.54 |
| auto en Samantha | 2 | 0.0% | 2/2 | 2/2 | 904 | 2584 | 2796 | 2.93 | 3.02 |
| auto it Eddy (Italiano (Italia)) | 2 | 62.5% | 1/2 | 2/2 | 1839 | 2979 | 3012 | 1.27 | 2.27 |
| auto it Flo (Italiano (Italia)) | 2 | 100.0% | 0/2 | 0/2 | 2486 | 2882 | 3038 | 1.02 | 1.41 |
| auto it Reed (Italiano (Italia)) | 2 | 9.1% | 1/2 | 2/2 | 2532 | 2621 | 2828 | 0.90 | 1.38 |
| auto it Sandy (Italiano (Italia)) | 2 | 33.3% | 0/2 | 2/2 | 2502 | 2786 | 3100 | 1.08 | 1.30 |

## Clips

| id | mode | voice | reference | transcript | errors | ms |
|---|---|---|---|---|---|---|
| stt-01 | auto | Samantha | Turn on the light | Turn on the light. | 0/4 | 2584 |
| stt-02 | auto | Daniel | Close the blinds | Close the blinds. | 0/3 | 2515 |
| stt-03 | auto | Eddy (Inglese (USA)) | Set the lights to 70 percent brightness | set the lights to 70% brightness. | 0/7 | 2820 |
| stt-04 | auto | Flo (Inglese (UK)) | Turn on the kitchen light | Turn on the kitchen light. | 0/5 | 2830 |
| stt-05 | auto | Reed (Inglese (USA)) | Dim the office lamp to 25 percent | DIME office lamp to 25% | 2/7 | 2998 |
| stt-06 | auto | Samantha | It's getting chilly | It's getting chilly. | 0/4 | 2796 |
| stt-07 | auto | Daniel | It's a bit dim in here | It's a bit dim in here. | 0/7 | 2867 |
| stt-08 | auto | Eddy (Inglese (USA)) | Light my way to the office, please | light my way to the office please | 0/7 | 2620 |
| stt-09 | auto | Flo (Inglese (UK)) | Turn the heating up everywhere | Turn the heating up everywhere. | 0/5 | 2579 |
| stt-10 | auto | Reed (Inglese (USA)) | Turn on the ventilation | turn on the ventilation. | 0/4 | 4817 |
| stt-11 | auto | Alice | Accendi la luce della cucina | Accendi la luce della cucina | 0/5 | 3633 |
| stt-12 | auto | Eddy (Italiano (Italia)) | Fai più caldo | fai più caldo | 0/3 | 3012 |
| stt-13 | auto | Flo (Italiano (Italia)) | Alza il riscaldamento ovunque | ¡Alzá en mi escandamento! | 4/4 | 3038 |
| stt-14 | auto | Reed (Italiano (Italia)) | Accendi la ventilazione | accendi la ventilazione | 0/3 | 2621 |
| stt-15 | auto | Sandy (Italiano (Italia)) | Accendi le luci del giardino | Facceli le luci del giardino! | 1/5 | 2786 |
| stt-16 | auto | Alice | Metti la lampada dell'atrio al minimo | Metti la lampada dell'atrio al minimo. | 0/7 | 3197 |
| stt-17 | auto | Eddy (Italiano (Italia)) | Abbassa le tapparelle dell'ufficio | abbassarne tapparenne del nufficio | 5/5 | 2979 |
| stt-18 | auto | Flo (Italiano (Italia)) | Non riesco a leggere, c'è poca luce | No nie jest koalegiory, się pokalusi. | 8/8 | 2882 |
| stt-19 | auto | Reed (Italiano (Italia)) | Porta il termostato della cucina a 21 gradi | e porta il termostato della cucina a 21 gradi. | 1/8 | 2828 |
| stt-20 | auto | Sandy (Italiano (Italia)) | Illuminami la strada fino alla sala riunioni | Umina milla strada fino alla scena riunioni. | 3/7 | 3100 |
