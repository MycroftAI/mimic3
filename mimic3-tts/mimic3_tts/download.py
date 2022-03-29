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
import argparse
import json
import logging
import sys
import typing
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from urllib.error import HTTPError

from ._resources import _PACKAGE, _VOICES
from .const import DEFAULT_VOICES_DOWNLOAD_DIR, DEFAULT_VOICES_URL_FORMAT

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


def download_voice(
    voice_key: str,
    url_base: str,
    voice_files: typing.Iterable[VoiceFile],
    voices_dir: typing.Union[str, Path],
    chunk_bytes: int = 4096,
):
    """Downloads a voice to a directory"""
    from tqdm.auto import tqdm

    if url_base.endswith("/"):
        # Remove final slash
        url_base = url_base[:-1]

    voice_dir = Path(voices_dir) / voice_key
    voice_dir.mkdir(parents=True, exist_ok=True)

    _LOGGER.debug("Downloading voice %s to %s", voice_key, voice_dir)

    for voice_file in voice_files:
        file_url = f"{url_base}/{voice_file.relative_path}"
        file_path = voice_dir / voice_file.relative_path

        try:
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


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(prog=f"{_PACKAGE}.download")
    parser.add_argument(
        "key",
        nargs="*",
        help="Keys of voices to download (e.g., en_US/vctk_low)",
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
        "--debug", action="store_true", help="Print DEBUG messages to console"
    )
    args = parser.parse_args()

    if args.debug:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)

    _LOGGER.debug(args)

    args.output_dir = Path(args.output_dir)
    args.key = args.key or []

    if not args.key:
        # Print available voices and exit
        json.dump(_VOICES, sys.stdout, indent=4, ensure_ascii=False)
        sys.exit(0)

    args.output_dir.mkdir(parents=True, exist_ok=True)

    for voice_key in args.key:
        voice_lang, voice_name = voice_key.split("/", maxsplit=1)
        voice_info = _VOICES[voice_key]
        voice_url = str.format(
            args.url_format, key=voice_key, lang=voice_lang, name=voice_name
        )
        voice_files = voice_info["files"]
        download_voice(
            voice_key=voice_key,
            url_base=voice_url,
            voice_files=[VoiceFile(file_key) for file_key in voice_files.keys()],
            voices_dir=args.output_dir,
        )


# -----------------------------------------------------------------------------

if __name__ == "__main__":
    main()
