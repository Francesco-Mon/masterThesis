import wave

import numpy as np

from cpsagent.ui.record_clips import RATE, save_wav


def test_saved_clip_is_16khz_mono_16bit(tmp_path):
    path = tmp_path / "x" / "rec-01.wav"
    save_wav(path, np.arange(RATE, dtype=np.int16))
    with wave.open(str(path)) as w:
        assert (w.getframerate(), w.getnchannels(), w.getsampwidth(), w.getnframes()) == (
            RATE, 1, 2, RATE,
        )  # fmt: skip
