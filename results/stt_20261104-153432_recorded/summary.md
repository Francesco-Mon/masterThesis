# STT stt_20261104-153432_recorded

Systran/faster-whisper-small@536b0662742c02347bc0e980a01041f333bce120, compute_type=int8, arm64 macOS 15.6.1, load 1.4 s (excluded)

WER = word-level edit distance / reference words (corpus level, after lowercasing and dropping punctuation). auto = language detected by the model; forced = reference language passed to transcribe(). Latency = wall time of transcribe(), model loading and one warm-up clip excluded; RTF = latency / audio duration.

**The audio is the author's own voice (one speaker, laptop microphone, quiet room, sentences read from the screen): one speaker is not a population.**

## Per language

| group | clips | WER | exact clips | language detected | audio ms (mean) | p50 ms | p95 ms | RTF p50 | RTF p95 |
|---|---|---|---|---|---|---|---|---|---|
| auto en | 10 | 128.1% | 4/10 | 6/10 | 2885 | 2490 | 10140 | 0.88 | 4.51 |
| auto it | 10 | 21.4% | 4/10 | 9/10 | 2585 | 2599 | 2955 | 1.07 | 1.22 |
| auto all | 20 | 75.2% | 8/20 | 15/20 | 2735 | 2578 | 9511 | 0.99 | 3.35 |
| forced en | 10 | 3.5% | 8/10 | 10/10 | 2885 | 1360 | 1408 | 0.47 | 0.62 |
| forced it | 10 | 16.1% | 4/10 | 10/10 | 2585 | 1513 | 1728 | 0.61 | 0.74 |
| forced all | 20 | 9.7% | 12/20 | 20/20 | 2735 | 1403 | 1596 | 0.55 | 0.66 |

## Clips

| id | mode | voice | reference | transcript | errors | ms |
|---|---|---|---|---|---|---|
| rec-01 | auto | author | Lobby lamp off, please | నికికికికికికికికికికికికికికికికికికికికికికికికికికికికికికికికికికికికికికికికికికికికికికికికికికికికికికిక | 56/4 | 10140 |
| rec-02 | auto | author | Open up the meeting room blinds | Open up the meeting room blinds. | 0/6 | 2581 |
| rec-03 | auto | author | Put the thermostat on 21 | Poživajte termostat na 21. | 4/5 | 2533 |
| rec-04 | auto | author | Brighten the hallway lamp to 80 percent | Brightened the hallway lamp to 80%. | 1/7 | 2445 |
| rec-05 | auto | author | This room is way too warm | Tukaj je bilo dobro. | 6/6 | 2495 |
| rec-06 | auto | author | Not enough light for reading here | not enough light for reading here | 0/6 | 2388 |
| rec-07 | auto | author | Keep the lights on while I walk | Keep the lights on while I work. | 1/7 | 2430 |
| rec-08 | auto | author | Pull the shutters down halfway | Poĺĺĺĺĺĺĺĺĺĺĺĺĺĺĺĺĺĺĺĺĺĺĺĺĺĺĺĺĺĺĺĺĺĺĺĺĺĺĺĺĺĺĺĺĺĺĺĺĺĺĺĺĺĺĺĺĺĺĺĺĺĺĺĺĺĺĺĺĺĺĺĺĺĺĺĺĺĺĺĺĺĺĺĺĺĺĺĺĺĺĺĺĺĺĺĺĺĺĺĺĺĺĺĺĺĺĺĺĺĺĺ | 5/5 | 9511 |
| rec-09 | auto | author | The sunlight is blinding me | The sunlight is blinding me. | 0/5 | 2490 |
| rec-10 | auto | author | Make the corridor a little cooler | Make the corridor a little cooler | 0/6 | 2430 |
| rec-11 | auto | author | Spegni la lampada dell'ingresso | Spegni la lampada dell'ingresso. | 0/5 | 2528 |
| rec-12 | auto | author | Alza le tapparelle della sala riunioni | alza le tapparelle della sala di unioni | 2/6 | 2578 |
| rec-13 | auto | author | Metti il riscaldamento su 22 | Metti il riscaldamento su 22°C. | 1/5 | 2554 |
| rec-14 | auto | author | Luce del corridoio al 60 per cento | Luce del corridoio al 60%. | 0/7 | 2585 |
| rec-15 | auto | author | Si soffoca qui dentro | si soffoga qui dentro | 1/4 | 2599 |
| rec-16 | auto | author | Mi serve più luce per leggere | Mi serve più luce per leggere. | 0/6 | 2955 |
| rec-17 | auto | author | Tieni accese le luci mentre cammino | Tieni accesso alle luci mentre cammino. | 2/6 | 2950 |
| rec-18 | auto | author | Chiudi un po' le persiane | chiudi un po' le versione | 1/5 | 2781 |
| rec-19 | auto | author | Il sole mi dà fastidio agli occhi | Il sole mi dà fastidio agli occhi. | 0/7 | 2723 |
| rec-20 | auto | author | Rinfresca un po' l'ufficio | Reinfresca um pouco o fijo. | 5/5 | 2796 |
| rec-01 | forced | author | Lobby lamp off, please | Lobby lamp off please | 0/4 | 1402 |
| rec-02 | forced | author | Open up the meeting room blinds | Open up the meeting room blinds. | 0/6 | 1408 |
| rec-03 | forced | author | Put the thermostat on 21 | Put the thermostat on 21. | 0/5 | 1383 |
| rec-04 | forced | author | Brighten the hallway lamp to 80 percent | Brightened the hallway lamp to 80%. | 1/7 | 1379 |
| rec-05 | forced | author | This room is way too warm | This room is way too warm. | 0/6 | 1360 |
| rec-06 | forced | author | Not enough light for reading here | not enough light for reading here | 0/6 | 1318 |
| rec-07 | forced | author | Keep the lights on while I walk | Keep the lights on while I work. | 1/7 | 1366 |
| rec-08 | forced | author | Pull the shutters down halfway | Pull the shutters down halfway. | 0/5 | 1344 |
| rec-09 | forced | author | The sunlight is blinding me | The sunlight is blinding me. | 0/5 | 1345 |
| rec-10 | forced | author | Make the corridor a little cooler | Make the corridor a little cooler | 0/6 | 1332 |
| rec-11 | forced | author | Spegni la lampada dell'ingresso | Spegni la lampada dell'ingresso. | 0/5 | 1728 |
| rec-12 | forced | author | Alza le tapparelle della sala riunioni | alza le tapparelle della sala di unioni | 2/6 | 1596 |
| rec-13 | forced | author | Metti il riscaldamento su 22 | Metti il riscaldamento su 22°C. | 1/5 | 1588 |
| rec-14 | forced | author | Luce del corridoio al 60 per cento | Luce del corridoio al 60%. | 0/7 | 1522 |
| rec-15 | forced | author | Si soffoca qui dentro | si soffoga qui dentro | 1/4 | 1403 |
| rec-16 | forced | author | Mi serve più luce per leggere | Mi serve più luce per leggere. | 0/6 | 1484 |
| rec-17 | forced | author | Tieni accese le luci mentre cammino | Tieni accesso alle luci mentre cammino. | 2/6 | 1513 |
| rec-18 | forced | author | Chiudi un po' le persiane | chiudi un po' le versione | 1/5 | 1502 |
| rec-19 | forced | author | Il sole mi dà fastidio agli occhi | Il sole mi dà fastidio agli occhi. | 0/7 | 1547 |
| rec-20 | forced | author | Rinfresca un po' l'ufficio | rinfresca un po' lo fiscio | 2/5 | 1499 |
