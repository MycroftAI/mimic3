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
"""Utility methods for Mimic 3"""
import hashlib
import re
import typing
import unicodedata

import numpy as np

WILDCARD = "*"

LANG_NAMES = {
    "bn": ("বাংলা", "Bengali"),
    "af_ZA": "Afrikaans",
    "da_DK": ("Dansk", "Danish"),
    "de_DE": ("Deutsch", "German"),
    "en_UK": "English (UK)",
    "en_US": "English (US)",
    "el_GR": ("Ελληνικά", "Greek"),
    "es_ES": ("Español", "Spanish"),
    "fa": ("فارسی", "Persian"),
    "fi_FI": ("Suomi", "Finnish"),
    "fr_FR": ("Français", "French"),
    "gu_IN": ("ગુજરાતી", "Gujarati"),
    "ha_NE": "Hausa",
    "hu_HU": ("Magyar Nyelv", "Hungarian"),
    "it_IT": ("Italiano", "Italian"),
    "jv_ID": ("Basa Jawa", "Javanese"),
    "ko_KO": ("한국어", "Korean"),
    "ne_NP": ("नेपाली", "Nepali"),
    "nl": ("Nederlands", "Dutch"),
    "pl_PL": ("Polski", "Polish"),
    "ru_RU": ("Русский", "Russian"),
    "sw": "Kiswahili",
    "te_IN": ("తెలుగు", "Telugu"),
    "tn_ZA": "Setswana",
    "uk_UK": ("украї́нська мо́ва", "Ukrainian"),
    "vi_VN": ("Tiếng Việt", "Vietnamese"),
    "yo": ("Èdè Yorùbá", "Yoruba"),
}


def audio_float_to_int16(
    audio: np.ndarray, max_wav_value: float = 32767.0
) -> np.ndarray:
    """Normalize audio and convert to int16 range"""
    audio_norm = audio * (max_wav_value / max(0.01, np.max(np.abs(audio))))
    audio_norm = np.clip(audio_norm, -max_wav_value, max_wav_value)
    audio_norm = audio_norm.astype("int16")
    return audio_norm


def wildcard_to_regex(template: str, wildcard: str = "*") -> re.Pattern:
    """Convert a string with wildcards into a regex pattern"""
    wildcard_escaped = re.escape(wildcard)

    pattern_parts = ["^"]
    for i, template_part in enumerate(re.split(f"({wildcard_escaped})", template)):
        if (i % 2) == 0:
            # Fixed string
            pattern_parts.append(re.escape(template_part))
        else:
            # Wildcard separator
            pattern_parts.append(".*")

    pattern_parts.append("$")
    pattern_str = "".join(pattern_parts)

    return re.compile(pattern_str)


def file_sha256_sum(fp: typing.BinaryIO, block_bytes: int = 4096) -> str:
    """Return the sha256 sum of a (possibly large) file"""
    current_hash = hashlib.sha256()

    # Read in blocks in case file is very large
    block = fp.read(block_bytes)
    while len(block) > 0:
        current_hash.update(block)
        block = fp.read(block_bytes)

    return current_hash.hexdigest()


def to_codepoints(s: str) -> typing.List[str]:
    """Split string into a list of codepoints"""
    return list(unicodedata.normalize("NFC", s))
