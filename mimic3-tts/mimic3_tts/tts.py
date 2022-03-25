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
"""Implementation of OpenTTS for Mimic 3"""
import itertools
import logging
import typing
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path

from gruut_ipa import IPA
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
from xdgenvpy import XDG

from .config import TrainingConfig
from .voice import SPEAKER_TYPE, Mimic3Voice

_DIR = Path(__file__).parent

_LOGGER = logging.getLogger(__name__)

PHONEMES_LIST_TYPE = typing.List[typing.List[str]]

DEFAULT_VOICE = "en_US/vctk_low"
DEFAULT_LANGUAGE = "en_US"


# -----------------------------------------------------------------------------


@dataclass
class Mimic3Settings:
    """Settings for Mimic 3 text to speech system"""

    voice: typing.Optional[str] = None
    """Default voice key"""

    language: typing.Optional[str] = None
    """Default language (e.g., "en_US")"""

    voices_directories: typing.Optional[typing.Iterable[typing.Union[str, Path]]] = None
    """Directories to search for voices (<lang>/<voice>)"""

    speaker: typing.Optional[SPEAKER_TYPE] = None
    """Default speaker name or id"""

    length_scale: typing.Optional[float] = None
    """Default length scale (use voice config if None)"""

    noise_scale: typing.Optional[float] = None
    """Default noise scale (use voice config if None)"""

    noise_w: typing.Optional[float] = None
    """Default noise W (use voice config if None)"""

    text_language: typing.Optional[str] = None
    """Language of text (use voice language if None)"""

    sample_rate: int = 22050
    """Sample rate of silence from add_break() in Hertz"""


@dataclass
class Mimic3Phonemes:
    """Pending task to synthesize audio from phonemes with specific settings"""

    current_settings: Mimic3Settings
    """Settings used to synthesize audio"""

    phonemes: typing.List[typing.List[str]] = field(default_factory=list)
    """Phonemes for synthesis"""

    is_utterance: bool = True
    """True if this is the end of a full utterance"""


class VoiceNotFoundError(Exception):
    """Raised if a voice cannot be found"""

    def __init__(self, voice: str):
        super().__init__(f"Voice not found: {voice}")


# -----------------------------------------------------------------------------


class Mimic3TextToSpeechSystem(TextToSpeechSystem):
    """Convert text to speech using Mimic 3"""

    def __init__(self, settings: Mimic3Settings):
        self.settings = settings

        self._results: typing.List[typing.Union[BaseResult, Mimic3Phonemes]] = []
        self._loaded_voices: typing.Dict[str, Mimic3Voice] = {}

    @staticmethod
    def get_default_voices_directories() -> typing.List[Path]:
        """Get list of directories to search for voices by default.

        On Linux, this is typically:
            - $HOME/.local/share/mimic3
            - /usr/local/share/mimic3
            - /usr/share/mimic3
        """
        data_dirs = [Path(d) / "mimic3" for d in XDG().XDG_DATA_DIRS.split(":")]
        return [_DIR.parent.parent / "voices"] + data_dirs

    def get_voices(self) -> typing.Iterable[Voice]:
        """Returns an iterable of all available voices"""
        voices_dirs: typing.Iterable[
            typing.Union[str, Path]
        ] = Mimic3TextToSpeechSystem.get_default_voices_directories()

        if self.settings.voices_directories is not None:
            voices_dirs = itertools.chain(self.settings.voices_directories, voices_dirs)

        # voices/<language>/<voice>/
        for voices_dir in voices_dirs:
            voices_dir = Path(voices_dir)

            if not voices_dir.is_dir():
                _LOGGER.debug("Skipping voice directory %s", voices_dir)
                continue

            _LOGGER.debug("Searching %s for voices", voices_dir)

            for lang_dir in voices_dir.iterdir():
                if not lang_dir.is_dir():
                    continue

                for voice_dir in lang_dir.iterdir():
                    if not voice_dir.is_dir():
                        continue

                    _LOGGER.debug("Voice found in %s", voice_dir)
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

    def preload_voice(self, voice_key: str):
        """Ensure voice is loaded in memory before synthesis"""
        self._get_or_load_voice(voice_key)

    # -------------------------------------------------------------------------

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

    def begin_utterance(self):
        pass

    # pylint: disable=arguments-differ
    def speak_text(self, text: str, text_language: typing.Optional[str] = None):
        voice = self._get_or_load_voice(self.voice)

        for sent_phonemes in voice.text_to_phonemes(text, text_language=text_language):
            self._results.append(
                Mimic3Phonemes(
                    current_settings=deepcopy(self.settings),
                    phonemes=sent_phonemes,
                    is_utterance=False,
                )
            )

    # pylint: disable=arguments-differ
    def speak_tokens(
        self,
        tokens: typing.Iterable[BaseToken],
        text_language: typing.Optional[str] = None,
    ):
        voice = self._get_or_load_voice(self.voice)
        token_phonemes: PHONEMES_LIST_TYPE = []

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
                    current_settings=deepcopy(self.settings),
                    phonemes=token_phonemes,
                    is_utterance=False,
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

        sent_phonemes: PHONEMES_LIST_TYPE = []

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
            yield self._speak_sentence_phonemes(sent_phonemes, settings=last_settings)
            sent_phonemes.clear()

        self._results.clear()

    # -------------------------------------------------------------------------

    def _speak_sentence_phonemes(
        self,
        sent_phonemes,
        settings: typing.Optional[Mimic3Settings] = None,
    ) -> AudioResult:
        """Synthesize audio from phonemes using given setings"""
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

    def _get_or_load_voice(self, voice_key: str) -> Mimic3Voice:
        """Get a loaded voice or load from the file system"""
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
