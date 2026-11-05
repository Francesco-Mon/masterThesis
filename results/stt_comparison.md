# STT comparison

WER = word-level edit distance / reference words (corpus level, after lowercasing and dropping punctuation). auto = language detected by the model; forced = reference language passed to transcribe(). Latency = wall time of transcribe(), model loading and one warm-up clip excluded; RTF = latency / audio duration.

**The audio is synthetic (macOS `say`): clean, no noise, no accent, so these figures are optimistic.**

**The audio is the author's own voice (one speaker, laptop microphone, quiet room, sentences read from the screen): one speaker is not a population.**

| condition | clips | WER EN | WER IT | language detected | p50 ms | p95 ms | RTF p50 | RTF p95 | run |
|---|---|---|---|---|---|---|---|---|---|
| synthetic auto | 20 | 3.8% | 40.0% | 18/20 | 2607 | 2714 | 1.26 | 2.84 | stt_20261104-143118_synthetic |
| synthetic forced | 20 | 3.8% | 32.7% | 20/20 | 1424 | 1630 | 0.70 | 1.47 | stt_20261104-143118_synthetic |
| recorded auto | 20 | 128.1% | 21.4% | 15/20 | 2578 | 9511 | 0.99 | 3.35 | stt_20261104-153432_recorded |
| recorded forced | 20 | 3.5% | 16.1% | 20/20 | 1403 | 1596 | 0.55 | 0.66 | stt_20261104-153432_recorded |
