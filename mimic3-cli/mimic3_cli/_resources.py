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
"""Shared access to package resources"""
import os
import typing
from pathlib import Path

try:
    import importlib.resources

    files = importlib.resources.files
except (ImportError, AttributeError):
    # Backport for Python < 3.9
    import importlib_resources  # type: ignore

    files = importlib_resources.files

_PACKAGE = "mimic3_http"
_DIR = Path(typing.cast(os.PathLike, files(_PACKAGE)))

__version__ = (_DIR / "VERSION").read_text(encoding="utf-8").strip()
