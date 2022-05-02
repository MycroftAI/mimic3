from pathlib import Path

from opentts_abc import (
    AudioResult,
    BaseResult,
    BaseToken,
    MarkResult,
    Phonemes,
    SayAs,
    Voice,
    Word,
)
from opentts_abc.ssml import SSMLSpeaker

from ._resources import __version__
from .const import DEFAULT_VOICE
from .tts import Mimic3Settings, Mimic3TextToSpeechSystem

__author__ = "Michael Hansen"
