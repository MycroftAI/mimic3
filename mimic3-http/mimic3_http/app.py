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
import dataclasses
import hashlib
import io
import logging
import typing
import wave
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qs
from uuid import uuid4

import quart_cors
from mimic3_tts import AudioResult, Mimic3TextToSpeechSystem, SSMLSpeaker
from quart import (
    Quart,
    Response,
    jsonify,
    render_template,
    request,
    send_from_directory,
)

from ._resources import _DIR, _PACKAGE
from .args import _MISSING

_LOGGER = logging.getLogger(__name__)


def get_app(args: argparse.Namespace, mimic3: Mimic3TextToSpeechSystem, temp_dir: str):
    """Create and return Quart application for Mimic 3 HTTP server"""

    _TEMP_DIR: typing.Optional[Path] = None

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

    @dataclass
    class TextToWavParams:
        """Synthesis parameters used for caching"""

        text: str
        voice: str = args.voice
        noise_scale: float = args.noise_scale
        noise_w: float = args.noise_w
        length_scale: float = args.length_scale
        ssml: bool = False
        text_language: typing.Optional[str] = None

        @property
        def cache_key(self) -> str:
            return hashlib.md5(repr(self).encode()).hexdigest()

    def text_to_wav(params: TextToWavParams, no_cache: bool = False) -> bytes:
        """Synthesize text into audio.

        Returns: WAV bytes
        """

        _LOGGER.debug(params)

        if _TEMP_DIR and (not no_cache):
            # Look up in cache
            maybe_wav_path = _TEMP_DIR / f"{params.cache_key}.wav"
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
                try:
                    if params.ssml:
                        # SSML
                        results = SSMLSpeaker(mimic3).speak(params.text)
                    else:
                        # Plain text
                        mimic3.begin_utterance()
                        mimic3.speak_text(
                            params.text, text_language=params.text_language
                        )
                        results = mimic3.end_utterance()

                    for result in results:
                        # Add audio to existing WAV file
                        if isinstance(result, AudioResult):
                            if not wav_params_set:
                                wav_file.setframerate(result.sample_rate_hz)
                                wav_file.setsampwidth(result.sample_width_bytes)
                                wav_file.setnchannels(result.num_channels)
                                wav_params_set = True

                            wav_file.writeframes(result.audio_bytes)
                except Exception as e:
                    if not wav_params_set:
                        # Set default parameters so exception can propagate
                        wav_file.setframerate(22050)
                        wav_file.setsampwidth(2)
                        wav_file.setnchannels(1)

                    raise e

            wav_bytes = wav_io.getvalue()

            if _TEMP_DIR and (not no_cache):
                # Store in cache
                wav_path = _TEMP_DIR / f"{params.cache_key}.wav"
                wav_path.write_bytes(wav_bytes)

                _LOGGER.debug("Cached WAV at %s", wav_path.absolute())

            return wav_bytes

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

        _LOGGER.debug("Request args: %s", request.args)

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

        # Set SSML flag either from arg or content type
        ssml_str = request.args.get("ssml")
        if ssml_str is not None:
            tts_args["ssml"] = _to_bool(ssml_str)
        elif request.content_type == "application/ssml+xml":
            tts_args["ssml"] = True

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

        wav_bytes = text_to_wav(
            TextToWavParams(text=text, **tts_args), no_cache=no_cache
        )

        return Response(wav_bytes, mimetype="audio/wav")

    @app.route("/api/voices", methods=["GET"])
    async def api_voices():
        voices_dict = {v.key: v for v in mimic3.get_voices()}
        voices = sorted(voices_dict.values(), key=lambda v: v.key)
        return jsonify([dataclasses.asdict(v) for v in voices])

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

    return app
