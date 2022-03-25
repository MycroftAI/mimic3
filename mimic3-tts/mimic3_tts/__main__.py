#!/usr/bin/env python3
import logging
import wave

from opentts_abc.ssml import SSMLSpeaker

from .tts import AudioResult, MarkResult, Mimic3Settings, Mimic3TextToSpeechSystem

logging.basicConfig(level=logging.DEBUG)

settings = Mimic3Settings()
tts = Mimic3TextToSpeechSystem(settings)

speaker = SSMLSpeaker(tts)
# ssml = '<speak><voice name="el_GR/rapunzelina_low"><s><w>Το</w><w>αερόστρωμνό</w><w>μου</w><w>είναι</w><w>γεμάτο</w><w>χέλια.</w></s></voice></speak>'
# ssml = '<speak><voice name="uk_UK/m-ailabs_low"><s><w>бажав</w></s></voice></speak>'
# ssml = '<speak><s><w>Hello</w><w>World</w></s></speak>'
# ssml = '<speak><s>Hello world</s></speak>'
# ssml = '<speak><s><voice name="el_GR/rapunzelina_low"><say-as interpret-as="characters">12</say-as></voice></s></speak>'
ssml = """
<speak>
<voice name="en_US/amy_low">
  Today is a test.
  This is another test.
</voice>


<voice name="es_ES/carlfm_low">
  <lang xml:lang="es_ES">
    Soy el <say-as interpret-as="number" format="ordinal">1</say-as>.
  </lang>
</voice>
</speak>
"""


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
