#!/usr/bin/env python3
import csv
import itertools
import logging
import time
import typing
from abc import ABCMeta, abstractmethod
from pathlib import Path
from xml.sax.saxutils import escape as xmlescape

import espeak_phonemizer
import gruut
import numpy as np
import onnxruntime
import phonemes2ids
from gruut_ipa import IPA

from mimic3_tts.config import Phonemizer, TrainingConfig
from mimic3_tts.utils import audio_float_to_int16

PHONEME_TYPE = str
PHONEME_ID_TYPE = int
WORD_PHONEMES_TYPE = typing.List[typing.List[PHONEME_TYPE]]
PHONEME_MAP_TYPE = typing.Dict[PHONEME_TYPE, typing.List[PHONEME_TYPE]]

SPEAKER_NAME_TYPE = str
SPEAKER_ID_TYPE = int
SPEAKER_TYPE = typing.Union[SPEAKER_NAME_TYPE, SPEAKER_ID_TYPE]
SPEAKER_MAP_TYPE = typing.Dict[SPEAKER_NAME_TYPE, SPEAKER_ID_TYPE]

DEFAULT_LANGUAGE = "en_US"

_LOGGER = logging.getLogger(__name__)

# -----------------------------------------------------------------------------


class Mimic3Voice(metaclass=ABCMeta):
    def __init__(
        self,
        config: TrainingConfig,
        onnx_model: onnxruntime.InferenceSession,
        phoneme_to_id: typing.Dict[PHONEME_TYPE, int],
        phoneme_map: typing.Optional[PHONEME_MAP_TYPE] = None,
        speaker_map: typing.Optional[SPEAKER_MAP_TYPE] = None,
    ):
        self.config = config
        self.onnx_model = onnx_model
        self.phoneme_to_id = phoneme_to_id
        self.phoneme_map = phoneme_map
        self.speaker_map = speaker_map

    @abstractmethod
    def text_to_phonemes(
        self, text: str, text_language: typing.Optional[str] = None
    ) -> typing.Iterable[WORD_PHONEMES_TYPE]:
        pass

    def word_to_phonemes(
        self,
        word_text: str,
        word_role: typing.Optional[str] = None,
        text_language: typing.Optional[str] = None,
    ) -> typing.List[PHONEME_TYPE]:
        word_phonemes = []
        for sent_phonemes in self.text_to_phonemes(
            word_text, text_language=text_language
        ):
            for sent_word_phonemes in sent_phonemes:
                word_phonemes.extend(sent_word_phonemes)

        return word_phonemes

    def say_as_to_phonemes(
        self,
        text: str,
        interpret_as: str,
        say_format: typing.Optional[str] = None,
        text_language: typing.Optional[str] = None,
    ) -> WORD_PHONEMES_TYPE:
        word_phonemes = []
        for sent_phonemes in self.text_to_phonemes(text, text_language=text_language):
            word_phonemes.extend(sent_phonemes)

        return word_phonemes

    def phonemes_to_ids(
        self, phonemes: WORD_PHONEMES_TYPE
    ) -> typing.Sequence[PHONEME_ID_TYPE]:
        phoneme_map = self.phoneme_map or self.config.phonemes.phoneme_map

        return phonemes2ids.phonemes2ids(
            word_phonemes=phonemes,
            phoneme_to_id=self.phoneme_to_id,
            pad=self.config.phonemes.pad,
            bos=self.config.phonemes.bos,
            eos=self.config.phonemes.eos,
            auto_bos_eos=self.config.phonemes.auto_bos_eos,
            blank=self.config.phonemes.blank,
            blank_word=self.config.phonemes.blank_word,
            blank_between=self.config.phonemes.blank_between,
            blank_at_start=self.config.phonemes.blank_at_start,
            blank_at_end=self.config.phonemes.blank_at_end,
            simple_punctuation=self.config.phonemes.simple_punctuation,
            punctuation_map=self.config.phonemes.punctuation_map,
            separate=self.config.phonemes.separate,
            separate_graphemes=self.config.phonemes.separate_graphemes,
            separate_tones=self.config.phonemes.separate_tones,
            tone_before=self.config.phonemes.tone_before,
            phoneme_map=phoneme_map,
            fail_on_missing=False,
        )

    def ids_to_audio(
        self,
        phoneme_ids: typing.Sequence[PHONEME_ID_TYPE],
        speaker: typing.Optional[
            typing.Union[SPEAKER_NAME_TYPE, SPEAKER_ID_TYPE]
        ] = None,
        length_scale: typing.Optional[float] = None,
        noise_scale: typing.Optional[float] = None,
        noise_w: typing.Optional[float] = None,
    ) -> np.ndarray:
        if length_scale is None:
            length_scale = self.config.inference.length_scale

        if noise_scale is None:
            noise_scale = self.config.inference.noise_scale

        if noise_w is None:
            noise_w = self.config.inference.noise_w

        # Create model inputs
        text_array = np.expand_dims(np.array(phoneme_ids, dtype=np.int64), 0)
        text_lengths_array = np.array([text_array.shape[1]], dtype=np.int64)
        scales_array = np.array(
            [
                noise_scale,
                length_scale,
                noise_w,
            ],
            dtype=np.float32,
        )

        # TODO: Use settings from voice config
        inputs = {
            "input": text_array,
            "input_lengths": text_lengths_array,
            "scales": scales_array,
        }

        speaker_id = 0
        if self.config.is_multispeaker:
            if isinstance(speaker, SPEAKER_NAME_TYPE):
                if self.speaker_map:
                    maybe_speaker_id = self.speaker_map.get(speaker)
                    if maybe_speaker_id is None:
                        try:
                            # Interpret as speaker id
                            speaker_id = int(speaker)
                        except ValueError:
                            _LOGGER.warning(
                                "Unable to find a speaker with the name '%s'. Falling back to first speaker.",
                                speaker,
                            )
                            pass
                    else:
                        speaker_id = maybe_speaker_id
            elif speaker is not None:
                speaker_id = speaker

            speaker_id_array = np.array([speaker_id], dtype=np.int64)
            inputs["sid"] = speaker_id_array

        _LOGGER.debug(
            "TTS settings: speaker-id=%s, length-scale=%s, noise-scale=%s, noise-w=%s",
            speaker_id,
            length_scale,
            noise_scale,
            noise_w,
        )

        # Infer audio from phonemes
        start_time = time.perf_counter()
        audio = self.onnx_model.run(None, inputs)[0].squeeze()
        audio = audio_float_to_int16(audio)
        end_time = time.perf_counter()

        # Compute real-time factor
        audio_duration_sec = audio.shape[-1] / self.config.audio.sample_rate
        infer_sec = end_time - start_time
        real_time_factor = (
            infer_sec / audio_duration_sec if audio_duration_sec > 0 else 0.0
        )

        _LOGGER.debug("RTF: %s", real_time_factor)

        return audio

    @staticmethod
    def load_from_directory(
        voice_dir: typing.Union[str, Path],
        session_options: typing.Optional[onnxruntime.SessionOptions] = None,
    ) -> "Mimic3Voice":
        voice_dir = Path(voice_dir)
        _LOGGER.debug("Loading voice from %s", voice_dir)

        config_path = voice_dir / "config.json"
        _LOGGER.debug("Loading config from %s", config_path)

        with open(config_path, "r", encoding="utf-8") as config_file:
            config = TrainingConfig.load(config_file)

        # phoneme -> id
        phoneme_ids_path = voice_dir / "phonemes.txt"
        _LOGGER.debug("Loading model phonemes from %s", phoneme_ids_path)
        with open(phoneme_ids_path, "r", encoding="utf-8") as ids_file:
            phoneme_to_id = phonemes2ids.load_phoneme_ids(ids_file)

        generator_path = voice_dir / "generator.onnx"
        _LOGGER.debug("Loading model from %s", generator_path)

        # Load onnx model
        session_options = session_options or onnxruntime.SessionOptions()
        onnx_model = onnxruntime.InferenceSession(
            str(generator_path), sess_options=session_options
        )

        # phoneme -> phoneme, phoneme, ...
        phoneme_map: typing.Optional[PHONEME_MAP_TYPE] = None
        phoneme_map_path = voice_dir / "phoneme_map.txt"
        if phoneme_map_path.is_file():
            _LOGGER.debug("Loading phoneme map from %s", phoneme_map_path)
            with open(phoneme_map_path, "r", encoding="utf-8") as map_file:
                phoneme_map = phonemes2ids.utils.load_phoneme_map(map_file)

        # id -> speaker
        speaker_map: typing.Optional[SPEAKER_MAP_TYPE] = None
        speaker_map_path = voice_dir / "speaker_map.csv"
        if speaker_map_path.is_file():
            _LOGGER.debug("Loading speaker map from %s", speaker_map_path)
            with open(speaker_map_path, "r", encoding="utf-8") as map_file:
                # id | dataset | name | [alias] | [alias] ...
                reader = csv.reader(map_file, delimiter="|")
                speaker_map = {}
                for row in reader:
                    speaker_id = int(row[0])
                    for alias in row[2:]:
                        speaker_map[alias] = speaker_id

        if config.phonemizer == Phonemizer.GRUUT:
            return GruutVoice(
                config=config,
                onnx_model=onnx_model,
                phoneme_to_id=phoneme_to_id,
                phoneme_map=phoneme_map,
                speaker_map=speaker_map,
            )

        if config.phonemizer == Phonemizer.ESPEAK:
            return EspeakVoice(
                config=config,
                onnx_model=onnx_model,
                phoneme_to_id=phoneme_to_id,
                phoneme_map=phoneme_map,
                speaker_map=speaker_map,
            )
        if config.phonemizer == Phonemizer.SYMBOLS:
            return SymbolsVoice(
                config=config,
                onnx_model=onnx_model,
                phoneme_to_id=phoneme_to_id,
                phoneme_map=phoneme_map,
                speaker_map=speaker_map,
            )

        raise ValueError(f"Unsupported phonemizer: {config.phonemizer}")


# -----------------------------------------------------------------------------


class GruutVoice(Mimic3Voice):
    def text_to_phonemes(
        self, text: str, text_language: typing.Optional[str] = None
    ) -> typing.Iterable[WORD_PHONEMES_TYPE]:
        text_language = text_language or self.config.text_language or DEFAULT_LANGUAGE
        for sentence in gruut.sentences(text, lang=text_language):
            sent_phonemes = [w.phonemes for w in sentence if w.phonemes]
            if sent_phonemes:
                yield sent_phonemes

    def word_to_phonemes(
        self,
        word_text: str,
        word_role: typing.Optional[str] = None,
        text_language: typing.Optional[str] = None,
    ) -> typing.List[PHONEME_TYPE]:
        text_language = text_language or self.config.text_language or DEFAULT_LANGUAGE

        word_role = xmlescape(word_role) if word_role else ""
        word_text = xmlescape(word_text)

        sentence = next(
            iter(
                gruut.sentences(
                    f'<w role="{word_role}">{word_text}</w>',
                    ssml=True,
                    lang=text_language,
                )
            )
        )

        sentence_word = next(iter(sentence))

        return sentence_word.phonemes

    def say_as_to_phonemes(
        self,
        text: str,
        interpret_as: str,
        say_format: typing.Optional[str] = None,
        text_language: typing.Optional[str] = None,
    ) -> WORD_PHONEMES_TYPE:
        text_language = text_language or self.config.text_language or DEFAULT_LANGUAGE

        word_text = xmlescape(text)
        interpret_as = xmlescape(interpret_as)
        format_attr = f'format="{xmlescape(say_format)}"' if say_format else ""

        sentences = gruut.sentences(
            f'<say-as interpret-as="{interpret_as}" {format_attr}>{word_text}</say-as>',
            ssml=True,
            lang=text_language,
        )

        sent_phonemes: WORD_PHONEMES_TYPE = []

        for sentence in sentences:
            sent_phonemes.extend(w.phonemes for w in sentence if w.phonemes)

        return sent_phonemes


# -----------------------------------------------------------------------------


class EspeakVoice(Mimic3Voice):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._phonemizer = espeak_phonemizer.Phonemizer()

    def text_to_phonemes(
        self, text: str, text_language: typing.Optional[str] = None
    ) -> typing.Iterable[WORD_PHONEMES_TYPE]:
        phoneme_separator = ""
        word_separator = self.config.phonemes.word_separator

        text_language = text_language or self.config.text_language or DEFAULT_LANGUAGE

        voice = self._language_to_voice(text_language)

        phoneme_str = self._phonemizer.phonemize(
            text,
            voice=voice,
            keep_clause_breakers=True,
            phoneme_separator=phoneme_separator,
            word_separator=word_separator,
            punctuation_separator=phoneme_separator,
        )

        word_phonemes = [
            list(IPA.graphemes(wp_str)) for wp_str in phoneme_str.split(word_separator)
        ]

        yield word_phonemes

    def word_to_phonemes(
        self,
        word_text: str,
        word_role: typing.Optional[str] = None,
        text_language: typing.Optional[str] = None,
    ) -> typing.List[PHONEME_TYPE]:
        phoneme_separator = ""
        text_language = text_language or self.config.text_language or DEFAULT_LANGUAGE

        word_role = xmlescape(word_role) if word_role else ""
        word_text = xmlescape(word_text)

        voice = self._language_to_voice(text_language)

        phoneme_str = self._phonemizer.phonemize(
            f'<w role="{word_role}">{word_text}</w>',
            voice=voice,
            keep_clause_breakers=True,
            phoneme_separator=phoneme_separator,
            punctuation_separator=phoneme_separator,
            ssml=True,
        )

        word_phonemes = list(IPA.graphemes(phoneme_str))

        return word_phonemes

    def say_as_to_phonemes(
        self,
        text: str,
        interpret_as: str,
        say_format: typing.Optional[str] = None,
        text_language: typing.Optional[str] = None,
    ) -> WORD_PHONEMES_TYPE:
        phoneme_separator = ""
        word_separator = self.config.phonemes.word_separator
        text_language = text_language or self.config.text_language or DEFAULT_LANGUAGE

        word_text = xmlescape(text)
        interpret_as = xmlescape(interpret_as)
        format_attr = f'format="{xmlescape(say_format)}"' if say_format else ""

        voice = self._language_to_voice(text_language)

        phoneme_str = self._phonemizer.phonemize(
            f'<say-as interpret-as="{interpret_as}" {format_attr}>{word_text}</say-as>',
            voice=voice,
            keep_clause_breakers=True,
            phoneme_separator=phoneme_separator,
            punctuation_separator=phoneme_separator,
            word_separator=word_separator,
            ssml=True,
        )

        word_phonemes = [
            list(IPA.graphemes(wp_str)) for wp_str in phoneme_str.split(word_separator)
        ]

        return word_phonemes

    def _language_to_voice(self, language: str) -> str:
        # en_US -> en-us
        return language.strip().lower().replace("_", "-")


# -----------------------------------------------------------------------------


class SymbolsVoice(Mimic3Voice):
    def text_to_phonemes(
        self, text: str, text_language: typing.Optional[str] = None
    ) -> typing.Iterable[WORD_PHONEMES_TYPE]:
        word_separator = self.config.phonemes.word_separator
        word_phonemes = [
            list(IPA.graphemes(wp_str)) for wp_str in text.split(word_separator)
        ]
        yield word_phonemes
