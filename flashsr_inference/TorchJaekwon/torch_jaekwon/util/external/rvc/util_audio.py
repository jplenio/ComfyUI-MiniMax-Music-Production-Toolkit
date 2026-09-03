import numpy as np

class UtilAudio:
    @staticmethod
    def norm_audio(audio: np.ndarray, #[time]
                   max: float = 0.9,
                   alpha: float = 0.75,
                   ) -> np.ndarray:
        tmp_max = np.abs(audio).max()
        assert tmp_max <= 2.5, "The maximum value of the audio is too high."
        
        audio = (audio / tmp_max * (max * alpha)) + (
            1 - alpha
        ) * audio
        return audio.astype(np.float32)