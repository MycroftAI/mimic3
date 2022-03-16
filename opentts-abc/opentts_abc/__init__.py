#!/usr/bin/env python3
"""Base classes for Open Text to Speech systems"""
import dataclasses
import io
import typing
import wave
from abc import ABCMeta, abstractmethod
from contextlib import AbstractContextManager
from copy import deepcopy
from dataclasses import dataclass


@dataclass
class Settings:
    voice: typing.Optional[str] = None
    language: typing.Optional[str] = None
    volume: typing.Optional[float] = None
    rate: typing.Optional[float] = None
    pitch: typing.Optional[float] = None
    active_lexicons: typing.Optional[typing.Sequence[str]] = None
    other_settings: typing.Optional[typing.Mapping[str, typing.Any]] = None


@dataclass
class BaseToken(metaclass=ABCMeta):
    text: str


@dataclass
class Word(BaseToken):
    role: typing.Optional[str] = None


@dataclass
class Phonemes(BaseToken):
    alphabet: typing.Optional[str] = None


@dataclass
class SayAs(BaseToken):
    interpret_as: str
    format: typing.Optional[str] = None


@dataclass
class _BaseResultDefaults:
    tag: typing.Optional[typing.Any] = None


@dataclass
class BaseResult(metaclass=ABCMeta):
    pass


@dataclass
class _AudioResultBase:
    sample_rate_hz: int
    sample_width_bytes: int
    num_channels: int
    audio_bytes: bytes


@dataclass
class AudioResult(BaseResult, _BaseResultDefaults, _AudioResultBase):
    def to_wav_bytes(self) -> bytes:
        with io.BytesIO() as wav_io:
            wav_file: wave.Wave_write = wave.open(wav_io, "wb")
            with wav_file:
                wav_file.setframerate(self.sample_rate_hz)
                wav_file.setsampwidth(self.sample_width_bytes)
                wav_file.setnchannels(self.num_channels)
                wav_file.writeframes(self.audio_bytes)

            return wav_io.getvalue()


@dataclass
class _MarkResultBase:
    name: str


@dataclass
class MarkResult(BaseResult, _BaseResultDefaults, _MarkResultBase):
    pass


@dataclass
class Voice:
    key: str
    name: str
    language: str
    description: str
    properties: typing.Optional[typing.Mapping[str, typing.Any]] = None


# @dataclass
# class LexiconEntry:
#     word: str
#     pronunciation: str
#     role: typing.Optional[str] = None


# @dataclass
# class Lexicon:
#     name: str
#     entries: typing.Mapping[str, typing.Sequence[LexiconEntry]]


class TextToSpeechSystem(AbstractContextManager, metaclass=ABCMeta):
    """Abstract base class for open text to speech systems"""

    @property
    @abstractmethod
    def voice(self) -> str:
        pass

    @voice.setter
    def voice(self, new_voice: str):
        pass

    @property
    @abstractmethod
    def language(self) -> str:
        pass

    @language.setter
    def language(self, new_language: str):
        pass

    def shutdown(self):
        pass

    def __exit__(self, exc_type, exc_value, traceback):
        self.shutdown()

    @abstractmethod
    def get_voices(self) -> typing.Iterable[Voice]:
        pass

    @abstractmethod
    def begin_utterance(self):
        pass

    @abstractmethod
    def speak_text(self, text: str):
        pass

    @abstractmethod
    def speak_tokens(self, tokens: typing.Iterable[BaseToken]):
        pass

    @abstractmethod
    def add_break(self, time_ms: int):
        pass

    @abstractmethod
    def set_mark(self, name: str):
        pass

    @abstractmethod
    def end_utterance(self) -> typing.Iterable[BaseResult]:
        pass
