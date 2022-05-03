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
from pathlib import Path

from xdgenvpy import XDG

DEFAULT_VOICE = "en_UK/apope_low"
DEFAULT_LANGUAGE = "en_UK"
DEFAULT_VOICES_URL_FORMAT = (
    "https://github.com/MycroftAI/mimic3-voices/raw/master/voices/{lang}/{name}"
)
DEFAULT_VOICES_DOWNLOAD_DIR = (
    Path(XDG().XDG_DATA_HOME) / "mycroft" / "mimic3" / "voices"
)

DEFAULT_VOLUME = 100.0
DEFAULT_RATE = 1.0
