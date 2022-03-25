from pathlib import Path

from opentts_abc import AudioResult, MarkResult
from opentts_abc.ssml import SSMLSpeaker

from ._resources import __version__
from .tts import Mimic3Settings, Mimic3TextToSpeechSystem

__author__ = "Michael Hansen"
