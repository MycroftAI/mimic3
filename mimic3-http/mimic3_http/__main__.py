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
import asyncio
import logging
import tempfile

import hypercorn
from mimic3_tts import Mimic3Settings, Mimic3TextToSpeechSystem

from .app import get_app
from .args import get_args

_LOGGER = logging.getLogger(__name__)


# -----------------------------------------------------------------------------

args = get_args()

if args.debug:
    logging.basicConfig(level=logging.DEBUG)
else:
    logging.basicConfig(level=logging.INFO)


_LOGGER.debug(args)


# -----------------------------------------------------------------------------
# Load Mimic 3
# -----------------------------------------------------------------------------

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
    # Ensure voices are preloaded
    for voice_key in args.preload_voice:
        _LOGGER.debug("Preloading voice: %s", voice_key)
        mimic3.preload_voice(voice_key)


# -----------------------------------------------------------------------------
# Run Web Server
# -----------------------------------------------------------------------------

_LOGGER.info("Starting web server")

hyp_config = hypercorn.config.Config()
hyp_config.bind = [f"{args.host}:{args.port}"]

with mimic3, tempfile.TemporaryDirectory(prefix="mimic3") as temp_dir:
    app = get_app(args, mimic3, temp_dir)
    asyncio.run(hypercorn.asyncio.serve(app, hyp_config))
