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
"""A command-line tool for downloading Mimic 3 voices"""
import argparse
import itertools
import json
import logging
import re
import sys
import typing
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from urllib.error import HTTPError

from ._resources import _PACKAGE, _VOICES
from .const import DEFAULT_VOICES_DOWNLOAD_DIR, DEFAULT_VOICES_URL_FORMAT
from .utils import WILDCARD, file_sha256_sum, wildcard_to_regex

_LOGGER = logging.getLogger(__name__)

# -----------------------------------------------------------------------------


class VoiceDownloadError(Exception):
    """Occurs when a voice fails to download"""


@dataclass
class VoiceFile:
    """File associated with a voice to download"""

    relative_path: str
    size_bytes: typing.Optional[int] = None
    sha256_sum: typing.Optional[str] = None


def is_later_version(version1: str, version2: str) -> bool:
    """True if version1 is later than version2"""
    v1_parts = [int(n) for n in version1.split(".")]
    v2_parts = [int(n) for n in version2.split(".")]

    for p1, p2 in itertools.zip_longest(v1_parts, v2_parts, fillvalue=0):
        if p1 > p2:
            # 2.0 vs 1.0
            return True

        if p1 < p2:
            # 1.0 vs 2.0
            return False

    # 1.0 vs 1.0
    return False


def download_voice(
    voice_key: str,
    url_base: str,
    voice_files: typing.Iterable[VoiceFile],
    voices_dir: typing.Union[str, Path],
    voice_version: str,
    chunk_bytes: int = 4096,
    redownload: bool = False,
):
    """Downloads a voice to a directory"""
    from tqdm.auto import tqdm

    if url_base.endswith("/"):
        # Remove final slash
        url_base = url_base[:-1]

    voice_dir = Path(voices_dir) / voice_key
    voice_dir.mkdir(parents=True, exist_ok=True)

    _LOGGER.debug("Downloading voice %s to %s", voice_key, voice_dir)

    version_path = voice_dir / "VERSION"
    if version_path.is_file():
        actual_version = version_path.read_text(encoding="utf-8").strip()
        if is_later_version(voice_version, actual_version):
            redownload = True
            _LOGGER.debug(
                "Replacing version %s of %s with version %s",
                actual_version,
                voice_key,
                voice_version,
            )

    for voice_file in voice_files:
        file_url = f"{url_base}/{voice_file.relative_path}"
        file_path = voice_dir / voice_file.relative_path
        file_path.parent.mkdir(parents=True, exist_ok=True)

        if (not redownload) and voice_file.sha256_sum and file_path.is_file():
            # Check if file exists and has correct sha256
            expected_sha256 = voice_file.sha256_sum

            with open(file_path, "rb") as check_file:
                actual_sha256 = file_sha256_sum(check_file)

            if actual_sha256 == expected_sha256:
                _LOGGER.debug("Skipping download of %s (sha256 match)", file_path)
                continue

        try:
            # Download file, show progress with tqdm
            with urllib.request.urlopen(file_url) as response:
                with open(file_path, mode="wb") as dest_file:
                    with tqdm(
                        unit="B",
                        unit_scale=True,
                        unit_divisor=1024,
                        miniters=1,
                        desc=voice_file.relative_path,
                        total=int(response.headers.get("content-length", 0)),
                    ) as pbar:
                        chunk = response.read(chunk_bytes)
                        while chunk:
                            dest_file.write(chunk)
                            pbar.update(len(chunk))
                            chunk = response.read(chunk_bytes)

            _LOGGER.debug("Downloaded %s", file_path)
        except HTTPError as e:
            _LOGGER.exception("download_voice")
            raise VoiceDownloadError(
                f"Failed to download file for voice {voice_key} from {file_url}: {e}"
            ) from e


# -----------------------------------------------------------------------------


def main(argv=None):
    """Main entry point"""
    parser = argparse.ArgumentParser(
        prog=f"{_PACKAGE}.download", description="Download utility for Mimic 3 voices"
    )
    parser.add_argument(
        "key",
        nargs="*",
        help="Keys of voices to download (e.g., en_US/vctk_low). May contain wildcards (*)",
    )
    parser.add_argument(
        "--output-dir",
        default=DEFAULT_VOICES_DOWNLOAD_DIR,
        help="Path to output directory",
    )
    parser.add_argument(
        "--url-format",
        default=DEFAULT_VOICES_URL_FORMAT,
        help="URL format string for voices (contains {key}, {lang}, {name})",
    )
    parser.add_argument(
        "--redownload",
        action="store_true",
        help="Force re-downloading of files if they already exist",
    )
    parser.add_argument(
        "--debug", action="store_true", help="Print DEBUG messages to console"
    )
    args = parser.parse_args(args=argv)

    if args.debug:
        logging.basicConfig(level=logging.DEBUG)
        logging.getLogger().setLevel(logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)
        logging.getLogger().setLevel(logging.INFO)

    _LOGGER.debug(args)

    args.output_dir = Path(args.output_dir)
    args.key = args.key or []

    if not args.key:
        # Print available voices and exit
        json.dump(_VOICES, sys.stdout, indent=4, ensure_ascii=False)
        sys.exit(0)

    args.key = [
        wildcard_to_regex(key, wildcard=WILDCARD) if WILDCARD in key else key
        for key in args.key
    ]

    args.output_dir.mkdir(parents=True, exist_ok=True)

    for key_or_pattern in args.key:
        if isinstance(key_or_pattern, re.Pattern):
            # Wildcards
            voice_keys = []
            for maybe_key in _VOICES.keys():
                if key_or_pattern.match(maybe_key):
                    voice_keys.append(maybe_key)

            _LOGGER.debug("%s matched %s", key_or_pattern, voice_keys)
        else:
            # No wildcards.
            # Resolve aliases.
            for maybe_key, maybe_info in _VOICES.items():
                for alias in maybe_info.get("aliases", []):
                    if key_or_pattern == alias:
                        # Alias match
                        key_or_pattern = maybe_key
                        break

            voice_keys = [key_or_pattern]

        for voice_key in voice_keys:
            if "/" not in voice_key:
                _LOGGER.error(
                    "Voice not recognized or not in <lang>/<name> format: %s", voice_key
                )
                continue

            voice_lang, voice_name = voice_key.split("/", maxsplit=1)
            voice_info = _VOICES[voice_key]
            voice_url = str.format(
                args.url_format, key=voice_key, lang=voice_lang, name=voice_name
            )
            voice_files = voice_info["files"]

            _LOGGER.info("Downloading %s", voice_key)
            download_voice(
                voice_key=voice_key,
                url_base=voice_url,
                voice_files=[
                    VoiceFile(file_key, sha256_sum=file_info.get("sha256_sum"))
                    for file_key, file_info in voice_files.items()
                ],
                voice_version=voice_info["version"],
                voices_dir=args.output_dir,
                redownload=args.redownload,
            )


# -----------------------------------------------------------------------------

if __name__ == "__main__":
    main()
