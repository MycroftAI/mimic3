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
    length_scale: typing.Optional[float] = None
    noise_scale: typing.Optional[float] = None
    noise_w: typing.Optional[float] = None
    text_language: typing.Optional[str] = None
    sample_rate: int = 22050


@dataclass
class Mimic3Phonemes:
    current_settings: Mimic3Settings
    phonemes: typing.List[typing.List[str]] = field(default_factory=list)
    is_utterance: bool = True


class VoiceNotFoundError(Exception):
    def __init__(self, voice: str):
        super().__init__(f"Voice not found: {voice}")


# -----------------------------------------------------------------------------


class Mimic3TextToSpeechSystem(TextToSpeechSystem):
    """Convert text to speech using Mimic 3"""

    def __init__(self, settings: Mimic3Settings):
        self.settings = settings

        self._results: typing.List[typing.Union[BaseResult, Mimic3Phonemes]] = []
        self._loaded_voices: typing.Dict[str, Mimic3Voice] = {}

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
        pass

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
                if result.is_utterance or (result.current_settings != last_settings):
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
            sent_phonemes.clear()

        self._results.clear()

    def preload_voice(self, voice_key: str):
        self._get_or_load_voice(voice_key)

    def _get_or_load_voice(self, voice_key: str) -> Mimic3Voice:
        existing_voice = self._loaded_voices.get(voice_key)
        if existing_voice is not None:
            return existing_voice

        # Look up as substring of known voice
        model_dir: typing.Optional[Path] = None
        for maybe_voice in self.get_voices():
            if maybe_voice.key.endswith(voice_key):
                model_dir = Path(maybe_voice.key)
                break

        if model_dir is None:
            raise VoiceNotFoundError(voice_key)

        # Full path to voice model directory
        canonical_key = str(model_dir.absolute())

        existing_voice = self._loaded_voices.get(canonical_key)
        if existing_voice is not None:
            # Alias
            self._loaded_voices[voice_key] = existing_voice

            return existing_voice

        voice = Mimic3Voice.load_from_directory(model_dir)

        _LOGGER.info("Loaded voice from %s", model_dir)

        # Add to cache
        self._loaded_voices[voice_key] = voice
        self._loaded_voices[canonical_key] = voice

        return voice
