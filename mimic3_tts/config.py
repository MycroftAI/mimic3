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
"""Configuration classes"""
import collections
import json
import typing
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

import numpy as np
from dataclasses_json import DataClassJsonMixin
from gruut_ipa import IPA
from phonemes2ids import BlankBetween


@dataclass
class AudioConfig(DataClassJsonMixin):
    """Audio input/output details"""

    filter_length: int = 1024
    hop_length: int = 256
    win_length: int = 1024
    mel_channels: int = 80
    sample_rate: int = 22050
    sample_bytes: int = 2
    channels: int = 1
    mel_fmin: float = 0.0
    mel_fmax: typing.Optional[float] = None
    ref_level_db: float = 20.0
    spec_gain: float = 1.0

    # Normalization
    signal_norm: bool = True
    min_level_db: float = -100.0
    max_norm: float = 1.0
    clip_norm: bool = True
    symmetric_norm: bool = True
    do_dynamic_range_compression: bool = True
    convert_db_to_amp: bool = True

    do_trim_silence: bool = False
    trim_silence_db: float = 40.0
    trim_margin_sec: float = 0.01
    trim_keep_sec: float = 0.25

    scale_mels: bool = False

    def __post_init__(self):
        if self.mel_fmax is not None:
            assert self.mel_fmax <= self.sample_rate // 2

    # -------------------------------------------------------------------------
    # Normalization
    # -------------------------------------------------------------------------

    def normalize(self, mel_db: np.ndarray) -> np.ndarray:
        """Put values in [0, max_norm] or [-max_norm, max_norm]"""
        mel_norm = ((mel_db - self.ref_level_db) - self.min_level_db) / (
            -self.min_level_db
        )
        if self.symmetric_norm:
            # Symmetric norm
            mel_norm = ((2 * self.max_norm) * mel_norm) - self.max_norm
            if self.clip_norm:
                mel_norm = np.clip(mel_norm, -self.max_norm, self.max_norm)
        else:
            # Asymmetric norm
            mel_norm = self.max_norm * mel_norm
            if self.clip_norm:
                mel_norm = np.clip(mel_norm, 0, self.max_norm)

        return mel_norm

    def denormalize(self, mel_db: np.ndarray) -> np.ndarray:
        """Pull values out of [0, max_norm] or [-max_norm, max_norm]"""
        if self.symmetric_norm:
            # Symmetric norm
            if self.clip_norm:
                mel_denorm = np.clip(mel_db, -self.max_norm, self.max_norm)

            mel_denorm = (
                (mel_denorm + self.max_norm) * -self.min_level_db / (2 * self.max_norm)
            ) + self.min_level_db
        else:
            # Asymmetric norm
            if self.clip_norm:
                mel_denorm = np.clip(mel_db, 0, self.max_norm)

            mel_denorm = (
                mel_denorm * -self.min_level_db / self.max_norm
            ) + self.min_level_db

        mel_denorm += self.ref_level_db

        return mel_denorm


@dataclass
class ModelConfig(DataClassJsonMixin):
    """TTS model hyperparameters"""

    num_symbols: int = 0
    n_speakers: int = 1

    inter_channels: int = 192
    hidden_channels: int = 192
    filter_channels: int = 768
    n_heads: int = 2
    n_layers: int = 6
    kernel_size: int = 3
    p_dropout: float = 0.1
    resblock: str = "1"
    resblock_kernel_sizes: typing.Tuple[int, ...] = (3, 7, 11)
    resblock_dilation_sizes: typing.Tuple[typing.Tuple[int, ...], ...] = (
        (1, 3, 5),
        (1, 3, 5),
        (1, 3, 5),
    )
    upsample_rates: typing.Tuple[int, ...] = (8, 8, 2, 2)
    upsample_initial_channel: int = 512
    upsample_kernel_sizes: typing.Tuple[int, ...] = (16, 16, 4, 4)
    n_layers_q: int = 3
    use_spectral_norm: bool = False
    gin_channels: int = 0  # single speaker
    use_sdp: bool = True  # StochasticDurationPredictor

    @property
    def is_multispeaker(self) -> bool:
        return self.n_speakers > 1


@dataclass
class PhonemesConfig(DataClassJsonMixin):
    """Phonemes to ids configuration"""

    phoneme_separator: str = " "
    """Separator between individual phonemes in CSV input"""

    word_separator: str = "#"
    """Separator between word phonemes in CSV input (must not match phoneme_separator)"""

    phoneme_to_id: typing.Optional[typing.Dict[str, int]] = None
    pad: typing.Optional[str] = "_"
    bos: typing.Optional[str] = None
    eos: typing.Optional[str] = None
    blank: typing.Optional[str] = "#"
    blank_word: typing.Optional[str] = None
    blank_between: typing.Union[str, BlankBetween] = BlankBetween.WORDS
    blank_at_start: bool = True
    blank_at_end: bool = True
    simple_punctuation: bool = True
    punctuation_map: typing.Optional[typing.Dict[str, str]] = None
    separate: typing.Optional[typing.List[str]] = None
    separate_graphemes: bool = False
    separate_tones: bool = False
    tone_before: bool = False
    phoneme_map: typing.Optional[typing.Dict[str, str]] = None
    auto_bos_eos: bool = False
    minor_break: typing.Optional[str] = IPA.BREAK_MINOR.value
    major_break: typing.Optional[str] = IPA.BREAK_MAJOR.value
    break_phonemes_into_graphemes: bool = False
    break_phonemes_into_codepoints: bool = False
    drop_stress: bool = False
    symbols: typing.Optional[typing.List[str]] = None

    def split_word_phonemes(self, phonemes_str: str) -> typing.List[typing.List[str]]:
        """Split phonemes string into a list of lists (outer is words, inner is individual phonemes in each word)"""
        return [
            word_phonemes_str.split(self.phoneme_separator)
            for word_phonemes_str in phonemes_str.split(self.word_separator)
        ]

    def join_word_phonemes(self, word_phonemes: typing.List[typing.List[str]]) -> str:
        """Split phonemes string into a list of lists (outer is words, inner is individual phonemes in each word)"""
        return self.word_separator.join(
            self.phoneme_separator.join(wp) for wp in word_phonemes
        )


class Phonemizer(str, Enum):
    """Method used to convert text to phonemes"""

    SYMBOLS = "symbols"
    GRUUT = "gruut"
    ESPEAK = "espeak"
    EPITRAN = "epitran"


class Aligner(str, Enum):
    """Text/audio aligner"""

    KALDI_ALIGN = "kaldi_align"
    """https://github.com/rhasspy/kaldi-align"""


class TextCasing(str, Enum):
    """Casing method applied to text"""

    LOWER = "lower"
    UPPER = "upper"


class MetadataFormat(str, Enum):
    """Format of training metadata"""

    TEXT = "text"
    PHONEMES = "phonemes"
    PHONEME_IDS = "ids"


@dataclass
class DatasetConfig:
    """Training dataset configuration"""

    name: str
    metadata_format: MetadataFormat = MetadataFormat.TEXT
    multispeaker: bool = False
    text_language: typing.Optional[str] = None
    audio_dir: typing.Optional[typing.Union[str, Path]] = None
    cache_dir: typing.Optional[typing.Union[str, Path]] = None

    def get_cache_dir(self, output_dir: typing.Union[str, Path]) -> Path:
        if self.cache_dir is not None:
            cache_dir = Path(self.cache_dir)
        else:
            cache_dir = Path("cache") / self.name

        if not cache_dir.is_absolute():
            cache_dir = Path(output_dir) / str(cache_dir)

        return cache_dir


@dataclass
class AlignerConfig:
    """Text/audio alignment configuration"""

    aligner: typing.Optional[Aligner] = None
    casing: typing.Optional[TextCasing] = None


@dataclass
class InferenceConfig:
    """Inference configuration"""

    length_scale: float = 1.0
    noise_scale: float = 0.667
    noise_w: float = 0.8

    minor_break_ms: typing.Optional[int] = None
    """Automatically add milliseconds of silence after a minor break (comma)"""

    major_break_ms: typing.Optional[int] = None
    """Automatically add milliseconds of silence after a major break (period)"""

    auto_append_text: typing.Optional[str] = None
    """Automatically append text to the end of an utterance if not present (e.g., punctuation)"""


@dataclass
class TrainingConfig(DataClassJsonMixin):
    """Master configuration for training"""

    seed: int = 1234
    epochs: int = 10000
    learning_rate: float = 2e-4
    betas: typing.Tuple[float, float] = field(default=(0.8, 0.99))
    eps: float = 1e-9
    batch_size: int = 32
    fp16_run: bool = False
    lr_decay: float = 0.999875
    segment_size: int = 8192
    init_lr_ratio: float = 1.0
    warmup_epochs: int = 0
    c_mel: int = 45
    c_kl: float = 1.0
    grad_clip: typing.Optional[float] = None

    min_seq_length: typing.Optional[int] = None
    max_seq_length: typing.Optional[int] = None

    min_spec_length: typing.Optional[int] = None
    max_spec_length: typing.Optional[int] = None

    min_speaker_utterances: typing.Optional[int] = None

    last_epoch: int = 1
    global_step: int = 1
    best_loss: typing.Optional[float] = None
    audio: AudioConfig = field(default_factory=AudioConfig)
    model: ModelConfig = field(default_factory=ModelConfig)
    phonemes: PhonemesConfig = field(default_factory=PhonemesConfig)
    text_aligner: AlignerConfig = field(default_factory=AlignerConfig)
    text_language: typing.Optional[str] = None
    phonemizer: typing.Optional[Phonemizer] = None
    datasets: typing.List[DatasetConfig] = field(default_factory=list)
    inference: InferenceConfig = field(default_factory=InferenceConfig)

    version: int = 1
    git_commit: str = ""

    @property
    def is_multispeaker(self):
        return self.model.is_multispeaker or any(d.multispeaker for d in self.datasets)

    def save(self, config_file: typing.TextIO):
        """Save config as JSON to a file"""
        json.dump(self.to_dict(), config_file, indent=4)

    @staticmethod
    def load(config_file: typing.TextIO) -> "TrainingConfig":
        """Load config from a JSON file"""
        return TrainingConfig.from_json(config_file.read())

    @staticmethod
    def load_and_merge(
        config: "TrainingConfig",
        config_files: typing.Iterable[typing.Union[str, Path, typing.TextIO]],
    ) -> "TrainingConfig":
        """Loads one or more JSON configuration files and overlays them on top of an existing config"""
        base_dict = config.to_dict()
        for maybe_config_file in config_files:
            if isinstance(maybe_config_file, (str, Path)):
                # File path
                config_file = open(maybe_config_file, "r", encoding="utf-8")
            else:
                # File object
                config_file = maybe_config_file

            with config_file:
                # Load new config and overlay on existing config
                new_dict = json.load(config_file)
                TrainingConfig.recursive_update(base_dict, new_dict)

        return TrainingConfig.from_dict(base_dict)

    @staticmethod
    def recursive_update(
        base_dict: typing.Dict[typing.Any, typing.Any],
        new_dict: typing.Mapping[typing.Any, typing.Any],
    ) -> None:
        """Recursively overwrites values in base dictionary with values from new dictionary"""
        for key, value in new_dict.items():
            if isinstance(value, collections.Mapping) and (
                base_dict.get(key) is not None
            ):
                TrainingConfig.recursive_update(base_dict[key], value)
            else:
                base_dict[key] = value
