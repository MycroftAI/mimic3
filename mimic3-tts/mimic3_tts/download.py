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
import shutil
import sys
import tempfile
import typing
import urllib.request
from pathlib import Path
from urllib.error import HTTPError

from xdgenvpy import XDG

from ._resources import _DIR, _PACKAGE

_LOGGER = logging.getLogger(__name__)

# -----------------------------------------------------------------------------


class VoiceDownloadError(Exception):
    """Occurs when a voice fails to download"""


def download_voice(voices_dir: typing.Union[str, Path], link: str) -> Path:
    """Download and extract a voice (or vocoder)"""
    from tqdm.auto import tqdm

    voice_name = link.split("/")[-1]
    voices_dir = Path(voices_dir)
    voices_dir.mkdir(parents=True, exist_ok=True)

    _LOGGER.debug("Downloading voice to %s from %s", voices_dir, link)

    try:
        with urllib.request.urlopen(link) as response:
            with tempfile.NamedTemporaryFile(mode="wb+", suffix=".tar.gz") as temp_file:
                with tqdm(
                    unit="B",
                    unit_scale=True,
                    unit_divisor=1024,
                    miniters=1,
                    desc=voice_name,
                    total=int(response.headers.get("content-length", 0)),
                ) as pbar:
                    chunk = response.read(4096)
                    while chunk:
                        temp_file.write(chunk)
                        pbar.update(len(chunk))
                        chunk = response.read(4096)

                temp_file.seek(0)

                # Extract
                with tempfile.TemporaryDirectory() as temp_dir_str:
                    temp_dir = Path(temp_dir_str)
                    _LOGGER.debug("Extracting %s to %s", temp_file.name, temp_dir_str)
                    shutil.unpack_archive(temp_file.name, temp_dir_str)

                    # Expecting <language>/<voice_name>
                    lang_dir = next(temp_dir.iterdir())
                    assert lang_dir.is_dir()

                    voice_dir = next(lang_dir.iterdir())
                    assert voice_dir.is_dir()

                    # Copy to destination
                    dest_lang_dir = voices_dir / lang_dir.name
                    dest_lang_dir.mkdir(parents=True, exist_ok=True)

                    dest_voice_dir = voices_dir / lang_dir.name / voice_dir.name
                    if dest_voice_dir.is_dir():
                        # Delete existing files
                        shutil.rmtree(str(dest_voice_dir))

                    # Move files
                    _LOGGER.debug("Moving %s to %s", voice_dir, dest_voice_dir)
                    shutil.move(str(voice_dir), str(dest_voice_dir))

                    _LOGGER.info("Installed %s to %s", link, dest_voice_dir)

                    return dest_voice_dir
    except HTTPError as e:
        _LOGGER.exception("download_voice")
        raise VoiceDownloadError(
            f"Failed to download voice {voice_name} from {link}: {e}"
        ) from e


# -----------------------------------------------------------------------------


def main():
    """Main entry point"""
    default_voices_dir = Path(XDG().XDG_DATA_HOME) / "mimic3"

    parser = argparse.ArgumentParser(prog=f"{_PACKAGE}.download")
    parser.add_argument("--url", action="append", help="URL of voice to download")
    parser.add_argument(
        "--name",
        action="append",
        help="Name of voice to download (e.g., en_US/vctk_low)",
    )
    parser.add_argument(
        "--output-dir",
        default=default_voices_dir,
        help=f"Path to output directory (default: {default_voices_dir})",
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
    args.url = args.url or []
    args.name = args.name or []

    with open(_DIR / "voices.json", "r", encoding="utf-8") as voices_file:
        voices_by_name = json.load(voices_file)

    if (not args.url) and (not args.name):
        # Print available voices and exit
        json.dump(voices_by_name, sys.stdout, indent=4, ensure_ascii=False)
        sys.exit(0)

    urls_to_download = args.url

    if args.name:
        # Gather URLs for voices by name

        for voice_name in args.name:
            voice_info = voices_by_name.get(voice_name)
            if not voice_info:
                _LOGGER.fatal("Voice not found: %s", voice_name)
                sys.exit(1)

            urls_to_download.append(voice_info["url"])

    args.output_dir.mkdir(parents=True, exist_ok=True)

    for url in urls_to_download:
        download_voice(args.output_dir, url)


# -----------------------------------------------------------------------------

if __name__ == "__main__":
    main()
