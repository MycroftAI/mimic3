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
import sys

from ._resources import _PACKAGE, __version__

_MISSING = object()


def get_args(argv=None) -> argparse.Namespace:
    """Parse and return command-line arguments"""
    parser = argparse.ArgumentParser(
        prog=_PACKAGE, description="Local HTTP web server for Mimic 3"
    )
    parser.add_argument(
        "--voices-dir",
        action="append",
        help="Directory with <language>/<voice> structure",
    )
    parser.add_argument("--voice", help="Default voice (name of model directory)")
    parser.add_argument(
        "--host", default="0.0.0.0", help="Host of HTTP server (default: 0.0.0.0)"
    )
    parser.add_argument(
        "--port", type=int, default=59125, help="Port of HTTP server (default: 59125)"
    )
    parser.add_argument(
        "--speaker", type=int, help="Default speaker to use (name or id)"
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
    parser.add_argument(
        "--cache-dir",
        nargs="?",
        default=_MISSING,
        help="Enable WAV cache with optional directory (default: no cache)",
    )
    parser.add_argument(
        "--preload-voice", action="append", help="Preload voice when starting up"
    )
    parser.add_argument(
        "--cuda",
        action="store_true",
        help="Use Onnx CUDA execution provider (requires onnxruntime-gpu)",
    )
    parser.add_argument(
        "--deterministic",
        action="store_true",
        help="Ensure that the same audio is always synthesized from the same text",
    )
    parser.add_argument(
        "--num-threads",
        type=int,
        default=1,
        help="Number of synthesis threads (default: 1)",
    )
    parser.add_argument(
        "--max-text-length",
        type=int,
        help="Maximum length of input text to process (default: no limit)",
    )
    parser.add_argument(
        "--default-voice",
        help="Default voice key to select in web interface",
    )
    parser.add_argument(
        "--play-program", default="aplay -q", help="Program to play WAV audio on server"
    )
    parser.add_argument(
        "--no-show-openapi", action="store_true", help="Don't show OpenAPI link"
    )
    parser.add_argument(
        "--debug", action="store_true", help="Print DEBUG messages to console"
    )
    parser.add_argument(
        "--version", action="store_true", help="Print version to console and exit"
    )
    args = parser.parse_args(args=argv)

    if args.version:
        print(__version__)
        sys.exit(0)

    return args
