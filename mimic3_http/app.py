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
import asyncio
import dataclasses
import json
import logging
import re
import shlex
import subprocess
import typing
from pathlib import Path
from queue import Queue
from urllib.parse import parse_qs
from uuid import uuid4

import quart_cors
from quart import (
    Quart,
    Response,
    jsonify,
    render_template,
    request,
    send_from_directory,
)
from swagger_ui import api_doc

from mimic3_tts import DEFAULT_VOICE, Mimic3Settings, Mimic3TextToSpeechSystem
from mimic3_tts.download import is_voice_downloaded
from mimic3_tts.utils import LANG_NAMES, SAMPLE_SENTENCES

from ._resources import _DIR, _PACKAGE
from .args import _MISSING
from .const import SynthesisRequest, TextToWavParams

_LOGGER = logging.getLogger(__name__)


def get_app(args: argparse.Namespace, request_queue: Queue, temp_dir: str):
    """Create and return Quart application for Mimic 3 HTTP server"""

    _TEMP_DIR: typing.Optional[Path] = None

    _MIMIC3 = Mimic3TextToSpeechSystem(
        Mimic3Settings(voices_directories=args.voices_dir)
    )

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

    async def text_to_wav(params: TextToWavParams, no_cache: bool = False) -> bytes:
        """Synthesize text into audio.

        Returns: WAV bytes
        """
        if args.deterministic:
            # Disable noise
            _LOGGER.debug("Disabling noise in deterministic mode")
            params.noise_scale = 0.0
            params.noise_w = 0.0

        _LOGGER.debug(params)

        if _TEMP_DIR and (not no_cache):
            # Look up in cache
            maybe_wav_path = _TEMP_DIR / f"{params.cache_key}.wav"
            if maybe_wav_path.is_file():
                _LOGGER.debug("Loading WAV from cache: %s", maybe_wav_path)
                wav_bytes = maybe_wav_path.read_bytes()
                return wav_bytes

        loop = asyncio.get_running_loop()
        future = loop.create_future()
        request_queue.put_nowait(
            SynthesisRequest(
                params=params,
                loop=loop,
                future=future,
            )
        )
        wav_bytes = await future

        if _TEMP_DIR and (not no_cache):
            # Store in cache
            wav_path = _TEMP_DIR / f"{params.cache_key}.wav"
            wav_path.parent.mkdir(parents=True, exist_ok=True)
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

    show_openapi = True

    @app.route("/")
    async def app_index():
        """Main page."""
        return await render_template(
            "index.html",
            show_openapi=show_openapi,
            max_text_length=args.max_text_length,
            default_voice=args.default_voice,
        )

    @app.route("/api/tts", methods=["GET", "POST"])
    async def app_tts() -> typing.Union[Response, str]:
        """Speak text to WAV."""
        tts_args: typing.Dict[str, typing.Any] = {
            "length_scale": args.length_scale,
            "noise_scale": args.noise_scale,
            "noise_w": args.noise_w,
        }

        _LOGGER.debug("Request args: %s", request.args)

        voice = request.args.get("voice") or args.voice or DEFAULT_VOICE
        tts_args["voice"] = str(voice)

        # TTS settings
        noise_scale = request.args.get("noiseScale")
        if noise_scale:
            tts_args["noise_scale"] = float(noise_scale)

        noise_w = request.args.get("noiseW")
        if noise_w:
            tts_args["noise_w"] = float(noise_w)

        length_scale = request.args.get("lengthScale")
        if length_scale:
            tts_args["length_scale"] = float(length_scale)

        # Set SSML flag either from arg or content type
        ssml_str = request.args.get("ssml")
        if ssml_str:
            tts_args["ssml"] = _to_bool(ssml_str)
        elif request.content_type == "application/ssml+xml":
            tts_args["ssml"] = True

        text_language = request.args.get("textLanguage")
        if text_language:
            tts_args["text_language"] = str(text_language)

        # Id used for cache
        cache_id = request.args.get("cacheId")
        if cache_id:
            tts_args["cache_id"] = str(cache_id)

        # Text can come from POST body or GET ?text arg
        if request.method == "POST":
            text = (await request.data).decode()
        else:
            text = request.args.get("text", "")

        assert text, "No text provided"

        if args.max_text_length is not None:
            text = text[: args.max_text_length]

        # Cache settings
        no_cache_str = request.args.get("noCache", "")
        no_cache = _to_bool(no_cache_str)

        wav_bytes = await text_to_wav(
            TextToWavParams(text=text, **tts_args), no_cache=no_cache
        )

        audio_target = request.args.get("audioTarget", "client").strip().lower()
        if audio_target == "client":
            return Response(wav_bytes, mimetype="audio/wav")

        # Play audio on server
        play_cmd = shlex.split(args.play_program)
        subprocess.run(play_cmd, input=wav_bytes, check=True)

        return "OK"

    @app.route("/api/voices", methods=["GET"])
    async def api_voices():
        voices_by_key = {v.key: v for v in _MIMIC3.get_voices()}
        sorted_voices = sorted(voices_by_key.values(), key=lambda v: v.key)
        voice_dicts = [dataclasses.asdict(v) for v in sorted_voices]

        # Add more fields to voices
        for voice_dict in voice_dicts:
            voice_lang = voice_dict["language"]

            # en_US => en
            short_lang = voice_lang.split("_", maxsplit=1)[0]

            # en_US => English (US)
            lang_name = LANG_NAMES.get(voice_lang, voice_lang)

            if isinstance(lang_name, str):
                # Native and English language name are the same
                native_lang, english_lang = lang_name, lang_name
            else:
                # Native and English language name are different
                native_lang, english_lang = lang_name

            voice_dict["language_native"] = native_lang
            voice_dict["language_english"] = english_lang

            sample_text = SAMPLE_SENTENCES.get(short_lang, "")
            sample_text = re.sub(r"\s+", " ", sample_text)
            voice_dict["sample_text"] = sample_text

            # Ensure aliases is not a set for JSON serialization
            aliases = voice_dict.get("aliases")
            if aliases is not None:
                voice_dict["aliases"] = list(aliases)

        return jsonify(voice_dicts)

    @app.route("/process", methods=["GET", "POST"])
    async def api_marytts_process():
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

        if args.max_text_length is not None:
            text = text[: args.max_text_length]

        voice = voice or args.voice or DEFAULT_VOICE

        # Assume SSML if text begins with an angle bracket
        ssml = text.strip().startswith("<")

        _LOGGER.debug("Speaking with voice '%s': %s", voice, text)
        wav_bytes = await text_to_wav(
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

    @app.route("/voices", methods=["GET"])
    async def api_marytts_voices():
        """MaryTTS-compatible /voices endpoint"""
        voices_by_key = {v.key: v for v in _MIMIC3.get_voices()}
        sorted_voices = sorted(voices_by_key.values(), key=lambda v: v.key)

        # [voice] [language] [gender] [tech=hmm]
        lines = []
        gender = "NA"  # don't have this information for every speaker yet
        tech = "vits"

        for voice in sorted_voices:
            if not is_voice_downloaded(voice.location):
                # Skip voices that are not yet installed
                continue
            if voice.is_multispeaker:
                # List each speaker separately
                for speaker in voice.speakers:
                    lines.append(
                        f"{voice.key}#{speaker} {voice.language} {gender} {tech}"
                    )
            else:
                lines.append(f"{voice.key} {voice.language} {gender} {tech}")

        return "\n".join(lines)

    @app.route("/api/healthcheck", methods=["GET"])
    async def api_healthcheck():
        """Endpoint to check health status"""
        return "OK"

    # Swagger UI
    show_openapi = not args.no_show_openapi
    if show_openapi:
        try:
            api_doc(
                app,
                config_path=_DIR / "swagger.yaml",
                url_prefix="/openapi",
                title="Mimic 3",
            )
        except Exception:
            # Fails with PyInstaller for some reason
            _LOGGER.exception("Error setting up swagger UI page")
            show_openapi = False

    @app.errorhandler(Exception)
    async def handle_error(err) -> typing.Tuple[str, int]:
        """Return error as text."""
        _LOGGER.exception(err)
        return (f"{err.__class__.__name__}: {err}", 500)

    return app
