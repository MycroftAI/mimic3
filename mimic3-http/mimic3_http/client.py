#!/usr/bin/env python3
import argparse
import logging
import os
import sys
import tempfile
import typing
from pathlib import Path

import requests

_PACKAGE = "mimic3_http.client"

_LOGGER = logging.getLogger(_PACKAGE)

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
        from playsound import playsound

        with tempfile.NamedTemporaryFile(mode="wb+", suffix=".wav") as wav_file:
            wav_file.write(wav_bytes)
            wav_file.seek(0)

            _LOGGER.debug("Playing WAV file: %s", wav_file.name)
            playsound(wav_file.name)


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
        "--voice",
        "-v",
        help="Name of voice (expected in <voices-dir>/<language>)",
    )
    parser.add_argument(
        "--output",
        "-o",
        help="Path to write WAV file (default: play audio)",
    )
    parser.add_argument(
        "--stdout",
        action="store_true",
        help="Write WAV data to stdout",
    )
    parser.add_argument(
        "--noise-scale",
        type=float,
        help="Noise scale [0-1], default is 0.667",
    )
    parser.add_argument(
        "--length-scale",
        type=float,
        help="Length scale (1.0 is default speed, 0.5 is 2x faster)",
    )
    parser.add_argument(
        "--noise-w",
        type=float,
        help="Variation in cadence [0-1], default is 0.8",
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
