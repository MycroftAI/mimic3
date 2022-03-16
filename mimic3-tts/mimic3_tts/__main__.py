#!/usr/bin/env python3
import logging
import wave

logging.basicConfig(level=logging.DEBUG)

from opentts_abc.ssml import SSMLSpeaker
from mimic3_tts.tts import Mimic3TextToSpeechSystem, Mimic3Settings, AudioResult, MarkResult

settings = Mimic3Settings(length_scale=1.2, noise_w=0)
tts = Mimic3TextToSpeechSystem(settings)

speaker = SSMLSpeaker(tts)
ssml = '<speak><s><voice name="en_US/vctk_low#20">This is a test.</voice></s></speak>'

wav_file: wave.Wave_write = wave.open("out.wav", "wb")
params_set = False
with wav_file:
    for result in speaker.speak(ssml):
        if isinstance(result, AudioResult):
            if not params_set:
                wav_file.setframerate(result.sample_rate_hz)
                wav_file.setsampwidth(result.sample_width_bytes)
                wav_file.setnchannels(result.num_channels)
                params_set = True

            wav_file.writeframes(result.audio_bytes)
        elif isinstance(result, MarkResult):
            print("mark", result.name)
