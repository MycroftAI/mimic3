#!/usr/bin/env python3
# Copyright 2022 Mycroft AI Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
import argparse
import asyncio
import dataclasses
import io
import logging
import sys
import tempfile
import typing
import wave
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qs
from uuid import uuid4

import hypercorn
import quart_cors
from mimic3_tts import AudioResult, Mimic3Settings, Mimic3TextToSpeechSystem
from quart import (
    Quart,
    Response,
    jsonify,
    render_template,
    request,
    send_from_directory,
)

_LOGGER = logging.getLogger(__name__)

_MISSING = object()
_TEMP_DIR: typing.Optional[Path] = None

_PACKAGE = "mimic3_http"
_DIR = Path(__file__).parent

# -----------------------------------------------------------------------------

parser = argparse.ArgumentParser(prog=_PACKAGE)
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
parser.add_argument("--speaker", type=int, help="Default speaker to use (name or id)")
parser.add_argument(
    "--length-scale", type=float, default=1.0, help="Speed of speech (> 1 is slower)"
)
parser.add_argument(
    "--noise-scale", type=float, default=0.333, help="Noise source for audio (0-1)"
)
parser.add_argument(
    "--noise-w", type=float, default=1.0, help="Variation in cadence (0-1)"
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
# parser.add_argument(
#     "--max-loaded-models",
#     type=int,
#     default=0,
#     help="Maximum number of voice models that can be loaded simultaneously (0 for no limit)",
# )
parser.add_argument(
    "--debug", action="store_true", help="Print DEBUG messages to console"
)
# parser.add_argument(
#     "--version", action="store_true", help="Print version to console and exit"
# )
args = parser.parse_args()

# if args.version:
#     print(__version__)
#     sys.exit(0)

if args.debug:
    logging.basicConfig(level=logging.DEBUG)
else:
    logging.basicConfig(level=logging.INFO)


_LOGGER.debug(args)


# -----------------------------------------------------------------------------


@dataclass(frozen=True)  # must be hashable
class TextToWavParams:
    text: str
    voice: str = args.voice
    noise_scale: float = args.noise_scale
    noise_w: float = args.noise_w
    length_scale: float = args.length_scale
    ssml: bool = False
    text_language: typing.Optional[str] = None


# params -> Path
_WAV_CACHE: typing.Dict[TextToWavParams, Path] = {}


# -----------------------------------------------------------------------------

# _TTS: typing.Dict[str, Mimic3] = {}
# _VOICE: str = args.voice


# TODO: XDG voice directories
# TODO: args.voices_dir

mimic3 = Mimic3TextToSpeechSystem(
    Mimic3Settings(
        voice=args.voice,
        speaker=args.speaker,
        length_scale=args.length_scale,
        noise_scale=args.noise_scale,
        noise_w=args.noise_w,
    )
)

if args.preload_voice:
    for voice_key in args.preload_voice:
        _LOGGER.debug("Preloading voice: %s", voice_key)
        mimic3.preload_voice(voice_key)


def text_to_wav(params: TextToWavParams, no_cache: bool = False) -> bytes:

    _LOGGER.debug(params)

    if _TEMP_DIR and (not no_cache):
        # Look up in cache
        maybe_wav_path = _TEMP_DIR / f"{hash(params)}.wav"
        if maybe_wav_path.is_file():
            _LOGGER.debug("Loading WAV from cache: %s", maybe_wav_path)
            wav_bytes = maybe_wav_path.read_bytes()
            return wav_bytes

    mimic3.voice = params.voice

    mimic3.settings.length_scale = params.length_scale
    mimic3.settings.noise_scale = params.noise_scale
    mimic3.settings.noise_w = params.noise_w

    with io.BytesIO() as wav_io:
        wav_file: wave.Wave_write = wave.open(wav_io, "wb")
        wav_params_set = False

        with wav_file:
            # TODO: SSML
            mimic3.begin_utterance()
            mimic3.speak_text(params.text, text_language=params.text_language)
            results = mimic3.end_utterance()

            for result in results:
                # TODO: Marks
                if isinstance(result, AudioResult):
                    if not wav_params_set:
                        wav_file.setframerate(result.sample_rate_hz)
                        wav_file.setsampwidth(result.sample_width_bytes)
                        wav_file.setnchannels(result.num_channels)
                        wav_params_set = True

                    wav_file.writeframes(result.audio_bytes)

        return wav_io.getvalue()


# -----------------------------------------------------------------------------

_TEMPLATES_DIR = _DIR / "templates"

app = Quart(_PACKAGE, template_folder=str(_TEMPLATES_DIR))
app.secret_key = str(uuid4())

if args.debug:
    app.config["TEMPLATES_AUTO_RELOAD"] = True

app = quart_cors.cors(app)


# -----------------------------------------------------------------------------

_CSS_DIR = _DIR / "css"
_IMG_DIR = _DIR / "img"


def _to_bool(s: str) -> bool:
    return s.strip().lower() in {"true", "1", "yes", "on"}


@app.route("/img/<path:filename>", methods=["GET"])
async def img(filename) -> Response:
    """Image static endpoint."""
    return await send_from_directory(_IMG_DIR, filename)


@app.route("/css/<path:filename>", methods=["GET"])
async def css(filename) -> Response:
    """CSS static endpoint."""
    return await send_from_directory(_CSS_DIR, filename)


@app.route("/")
async def app_index():
    """Main page."""
    return await render_template("index.html")


@app.route("/api/tts", methods=["GET", "POST"])
async def app_tts() -> Response:
    """Speak text to WAV."""
    tts_args: typing.Dict[str, typing.Any] = {}

    _LOGGER.debug(request.args)

    voice = request.args.get("voice")
    if voice is not None:
        tts_args["voice"] = str(voice)

    # TTS settings
    noise_scale = request.args.get("noiseScale")
    if noise_scale is not None:
        tts_args["noise_scale"] = float(noise_scale)

    noise_w = request.args.get("noiseW")
    if noise_w is not None:
        tts_args["noise_w"] = float(noise_w)

    length_scale = request.args.get("lengthScale")
    if length_scale is not None:
        tts_args["length_scale"] = float(length_scale)

    ssml_str = request.args.get("ssml")
    if ssml_str is not None:
        tts_args["ssml"] = _to_bool(ssml_str)

    text_language = request.args.get("textLanguage")
    if text_language is not None:
        tts_args["text_language"] = str(text_language)

    # Text can come from POST body or GET ?text arg
    if request.method == "POST":
        text = (await request.data).decode()
    else:
        text = request.args.get("text", "")

    assert text, "No text provided"

    # Cache settings
    no_cache_str = request.args.get("noCache", "")
    no_cache = _to_bool(no_cache_str)

    wav_bytes = text_to_wav(TextToWavParams(text=text, **tts_args), no_cache=no_cache)

    return Response(wav_bytes, mimetype="audio/wav")


@app.route("/api/voices", methods=["GET"])
async def api_voices():
    return jsonify([dataclasses.asdict(v) for v in mimic3.get_voices()])


@app.route("/process", methods=["GET", "POST"])
async def api_process():
    """MaryTTS-compatible /process endpoint"""
    voice = args.voice

    if request.method == "POST":
        data = parse_qs((await request.data).decode())
        text = data.get("INPUT_TEXT", [""])[0]

        if "VOICE" in data:
            voice = str(data.get("VOICE", [voice])[0]).strip()
    else:
        text = request.args.get("INPUT_TEXT", "")
        voice = str(request.args.get("VOICE", voice)).strip()

    voice = voice or args.voice

    # Assume SSML if text begins with an angle bracket
    ssml = text.strip().startswith("<")

    _LOGGER.debug("Speaking with voice '%s': %s", voice, text)
    wav_bytes = text_to_wav(
        TextToWavParams(
            text=text,
            voice=voice,
            ssml=ssml,
            length_scale=args.length_scale,
            noise_scale=args.noise_scale,
            noise_w=args.noise_w,
        )
    )

    return Response(wav_bytes, mimetype="audio/wav")


@app.errorhandler(Exception)
async def handle_error(err) -> typing.Tuple[str, int]:
    """Return error as text."""
    _LOGGER.exception(err)
    return (f"{err.__class__.__name__}: {err}", 500)


# -----------------------------------------------------------------------------
# Run Web Server
# -----------------------------------------------------------------------------

_LOGGER.info("Starting web server")

hyp_config = hypercorn.config.Config()
hyp_config.bind = [f"{args.host}:{args.port}"]

with mimic3, tempfile.TemporaryDirectory(prefix="mimic3") as temp_dir:
    if args.cache_dir != _MISSING:
        if args.cache_dir is None:
            # Use temporary directory
            _TEMP_DIR = Path(temp_dir)
        else:
            # Use user-supplied cache directory
            _TEMP_DIR = Path(args.cache_dir)
            _TEMP_DIR.mkdir(parents=True, exist_ok=True)

    if _TEMP_DIR:
        _LOGGER.debug("Cache directory: %s", _TEMP_DIR)

    asyncio.run(hypercorn.asyncio.serve(app, hyp_config))
