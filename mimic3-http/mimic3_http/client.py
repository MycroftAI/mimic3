#!/usr/bin/env python3
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
import subprocess
import shlex
import shutil
import logging
import os
import sys
import tempfile
import typing
from pathlib import Path

import requests

_PACKAGE = "mimic3_http.client"

_LOGGER = logging.getLogger(_PACKAGE)

_DEFAULT_PLAY_PROGRAMS = ["paplay", "play -q", "aplay -q"]

# -----------------------------------------------------------------------------


def main():
    args = get_args()

    if args.output:
        args.output = Path(args.output)
        args.output.parent.mkdir(parents=True, exist_ok=True)

    if args.ssml:
        headers = {"Content-Type": "application/ssml+xml"}
    else:
        headers = {"Content-Type": "text/plain"}

    params: typing.Dict[str, str] = {}

    if args.voice:
        params["voice"] = args.voice

    if args.length_scale:
        params["lengthScale"] = args.length_scale

    if args.noise_scale:
        params["noiseScale"] = args.noise_scale

    if args.noise_w:
        params["noiseW"] = args.noise_w

    if args.text:
        data = "\n".join(args.text)
    else:
        if os.isatty(sys.stdin.fileno()):
            print("Reading text from stdin...", file=sys.stderr)

        data = sys.stdin.read()

    wav_bytes = requests.post(
        args.url, headers=headers, params=params, data=data
    ).content

    if args.output:
        args.output.write_bytes(wav_bytes)
        _LOGGER.info("Wrote WAV data to %s", args.output)
    elif args.stdout:
        _LOGGER.debug("Writing WAV data to stdout")
        sys.stdout.buffer.write(wav_bytes)
    else:
        play_wav_bytes(args, wav_bytes)


# -----------------------------------------------------------------------------


def play_wav_bytes(args: argparse.Namespace, wav_bytes: bytes):
    with tempfile.NamedTemporaryFile(mode="wb+", suffix=".wav") as wav_file:
        wav_file.write(wav_bytes)
        wav_file.seek(0)

        for play_program in reversed(args.play_program):
            play_cmd = shlex.split(play_program)
            if not shutil.which(play_cmd[0]):
                continue

            play_cmd.append(wav_file.name)
            _LOGGER.debug("Playing WAV file: %s", play_cmd)
            subprocess.check_output(play_cmd)
            break


# -----------------------------------------------------------------------------


def get_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog=_PACKAGE)
    parser.add_argument(
        "text", nargs="*", help="Text to convert to speech (default: stdin)"
    )
    parser.add_argument(
        "--url",
        "-u",
        default="http://localhost:59125/api/tts",
        help="URL of mimic3 HTTP server (default: http://localhost:59125/api/tts)",
    )
    parser.add_argument(
        "--voice", "-v", help="Name of voice (expected in <voices-dir>/<language>)",
    )
    parser.add_argument(
        "--output", "-o", help="Path to write WAV file (default: play audio)",
    )
    parser.add_argument(
        "--stdout", action="store_true", help="Write WAV data to stdout",
    )
    parser.add_argument(
        "--noise-scale", type=float, help="Noise scale [0-1], default is 0.667",
    )
    parser.add_argument(
        "--length-scale",
        type=float,
        help="Length scale (1.0 is default speed, 0.5 is 2x faster)",
    )
    parser.add_argument(
        "--noise-w", type=float, help="Variation in cadence [0-1], default is 0.8",
    )
    parser.add_argument(
        "--play-program",
        action="append",
        default=_DEFAULT_PLAY_PROGRAMS,
        help="Program(s) used to play WAV files",
    )
    parser.add_argument("--ssml", action="store_true", help="Input text is SSML")
    parser.add_argument(
        "--debug", action="store_true", help="Print DEBUG messages to the console"
    )
    args = parser.parse_args()

    if args.debug:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)

    return args


# -----------------------------------------------------------------------------

if __name__ == "__main__":
    main()
