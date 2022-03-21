#!/usr/bin/env python3
import logging
import time
import typing
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from xml.sax.saxutils import escape as xmlescape

import gruut
import numpy as np
import onnxruntime
import phonemes2ids
from gruut.const import LookupPhonemes, WordRole
from gruut_ipa import IPA, Phoneme, guess_phonemes
from opentts_abc import (
    AudioResult,
    BaseResult,
    BaseToken,
    MarkResult,
    Phonemes,
    SayAs,
    TextToSpeechSystem,
    Voice,
    Word,
)

from mimic3_tts.config import TrainingConfig
from mimic3_tts.utils import audio_float_to_int16
from mimic3_tts.voice import Mimic3Voice, SPEAKER_TYPE

_DIR = Path(__file__).parent

_LOGGER = logging.getLogger(__name__)

PHONEMES_LIST = typing.List[typing.List[str]]

DEFAULT_VOICE = "en_US/vctk_low"
DEFAULT_LANGUAGE = "en_US"


# -----------------------------------------------------------------------------


@dataclass
class Mimic3Settings:
    voice: typing.Optional[str] = None
    language: typing.Optional[str] = None
    voices_directories: typing.Optional[typing.Iterable[typing.Union[str, Path]]] = None
    speaker: typing.Optional[SPEAKER_TYPE] = None
    length_scale: float = 1.0
    noise_scale: float = 0.667
    noise_w: float = 0.8
    text_language: typing.Optional[str] = None
    sample_rate: int = 22050


@dataclass
class Mimic3Phonemes:
    current_settings: Mimic3Settings
    phonemes: typing.List[typing.List[str]] = field(default_factory=list)


# -----------------------------------------------------------------------------


class Mimic3TextToSpeechSystem(TextToSpeechSystem):
    """Convert text to speech using Mimic 3"""

    def __init__(self, settings: Mimic3Settings):
        self.settings = settings

        self._results: typing.List[typing.Union[BaseResult, Mimic3Phonemes]] = []

        self.loaded_voices: typing.Dict[str, Mimic3Voice] = {}

    @property
    def voice(self) -> str:
        return self.settings.voice or DEFAULT_VOICE

    @voice.setter
    def voice(self, new_voice: str):
        if new_voice != self.settings.voice:
            # Clear speaker on voice change
            self.speaker = None

        self.settings.voice = new_voice

        if "#" in self.settings.voice:
            # Split
            voice, speaker = self.settings.voice.split("#", maxsplit=1)
            self.settings.voice = voice
            self.speaker = speaker

    @property
    def speaker(self) -> typing.Optional[SPEAKER_TYPE]:
        return self.settings.speaker

    @speaker.setter
    def speaker(self, new_speaker: typing.Optional[SPEAKER_TYPE]):
        self.settings.speaker = new_speaker

    @property
    def language(self) -> str:
        return self.settings.language or DEFAULT_LANGUAGE

    @language.setter
    def language(self, new_language: str):
        self.settings.language = new_language

    @staticmethod
    def get_default_voices_directories() -> typing.List[Path]:
        return [_DIR.parent.parent / "voices"]

    def get_voices(self) -> typing.Iterable[Voice]:
        voices_dirs = (
            self.settings.voices_directories
            or Mimic3TextToSpeechSystem.get_default_voices_directories()
        )

        # voices/<language>/<voice>/
        for voices_dir in voices_dirs:
            voices_dir = Path(voices_dir)

            if not voices_dir.is_dir():
                continue

            for lang_dir in voices_dir.iterdir():
                if not lang_dir.is_dir():
                    continue

                for voice_dir in lang_dir.iterdir():
                    if not voice_dir.is_dir():
                        continue

                    voice_lang = lang_dir.name

                    # Load config
                    config_path = voice_dir / "config.json"
                    _LOGGER.debug("Loading config from %s", config_path)

                    with open(config_path, "r", encoding="utf-8") as config_file:
                        config = TrainingConfig.load(config_file)

                    properties: typing.Dict[str, typing.Any] = {
                        "length_scale": config.inference.length_scale,
                        "noise_scale": config.inference.noise_scale,
                        "noise_w": config.inference.noise_w,
                    }

                    # Load speaker names
                    voice_name = voice_dir.name
                    speakers: typing.Optional[typing.Sequence[str]] = None

                    speakers_path = voice_dir / "speakers.txt"
                    if speakers_path.is_file():
                        speakers = []
                        with open(
                            speakers_path, "r", encoding="utf-8"
                        ) as speakers_file:
                            for line in speakers_file:
                                line = line.strip()
                                if line:
                                    speakers.append(line)

                    yield Voice(
                        key=str(voice_dir.absolute()),
                        name=voice_name,
                        language=voice_lang,
                        description="",
                        speakers=speakers,
                        properties=properties,
                    )

    def begin_utterance(self):
        self._results.clear()

    def speak_text(self, text: str, text_language: typing.Optional[str] = None):
        voice = self._get_or_load_voice(self.voice)

        for sent_phonemes in voice.text_to_phonemes(text, text_language=text_language):
            self._results.append(
                Mimic3Phonemes(
                    current_settings=deepcopy(self.settings),
                    phonemes=sent_phonemes,
                )
            )

    def _speak_sentence_phonemes(
        self,
        sent_phonemes,
        settings: typing.Optional[Mimic3Settings] = None,
    ) -> AudioResult:
        settings = settings or self.settings
        voice = self._get_or_load_voice(settings.voice or self.voice)
        sent_phoneme_ids = voice.phonemes_to_ids(sent_phonemes)

        _LOGGER.debug("phonemes=%s, ids=%s", sent_phonemes, sent_phoneme_ids)

        audio = voice.ids_to_audio(
            sent_phoneme_ids,
            speaker=self.speaker,
            length_scale=settings.length_scale,
            noise_scale=settings.noise_scale,
            noise_w=settings.noise_w,
        )

        audio_bytes = audio.tobytes()
        return AudioResult(
            sample_rate_hz=voice.config.audio.sample_rate,
            audio_bytes=audio_bytes,
            # 16-bit mono
            sample_width_bytes=2,
            num_channels=1,
        )

    def speak_tokens(
        self,
        tokens: typing.Iterable[BaseToken],
        text_language: typing.Optional[str] = None,
    ):
        voice = self._get_or_load_voice(self.voice)
        token_phonemes: PHONEMES_LIST = []

        for token in tokens:
            if isinstance(token, Word):
                word_phonemes = voice.word_to_phonemes(
                    token.text, word_role=token.role, text_language=text_language
                )
                token_phonemes.append(word_phonemes)
            elif isinstance(token, Phonemes):
                phoneme_str = token.text.strip()
                if " " in phoneme_str:
                    token_phonemes.append(phoneme_str.split())
                else:
                    token_phonemes.append(list(IPA.graphemes(phoneme_str)))
            elif isinstance(token, SayAs):
                say_as_phonemes = voice.say_as_to_phonemes(
                    token.text,
                    interpret_as=token.interpret_as,
                    say_format=token.format,
                    text_language=text_language,
                )
                token_phonemes.extend(say_as_phonemes)

        if token_phonemes:
            self._results.append(
                Mimic3Phonemes(
                    current_settings=deepcopy(self.settings), phonemes=token_phonemes
                )
            )

    def add_break(self, time_ms: int):
        # Generate silence (16-bit mono at sample rate)
        num_bytes = int((time_ms / 1000.0) * self.settings.sample_rate * 2)
        audio_bytes = bytes(num_bytes)

        self._results.append(
            AudioResult(
                sample_rate_hz=self.settings.sample_rate,
                audio_bytes=audio_bytes,
                # 16-bit mono
                sample_width_bytes=2,
                num_channels=1,
            )
        )

    def set_mark(self, name: str):
        self._results.append(MarkResult(name=name))

    def end_utterance(self) -> typing.Iterable[BaseResult]:
        last_settings = self.settings

        sent_phonemes: PHONEMES_LIST = []

        for result in self._results:
            if isinstance(result, Mimic3Phonemes):
                if result.current_settings != last_settings:
                    if sent_phonemes:
                        yield self._speak_sentence_phonemes(
                            sent_phonemes, settings=last_settings
                        )
                        sent_phonemes.clear()

                sent_phonemes.extend(result.phonemes)
                last_settings = result.current_settings
            else:
                if sent_phonemes:
                    yield self._speak_sentence_phonemes(
                        sent_phonemes, settings=last_settings
                    )
                    sent_phonemes.clear()

                yield result

        if sent_phonemes:
            yield self._speak_sentence_phonemes(sent_phonemes)

    def _get_or_load_voice(self, voice_key: str) -> Mimic3Voice:
        existing_voice = self.loaded_voices.get(voice_key)
        if existing_voice is not None:
            return existing_voice

        # Look up as substring of known voice
        model_dir: typing.Optional[Path] = None
        for maybe_voice in self.get_voices():
            if maybe_voice.key.endswith(voice_key):
                model_dir = Path(maybe_voice.key)
                break

        assert model_dir is not None
        existing_voice = self.loaded_voices.get(str(model_dir.absolute()))
        if existing_voice is not None:
            # Alias
            self.loaded_voices[voice_key] = existing_voice

            return existing_voice

        voice = Mimic3Voice.load_from_directory(model_dir)

        _LOGGER.info("Loaded voice from %s", model_dir)

        # Add to cache
        self.loaded_voices[voice_key] = voice

        return voice

    # def start(self):
    #     self.stop()

    #     self._thread = threading.Thread(target=self._thread_proc, daemon=True)
    #     self._thread.start()

    # def stop(self):
    #     if self._thread is not None:
    #         self._request_queue.put(None)
    #         self._thread.join()
    #         self._thread = None

    #     # Drain queues
    #     while not self._request_queue.empty():
    #         self._request_queue.get()

    #     while not self._result_queue.empty():
    #         self._result_queue.get()

    # def _thread_proc(self):
    #     try:
    #         self._load_model()
    #         self._load_text_processor()

    #         while True:
    #             message = self._request_queue.get()
    #             if message is None:
    #                 break

    #             if isinstance(message, AddLexiconMessage):
    #                 self._add_lexicon(message.lexicon_file)
    #             elif isinstance(message, TextToSpeechMessage):
    #                 result = self._text_to_speech(**dataclasses.asdict(message))
    #                 self._result_queue.put(result)

    #     except Exception:
    #         _LOGGER.exception("_thread_proc")

    # def _load_model(self):
    #     """Load model configuration and generator"""

    #     if self._config is None:
    #         config_path = self.model_dir / "config.json"
    #         _LOGGER.debug("Loading model config from %s", config_path)

    #         with open(config_path, "r", encoding="utf-8") as config_file:
    #             self._config = TrainingConfig.load(config_file)

    #     self.lang = self.lang or self._config.text_language or "en_US"

    #     if self._phoneme_to_id is None:
    #         # phoneme -> id
    #         phoneme_ids_path = self.model_dir / "phonemes.txt"
    #         _LOGGER.debug("Loading model phonemes from %s", phoneme_ids_path)
    #         with open(phoneme_ids_path, "r", encoding="utf-8") as ids_file:
    #             self._phoneme_to_id = phonemes2ids.load_phoneme_ids(ids_file)

    #         valid_phonemes = []
    #         for phoneme_str in self._phoneme_to_id:
    #             maybe_phoneme = Phoneme(phoneme_str)
    #             if any(
    #                 [
    #                     maybe_phoneme.vowel,
    #                     maybe_phoneme.consonant,
    #                     maybe_phoneme.dipthong,
    #                     maybe_phoneme.schwa,
    #                 ]
    #             ):
    #                 valid_phonemes.append(maybe_phoneme)

    #         self._voice_phonemes = Phonemes(phonemes=valid_phonemes)

    #     if self._phoneme_map is None:
    #         # phoneme -> phoneme, phoneme, ...
    #         phoneme_map_path = self.model_dir / "phoneme_map.txt"
    #         if phoneme_map_path.is_file():
    #             _LOGGER.debug("Loading phoneme map from %s", phoneme_map_path)
    #             with open(phoneme_map_path, "r", encoding="utf-8") as map_file:
    #                 self._phoneme_map = phonemes2ids.utils.load_phoneme_map(map_file)

    #     if self._onnx_model is None:
    #         generator_path = self.model_dir / "generator.onnx"
    #         _LOGGER.debug("Loading model from %s", generator_path)

    #         sess_options = onnxruntime.SessionOptions()
    #         sess_options.enable_cpu_mem_arena = False
    #         sess_options.enable_mem_pattern = False
    #         sess_options.enable_mem_reuse = False

    #         self._onnx_model = onnxruntime.InferenceSession(
    #             str(generator_path), sess_options=sess_options
    #         )

    # def _load_text_processor(self):
    #     if self._text_processor is None:
    #         self._text_processor = gruut.TextProcessor(default_lang=self.lang)

    # def add_lexicon(self, lexicon_file: typing.Iterable[str]):
    #     """Load a custom pronunciation lexicon from a file.

    #     Format is:
    #     <word> <role> <phoneme> <phoneme> ...

    #     Role can be things like "gruut:VB" or "gruut:NN".
    #     Use "_" for the default role (any part of speech).
    #     """
    #     self._request_queue.put(AddLexiconMessage(lexicon_file=list(lexicon_file)))

    # def _add_lexicon(self, lexicon_file: typing.Iterable[str]):
    #     self._load_text_processor()
    #     assert self._text_processor is not None

    #     # word -> role -> [phoneme, phoneme, ...]
    #     lexicon: typing.Dict[str, typing.Dict[str, typing.List[str]]] = {}

    #     for line in lexicon_file:
    #         line = line.strip()
    #         if not line:
    #             continue

    #         word, role, *phonemes = line.split()
    #         if (not word) or (not phonemes):
    #             _LOGGER.warning("Empty word or pronunciation in lexicon: %s", line)
    #             continue

    #         if role == "_":
    #             role = WordRole.DEFAULT

    #         word_roles = lexicon.get(word)
    #         if word_roles is None:
    #             word_roles = {}
    #             lexicon[word] = word_roles

    #         word_roles[role] = phonemes

    #     if lexicon:

    #         # Wrap the "lookup_phonemes" method in the gruut text processor.
    #         # Our lexicon will be consulted first.
    #         settings = self._text_processor.get_settings()
    #         base_lookup = settings.lookup_phonemes

    #         def lookup_phonemes(word: str, role: typing.Optional[str] = None, **kwargs):
    #             word_roles = lexicon.get(word)

    #             if not word_roles:
    #                 # Try lower case
    #                 word_roles = lexicon.get(word.lower())

    #             if word_roles:
    #                 if role is None:
    #                     role = WordRole.DEFAULT

    #                 phonemes = word_roles.get(role)

    #                 if (phonemes is None) and (role != WordRole.DEFAULT):
    #                     phonemes = word_roles.get(WordRole.DEFAULT)

    #                 if phonemes:
    #                     return phonemes

    #             if base_lookup is not None:
    #                 return base_lookup(word, role, **kwargs)

    #             return None

    #         settings.lookup_phonemes = typing.cast(LookupPhonemes, lookup_phonemes)
    #         _LOGGER.debug("Added custom pronunciations for %s word(s)", len(lexicon))

    # def text_to_speech(
    #     self,
    #     text: str,
    #     speaker_id: typing.Optional[int] = None,
    #     length_scale: typing.Optional[float] = None,
    #     noise_scale: typing.Optional[float] = None,
    #     noise_w: typing.Optional[float] = None,
    #     ssml: bool = False,
    #     text_language: typing.Optional[str] = None,
    # ) -> Result:
    #     self._request_queue.put(
    #         TextToSpeechMessage(
    #             text=text,
    #             speaker_id=speaker_id,
    #             length_scale=length_scale,
    #             noise_scale=noise_scale,
    #             noise_w=noise_w,
    #             ssml=ssml,
    #             text_language=text_language,
    #         )
    #     )

    #     result = typing.cast(Result, self._result_queue.get())

    #     return result

    # def _text_to_speech(
    #     self,
    #     text: str,
    #     speaker_id: typing.Optional[int] = None,
    #     length_scale: typing.Optional[float] = None,
    #     noise_scale: typing.Optional[float] = None,
    #     noise_w: typing.Optional[float] = None,
    #     ssml: bool = False,
    #     text_language: typing.Optional[str] = None,
    # ) -> Result:
    #     """Speak text and return WAV audio as bytes"""
    #     text_language = text_language or self.lang
    #     assert self._text_processor is not None

    #     # Ensure model is loaded
    #     assert self.lang is not None
    #     assert self._config is not None
    #     assert self._phoneme_to_id is not None
    #     assert self._onnx_model is not None

    #     # Resolve settings
    #     if speaker_id is None:
    #         speaker_id = self.speaker_id or 0

    #     if length_scale is None:
    #         length_scale = self.length_scale

    #     if noise_scale is None:
    #         noise_scale = self.noise_scale

    #     if noise_w is None:
    #         noise_w = self.noise_w

    #     # Process text into sentences
    #     result = Result(text=text)
    #     audio_arrays: typing.List[np.ndarray] = []

    #     graph, root = self._text_processor.process(text, lang=text_language, ssml=ssml)
    #     sentences = list(self._text_processor.sentences(graph, root))

    #     for sentence in sentences:
    #         result.sentence_words.append([w.text for w in sentence])

    #         if text_language == self.lang:
    #             sent_phonemes = [w.phonemes for w in sentence if w.phonemes]
    #         else:
    #             # Convert phonemes to ids to target language
    #             other_sent_phonemes = [w.phonemes for w in sentence if w.phonemes]
    #             _LOGGER.debug(other_sent_phonemes)

    #             sent_phonemes = []
    #             for other_word_p in other_sent_phonemes:
    #                 word_p = []
    #                 for other_p in other_word_p:
    #                     if IPA.is_break(other_p):
    #                         # Keep breaks
    #                         word_p.append(other_p)
    #                         continue

    #                     original_p = other_p
    #                     stress = ""
    #                     while other_p and IPA.is_stress(other_p[0]):
    #                         stress = other_p[0]
    #                         other_p = other_p[1:]

    #                     if not other_p:
    #                         continue

    #                     if other_p in self._phoneme_to_id:
    #                         word_p.append(original_p)
    #                         continue

    #                     assert self._voice_phonemes is not None
    #                     guessed = guess_phonemes(
    #                         other_p, to_phonemes=self._voice_phonemes
    #                     )
    #                     if guessed.phonemes:
    #                         word_p.extend([p.text for p in guessed.phonemes])

    #                 if word_p:
    #                     sent_phonemes.append(word_p)

    #         result.sentence_phonemes.append(sent_phonemes)

    #         sent_phoneme_ids = phonemes2ids.phonemes2ids(
    #             word_phonemes=sent_phonemes,
    #             phoneme_to_id=self._phoneme_to_id,
    #             pad=self._config.phonemes.pad,
    #             bos=self._config.phonemes.bos,
    #             eos=self._config.phonemes.eos,
    #             auto_bos_eos=self._config.phonemes.auto_bos_eos,
    #             blank=self._config.phonemes.blank,
    #             blank_word=self._config.phonemes.blank_word,
    #             blank_between=self._config.phonemes.blank_between,
    #             blank_at_start=self._config.phonemes.blank_at_start,
    #             blank_at_end=self._config.phonemes.blank_at_end,
    #             simple_punctuation=self._config.phonemes.simple_punctuation,
    #             punctuation_map=self._config.phonemes.punctuation_map,
    #             separate=self._config.phonemes.separate,
    #             separate_graphemes=self._config.phonemes.separate_graphemes,
    #             separate_tones=self._config.phonemes.separate_tones,
    #             tone_before=self._config.phonemes.tone_before,
    #             phoneme_map=self._phoneme_map or self._config.phonemes.phoneme_map,
    #             fail_on_missing=False,
    #         )

    #         result.sentence_phoneme_ids.append(sent_phonemes)

    #         _LOGGER.debug("%s %s %s", sentence.text, sent_phonemes, sent_phoneme_ids)

    #         # Create model inputs
    #         text_array = np.expand_dims(np.array(sent_phoneme_ids, dtype=np.int64), 0)
    #         text_lengths_array = np.array([text_array.shape[1]], dtype=np.int64)
    #         scales_array = np.array(
    #             [noise_scale, length_scale, noise_w], dtype=np.float32
    #         )

    #         inputs = {
    #             "input": text_array,
    #             "input_lengths": text_lengths_array,
    #             "scales": scales_array,
    #         }

    #         if self._config.is_multispeaker:
    #             speaker_id_array = np.array([speaker_id], dtype=np.int64)
    #             inputs["sid"] = speaker_id_array

    #         # Infer audio from phonemes
    #         start_time = time.perf_counter()
    #         audio = self._onnx_model.run(None, inputs)[0].squeeze()
    #         audio = audio_float_to_int16(audio)
    #         end_time = time.perf_counter()

    #         # Compute real-time factor
    #         audio_duration_sec = audio.shape[-1] / self._config.audio.sample_rate
    #         infer_sec = end_time - start_time
    #         real_time_factor = (
    #             infer_sec / audio_duration_sec if audio_duration_sec > 0 else 0.0
    #         )

    #         _LOGGER.debug("RTF: %s", real_time_factor)

    #         audio_arrays.append(audio)

    #     # Write to WAV and return bytes
    #     with io.BytesIO() as wav_file:
    #         write_wav(
    #             wav_file, self._config.audio.sample_rate, np.concatenate(audio_arrays),
    #         )

    #         result.wav_bytes = wav_file.getvalue()

    #     return result
