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
import asyncio
import hashlib
import typing
from dataclasses import dataclass


@dataclass
class TextToWavParams:
    """Synthesis parameters used for caching"""

    text: str
    voice: str
    noise_scale: float
    noise_w: float
    length_scale: float
    ssml: bool = False
    text_language: typing.Optional[str] = None
    cache_id: typing.Optional[str] = None

    @property
    def cache_key(self) -> str:
        if self.cache_id:
            return self.cache_id

        return hashlib.md5(repr(self).encode()).hexdigest()


@dataclass
class SynthesisRequest:
    """Request to synthesize audio from text"""

    params: TextToWavParams

    loop: asyncio.AbstractEventLoop
    future: asyncio.Future
