# Copyright 2022 Mycroft AI Inc.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
import argparse
import io
import logging
import threading
import typing
import wave
from queue import Queue

from mimic3_tts import (
    AudioResult,
    Mimic3Settings,
    Mimic3TextToSpeechSystem,
    SSMLSpeaker,
)

from .const import SynthesisRequest

_LOGGER = logging.getLogger(__name__)


def do_synthesis(item: SynthesisRequest, mimic3: Mimic3TextToSpeechSystem) -> bytes:
    """Synthesize text into audio.

    Returns: WAV bytes
    """
    params = item.params
    mimic3.speaker = None
    mimic3.voice = params.voice

    mimic3.settings.length_scale = params.length_scale
    mimic3.settings.noise_scale = params.noise_scale
    mimic3.settings.noise_w = params.noise_w

    with io.BytesIO() as wav_io:
        wav_file: wave.Wave_write = wave.open(wav_io, "wb")
        wav_params_set = False

        with wav_file:
            try:
                if params.ssml:
                    # SSML
                    results = SSMLSpeaker(mimic3).speak(params.text)
                else:
                    # Plain text
                    mimic3.begin_utterance()
                    mimic3.speak_text(params.text, text_language=params.text_language)
                    results = mimic3.end_utterance()

                for result in results:
                    # Add audio to existing WAV file
                    if isinstance(result, AudioResult):
                        if not wav_params_set:
                            wav_file.setframerate(result.sample_rate_hz)
                            wav_file.setsampwidth(result.sample_width_bytes)
                            wav_file.setnchannels(result.num_channels)
                            wav_params_set = True

                        wav_file.writeframes(result.audio_bytes)
            except Exception as e:
                if not wav_params_set:
                    # Set default parameters so exception can propagate
                    wav_file.setframerate(22050)
                    wav_file.setsampwidth(2)
                    wav_file.setnchannels(1)

                raise e

        wav_bytes = wav_io.getvalue()

        return wav_bytes


def do_synthesis_proc(args: argparse.Namespace, request_queue: Queue):
    """Thread handler for synthesis requests"""
    try:
        # Load Mimic 3
        mimic3 = Mimic3TextToSpeechSystem(
            Mimic3Settings(
                voice=args.voice,
                speaker=args.speaker,
                length_scale=args.length_scale,
                noise_scale=args.noise_scale,
                noise_w=args.noise_w,
                use_cuda=args.cuda,
                voices_directories=args.voices_dir,
                use_deterministic_compute=args.deterministic,
            )
        )

        with mimic3:
            if args.preload_voice:
                # Ensure voices are preloaded
                for voice_key in args.preload_voice:
                    _LOGGER.debug("Preloading voice: %s", voice_key)
                    mimic3.preload_voice(voice_key)

            _LOGGER.debug(
                "Started inference thread %s", threading.current_thread().ident
            )

            while True:
                item = request_queue.get()
                if item is None:
                    # Exit signal
                    break

                item = typing.cast(SynthesisRequest, item)

                try:
                    result = do_synthesis(item, mimic3)

                    # Set result on main loop
                    item.loop.call_soon_threadsafe(item.future.set_result, result)
                except Exception as e:
                    _LOGGER.exception("Error during inference")

                    # Signal error on main loop
                    item.loop.call_soon_threadsafe(item.future.set_exception, e)

    except Exception:
        _LOGGER.exception("Unexpected error in inference thread")
