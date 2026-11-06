import numpy as np

from local_voice import SentenceSplitter, resample


def test_splitter_emits_sentences_as_they_complete():
    s = SentenceSplitter()
    assert s.feed("The sky is blue") == []
    assert s.feed(" because of Rayleigh scattering. Shorter wave") == ["The sky is blue because of Rayleigh scattering."]
    assert s.feed("lengths scatter more!\nThat is all.") == ["Shorter wavelengths scatter more!"]
    assert s.flush() == "That is all."
    assert s.flush() is None


def test_splitter_keeps_short_fragments_attached():
    s = SentenceSplitter()
    assert s.feed("Dr. Smith arrived late. Fine.") == ["Dr. Smith arrived late."]
    assert s.flush() == "Fine."


def test_resample_changes_length():
    audio = np.zeros(24000, dtype=np.float32)
    assert len(resample(audio, 24000, 16000)) == 16000


def test_stt_backend_follows_platform(monkeypatch):
    import local_voice

    monkeypatch.setattr(local_voice.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(local_voice.platform, "machine", lambda: "arm64")
    assert local_voice.LocalSpeech(None, "af_heart").stt_model == "mlx-community/whisper-large-v3-turbo"
    monkeypatch.setattr(local_voice.platform, "system", lambda: "Linux")
    speech = local_voice.LocalSpeech(None, "af_heart")
    assert speech.backend == "faster-whisper" and speech.stt_model == "large-v3-turbo"
    assert local_voice.LocalSpeech("small", "af_heart").stt_model == "small"


def test_faster_whisper_transcribe_joins_segments_and_drops_no_speech():
    import local_voice

    class Seg:
        def __init__(self, text, p):
            self.text, self.no_speech_prob = text, p

    class FakeModel:
        def transcribe(self, audio, language, beam_size):
            return [Seg(" Hello ", 0.1), Seg("noise", 0.9), Seg("there.", 0.2)], None

    s = local_voice.LocalSpeech("small", "af_heart")
    s.backend = "faster-whisper"
    s._whisper = FakeModel()
    assert s.transcribe(np.zeros(16000, dtype=np.float32)) == "Hello there."
