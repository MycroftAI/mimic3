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
import audioop
import itertools
import logging
import re
import typing
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path

from gruut_ipa import IPA
from xdgenvpy import XDG

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

from ._resources import _VOICES
from .config import TrainingConfig
from .const import (
    DEFAULT_LANGUAGE,
    DEFAULT_RATE,
    DEFAULT_VOICE,
    DEFAULT_VOICES_DOWNLOAD_DIR,
    DEFAULT_VOICES_URL_FORMAT,
    DEFAULT_VOLUME,
)
from .download import VoiceFile, download_voice
from .utils import WILDCARD, wildcard_to_regex
from .voice import SPEAKER_TYPE, BreakType, Mimic3Voice

_DIR = Path(__file__).parent

_LOGGER = logging.getLogger(__name__)

PHONEMES_LIST_TYPE = typing.List[typing.List[str]]


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

    voices_url_format: typing.Optional[str] = DEFAULT_VOICES_URL_FORMAT
    """URL format string for a voice directory.

    May contain:
      * {key} - unique voice key
      * {lang} - voice language
      * {name} - voice name
    """

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

    voices_download_dir: typing.Union[str, Path] = DEFAULT_VOICES_DOWNLOAD_DIR
    """Directory to download voices to"""

    no_download: bool = False
    """Do not download voices automatically"""

    use_cuda: bool = False
    """Use CUDA GPU acceleration (requires onnxruntime-gpu)"""

    share_onnx_models_between_threads: bool = True
    """If True, Onnx models are shared between threads"""

    volume: float = DEFAULT_VOLUME
    """Voice volume in [0, 100]"""

    rate: float = DEFAULT_RATE
    """Voice speaking rate (< 1 is slower, > 1 is faster)"""

    use_deterministic_compute: bool = False
    """Force onnxruntime to use deterministic compute mode. For fully deterministic synthesis, also set noise_scale and noise_w to 0."""


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
            - $HOME/.local/share/mycroft/mimic3/voices
            - /usr/local/share/mycroft/mimic3/voices
            - /usr/share/mycroft/mimic3/voices
        """
        return [
            Path(d) / "mycroft" / "mimic3" / "voices"
            for d in XDG().XDG_DATA_DIRS.split(":")
        ]

    def get_voices(self) -> typing.Iterable[Voice]:
        """Returns an iterable of all available voices"""
        voices_dirs: typing.Iterable[
            typing.Union[str, Path]
        ] = Mimic3TextToSpeechSystem.get_default_voices_directories()

        if self.settings.voices_directories is not None:
            voices_dirs = itertools.chain(self.settings.voices_directories, voices_dirs)

        known_voices = set(_VOICES.keys())

        # voices/<language>/<voice>/
        for voices_dir in voices_dirs:
            voices_dir = Path(voices_dir)

            if not voices_dir.is_dir() or voices_dir.name.startswith("."):
                _LOGGER.debug("Skipping voice directory %s", voices_dir)
                continue

            _LOGGER.debug("Searching %s for voices", voices_dir)

            for lang_dir in voices_dir.iterdir():
                if not lang_dir.is_dir() or lang_dir.name.startswith("."):
                    continue

                for voice_dir in lang_dir.iterdir():
                    if not voice_dir.is_dir() or voice_dir.name.startswith("."):
                        continue

                    config_path = voice_dir / "config.json"
                    if not config_path.is_file():
                        continue

                    _LOGGER.debug("Voice found in %s", voice_dir)
                    voice_lang = lang_dir.name

                    # Load config
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

                    # Load aliases
                    aliases: typing.Optional[typing.Set[str]] = None
                    aliases_path = voice_dir / "ALIASES"
                    if aliases_path.is_file():
                        aliases = set()

                        with open(aliases_path, "r", encoding="utf-8") as aliases_file:
                            for line in aliases_file:
                                line = line.strip()
                                if line:
                                    aliases.add(line)

                    voice_key = f"{voice_lang}/{voice_name}"

                    yield Voice(
                        key=voice_key,
                        name=voice_name,
                        language=voice_lang,
                        description="",
                        speakers=speakers,
                        location=str(voice_dir.absolute()),
                        properties=properties,
                        aliases=aliases,
                    )

                    known_voices.discard(voice_key)

        # Yield voices that haven't yet been downloaded
        for voice_key in known_voices:
            voice_lang, voice_name = voice_key.split("/", maxsplit=1)
            voice_info = _VOICES.get(voice_key, {})
            speakers = voice_info.get("speakers", [])
            properties = voice_info.get("properties", {})

            yield Voice(
                key=voice_key,
                name=voice_name,
                language=voice_lang,
                description="",
                speakers=speakers,
                location=str.format(
                    self.settings.voices_url_format or DEFAULT_VOICES_URL_FORMAT,
                    lang=voice_lang,
                    name=voice_name,
                    key=voice_key,
                ),
                properties=properties,
            )

    def preload_voice(self, voice_key: str):
        """Ensure voice(s) are loaded in memory before synthesis.

        Voice key may contain wildcards (*).
        """
        voice_keys = []

        if WILDCARD in voice_key:
            key_or_pattern = wildcard_to_regex(voice_key, wildcard=WILDCARD)
            if isinstance(key_or_pattern, re.Pattern):
                # Wildcards
                for maybe_key in _VOICES.keys():
                    if key_or_pattern.match(maybe_key):
                        voice_keys.append(maybe_key)

                _LOGGER.debug("%s matched %s", key_or_pattern, voice_keys)
            else:
                # Didn't contain wildcards
                voice_keys.append(voice_key)
        else:
            # No wildcards
            voice_keys.append(voice_key)

        for key_to_load in voice_keys:
            self._get_or_load_voice(key_to_load)

    # -------------------------------------------------------------------------

    @property
    def voice(self) -> str:
        return self.settings.voice or DEFAULT_VOICE

    @voice.setter
    def voice(self, new_voice: str):
        if new_voice != self.settings.voice:
            # Clear speaker on voice change
            self.speaker = None

        self.settings.voice = new_voice or DEFAULT_VOICE

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

    @property
    def volume(self) -> float:
        return self.settings.volume

    @volume.setter
    def volume(self, new_volume: float):
        self.settings.volume = max(0, min(100, new_volume))

    @property
    def rate(self) -> float:
        return self.settings.rate

    @rate.setter
    def rate(self, new_rate: float):
        self.settings.rate = new_rate

    def begin_utterance(self):
        pass

    def speak_text(self, text: str, text_language: typing.Optional[str] = None):
        voice = self._get_or_load_voice(self.voice)

        # Automatically append text (e.g., punctuation) if not present
        append_text = voice.config.inference.auto_append_text
        if append_text and (not text.endswith(append_text)):
            text += append_text

        # Automatic silence after major/minor breaks (optional)
        minor_break_ms = voice.config.inference.minor_break_ms
        major_break_ms = voice.config.inference.major_break_ms

        # Process chunks
        for sent_phonemes, break_type in voice.text_to_phonemes(
            text, text_language=text_language
        ):
            add_major_silence = (break_type == BreakType.MAJOR) and (
                major_break_ms is not None
            )
            add_minor_silence = (break_type == BreakType.MINOR) and (
                minor_break_ms is not None
            )

            # Utterances have start/end meta phonemes (usually ^ and $)
            is_utterance = (
                (break_type == BreakType.UTTERANCE)
                or add_major_silence
                or add_minor_silence
            )

            self._results.append(
                Mimic3Phonemes(
                    current_settings=deepcopy(self.settings),
                    phonemes=sent_phonemes,
                    is_utterance=is_utterance,
                )
            )

            # Add silence if using manual break intervals
            if add_major_silence:
                assert major_break_ms is not None
                self.add_break(major_break_ms)
            elif add_minor_silence:
                assert minor_break_ms is not None
                self.add_break(minor_break_ms)

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
        num_samples = int((time_ms / 1000.0) * self.settings.sample_rate)
        audio_bytes = bytes(num_samples * 2)

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
        last_settings: typing.Optional[Mimic3Settings] = None

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
            speaker=settings.speaker,
            length_scale=settings.length_scale,
            noise_scale=settings.noise_scale,
            noise_w=settings.noise_w,
            rate=settings.rate,
        )

        audio_bytes = audio.tobytes()

        if settings.volume != DEFAULT_VOLUME:
            audio_bytes = audioop.mul(audio_bytes, 2, settings.volume / 100.0)

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
            if (voice_key == maybe_voice.key) or (
                maybe_voice.aliases and (voice_key in maybe_voice.aliases)
            ):
                maybe_model_dir = Path(maybe_voice.location)

                if (not maybe_model_dir.is_dir()) and (not self.settings.no_download):
                    # Download voice
                    maybe_model_dir = self._download_voice(voice_key)

                if maybe_model_dir.is_dir():
                    # Voice found
                    model_dir = maybe_model_dir
                    break

        if model_dir is None:
            raise VoiceNotFoundError(voice_key)

        voice_lang = model_dir.parent.name
        voice_name = model_dir.name
        canonical_key = f"{voice_lang}/{voice_name}"

        existing_voice = self._loaded_voices.get(canonical_key)
        if existing_voice is not None:
            # Alias
            self._loaded_voices[voice_key] = existing_voice

            return existing_voice

        # https://onnxruntime.ai/docs/execution-providers/
        providers = None
        if self.settings.use_cuda:
            providers = ["CUDAExecutionProvider"]

        voice = Mimic3Voice.load_from_directory(
            model_dir,
            providers=providers,
            share_models=self.settings.share_onnx_models_between_threads,
            use_deterministic_compute=self.settings.use_deterministic_compute,
        )

        _LOGGER.info("Loaded voice from %s", model_dir)

        # Add to cache
        self._loaded_voices[voice_key] = voice
        self._loaded_voices[canonical_key] = voice

        return voice

    def _download_voice(self, voice_key: str) -> Path:
        """Downloads a voice by key"""
        voice_lang, voice_name = voice_key.split("/", maxsplit=1)
        voice_info = _VOICES[voice_key]
        voice_url = str.format(
            self.settings.voices_url_format or DEFAULT_VOICES_URL_FORMAT,
            key=voice_key,
            lang=voice_lang,
            name=voice_name,
        )
        voice_files = voice_info["files"]
        download_voice(
            voice_key=voice_key,
            url_base=voice_url,
            voice_files=[VoiceFile(file_key) for file_key in voice_files.keys()],
            voice_version=voice_info["version"],
            voices_dir=self.settings.voices_download_dir,
        )

        voice_dir = Path(self.settings.voices_download_dir) / voice_key

        return voice_dir
