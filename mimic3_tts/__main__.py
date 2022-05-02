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
import csv
import io
import logging
import os
import shlex
import shutil
import string
import subprocess
import sys
import tempfile
import threading
import time
import typing
import wave
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from queue import Queue

from ._resources import _PACKAGE

if typing.TYPE_CHECKING:
    from . import BaseResult, Mimic3TextToSpeechSystem  # noqa: F401


_LOGGER = logging.getLogger(_PACKAGE)

_DEFAULT_PLAY_PROGRAMS = ["paplay", "play -q", "aplay -q"]

# -----------------------------------------------------------------------------


@dataclass
class ResultToProcess:
    result: "BaseResult"
    line: str
    line_id: str = ""


@dataclass
class CommandLineInterfaceState:
    args: argparse.Namespace
    texts: typing.Optional[typing.Iterable[str]] = None
    mark_writer: typing.Optional[typing.TextIO] = None
    tts: typing.Optional["Mimic3TextToSpeechSystem"] = None
    text_from_stdin: bool = False

    all_audio: bytes = field(default_factory=bytes)
    sample_rate_hz: int = 22050
    sample_width_bytes: int = 2
    num_channels: int = 1

    result_queue: typing.Optional["Queue[typing.Optional[ResultToProcess]]"] = None
    result_thread: typing.Optional[threading.Thread] = None


class OutputNaming(str, Enum):
    """Format used for output file names"""

    TEXT = "text"
    TIME = "time"
    ID = "id"


class StdinFormat(str, Enum):
    """Format of standard input"""

    AUTO = "auto"
    """Choose based on SSML state"""

    LINES = "lines"
    """Each line is a separate sentence/document"""

    DOCUMENT = "document"
    """Entire input is one document"""


# -----------------------------------------------------------------------------


def main():
    """Main entry point"""
    args = get_args()

    if args.debug:
        logging.basicConfig(level=logging.DEBUG)
        logging.getLogger().setLevel(logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)
        logging.getLogger().setLevel(logging.INFO)

    if args.version:
        # Print version and exit
        from . import __version__

        print(__version__)
        sys.exit(0)

    state = CommandLineInterfaceState(args=args)
    initialize_args(state)
    initialize_tts(state)

    try:
        if args.voices:
            # Print voices and exit
            print_voices(state)
        else:
            # Process user input
            if os.isatty(sys.stdin.fileno()):
                print("Reading text from stdin...", file=sys.stderr)

            process_lines(state)
    finally:
        shutdown_tts(state)


def initialize_args(state: CommandLineInterfaceState):
    """Initialze CLI state from command-line arguments"""
    import numpy as np

    args = state.args

    # Create output directory
    if args.output_dir:
        args.output_dir = Path(args.output_dir)
        args.output_dir.mkdir(parents=True, exist_ok=True)

    # Open file for writing the names from <mark> tags in SSML.
    # Each name is printed on a single line.
    if args.mark_file and (args.mark_file != "-"):
        args.mark_file = Path(args.mark_file)
        args.mark_file.parent.mkdir(parents=True, exist_ok=True)
        state.mark_writer = open(  # pylint: disable=consider-using-with
            args.mark_file, "w", encoding="utf-8"
        )
    elif args.stdout:
        state.mark_writer = sys.stderr
    else:
        state.mark_writer = sys.stdout

    if args.seed is not None:
        _LOGGER.debug("Setting random seed to %s", args.seed)
        np.random.seed(args.seed)

    if args.csv_voice:
        # --csv-voice implies --csv
        args.csv = True

    if args.csv:
        args.output_naming = OutputNaming.ID
    elif args.ssml:
        # Avoid text mangling when using SSML
        args.output_naming = OutputNaming.TIME

    # Read text from stdin or arguments
    if args.text:
        # Use arguments
        state.texts = args.text
    else:
        # Use stdin
        state.text_from_stdin = True
        stdin_format = StdinFormat.LINES

        if (args.stdin_format == StdinFormat.AUTO) and args.ssml:
            # Assume SSML input is entire document
            stdin_format = StdinFormat.DOCUMENT

        if stdin_format == StdinFormat.DOCUMENT:
            # One big line
            state.texts = [sys.stdin.read()]
        else:
            # Multiple lines
            state.texts = sys.stdin

    assert state.texts is not None

    if args.process_on_blank_line:

        # Combine text until a blank line is encountered.
        # Good for line-wrapped books where
        # sentences are broken
        # up across multiple
        # lines.
        def process_on_blank_line(lines: typing.Iterable[str]):
            text = ""
            for line in lines:
                line = line.strip()
                if not line:
                    if text:
                        yield text

                    text = ""
                    continue

                text += " " + line

        state.texts = process_on_blank_line(state.texts)

    if args.remote and args.remote.endswith("/"):
        # Ensure no slash
        args.remote = args.remote[:-1]

    if (not args.speaker) and args.voice and ("#" in args.voice):
        # Split apart voice
        args.voice, args.speaker = args.voice.split("#", maxsplit=1)

    if args.deterministic:
        # Disable noise
        _LOGGER.debug("Disabling noise in deterministic mode")
        args.noise_scale = 0.0
        args.noise_w = 0.0


def initialize_tts(state: CommandLineInterfaceState):
    """Create Mimic 3 TTS from command-line arguments"""
    from mimic3_tts import Mimic3Settings, Mimic3TextToSpeechSystem  # noqa: F811

    args = state.args

    if not args.remote:
        # Local TTS
        state.tts = Mimic3TextToSpeechSystem(
            Mimic3Settings(
                length_scale=args.length_scale,
                noise_scale=args.noise_scale,
                noise_w=args.noise_w,
                voices_directories=args.voices_dir,
                use_cuda=args.cuda,
                use_deterministic_compute=args.deterministic,
            )
        )

        state.tts.voice = args.voice
        state.tts.speaker = args.speaker

    if args.voices:
        # Don't bother with the rest of the initialization
        return

    if state.tts:
        if state.args.voice:
            # Set default voice
            state.tts.voice = state.args.voice

        if state.args.preload_voice:
            for voice_key in state.args.preload_voice:
                _LOGGER.debug("Preloading voice: %s", voice_key)
                state.tts.preload_voice(voice_key)

    state.result_queue = Queue(maxsize=args.result_queue_size)

    state.result_thread = threading.Thread(
        target=process_result, daemon=True, args=(state,)
    )
    state.result_thread.start()


def process_result(state: CommandLineInterfaceState):
    try:
        from mimic3_tts import AudioResult, MarkResult

        assert state.result_queue is not None
        args = state.args

        while True:
            result_todo = state.result_queue.get()
            if result_todo is None:
                break

            try:
                result = result_todo.result
                line = result_todo.line
                line_id = result_todo.line_id

                if isinstance(result, AudioResult):
                    if args.interactive or args.output_dir:
                        # Convert to WAV audio
                        wav_bytes: typing.Optional[bytes] = None
                        if args.interactive:
                            if args.stdout:
                                # Write audio to stdout
                                sys.stdout.buffer.write(result.audio_bytes)
                                sys.stdout.buffer.flush()
                            else:
                                # Play sound
                                if not wav_bytes:
                                    wav_bytes = result.to_wav_bytes()

                                if wav_bytes:
                                    play_wav_bytes(state.args, wav_bytes)

                        if args.output_dir:
                            if not wav_bytes:
                                wav_bytes = result.to_wav_bytes()

                            # Determine file name
                            if args.output_naming == OutputNaming.TEXT:
                                # Use text itself
                                file_name = line.strip().replace(" ", "_")
                                file_name = file_name.translate(
                                    str.maketrans(
                                        "", "", string.punctuation.replace("_", "")
                                    )
                                )
                            elif args.output_naming == OutputNaming.TIME:
                                # Use timestamp
                                file_name = str(time.time())
                            elif args.output_naming == OutputNaming.ID:
                                file_name = line_id

                            assert file_name, f"No file name for text: {line}"
                            wav_path = args.output_dir / (file_name + ".wav")
                            wav_path.write_bytes(wav_bytes)

                            _LOGGER.debug("Wrote %s", wav_path)
                    else:
                        # Combine all audio and output to stdout at the end
                        state.all_audio += result.audio_bytes
                        state.sample_rate_hz = result.sample_rate_hz
                        state.sample_width_bytes = result.sample_width_bytes
                        state.num_channels = result.num_channels
                elif isinstance(result, MarkResult):
                    if state.mark_writer:
                        print(result.name, file=state.mark_writer)
            except Exception:
                _LOGGER.exception("Error processing result")
    except Exception:
        _LOGGER.exception("process_result")


def process_line(
    line: str,
    state: CommandLineInterfaceState,
    line_id: str = "",
    line_voice: typing.Optional[str] = None,
):
    assert state.result_queue is not None
    args = state.args

    if state.tts:
        # Local TTS
        from mimic3_tts import SSMLSpeaker

        assert state.tts is not None

        args = state.args

        if line_voice:
            if line_voice.startswith("#"):
                # Same voice, but different speaker
                state.tts.speaker = line_voice[1:]
            else:
                # Different voice
                state.tts.voice = line_voice

        if args.ssml:
            results = SSMLSpeaker(state.tts).speak(line)
        else:
            state.tts.begin_utterance()

            # TODO: text language
            state.tts.speak_text(line)

            results = state.tts.end_utterance()
    else:
        # Remote TTS
        from mimic3_tts import AudioResult

        voice: typing.Optional[str] = None
        if line_voice:
            if line_voice.startswith("#"):
                # Same voice, but different speaker
                if args.voice:
                    voice = f"{args.voice}{line_voice}"
            else:
                # Different voice
                voice = line_voice

        # Get remote WAV data and repackage as AudioResult
        wav_bytes = get_remote_wav_bytes(state, line, voice=voice)
        with io.BytesIO(wav_bytes) as wav_io:
            wav_reader: wave.Wave_read = wave.open(wav_io, "rb")
            with wav_reader as wav_file:
                results = [
                    AudioResult(
                        sample_rate_hz=wav_file.getframerate(),
                        sample_width_bytes=wav_file.getsampwidth(),
                        num_channels=wav_file.getnchannels(),
                        audio_bytes=wav_file.readframes(wav_file.getnframes()),
                    )
                ]

    # Add results to processing queue
    for result in results:
        state.result_queue.put(
            ResultToProcess(
                result=result,
                line=line,
                line_id=line_id,
            )
        )

    # Restore voice/speaker
    if state.tts:
        state.tts.voice = args.voice
        state.tts.speaker = args.speaker


def process_lines(state: CommandLineInterfaceState):
    assert state.texts is not None

    args = state.args

    try:
        result_idx = 0

        for line in state.texts:
            line_voice: typing.Optional[str] = None
            line_id = ""
            line = line.strip()
            if not line:
                continue

            if args.output_naming == OutputNaming.ID:
                # Line has the format id|text instead of just text
                with io.StringIO(line) as line_io:
                    reader = csv.reader(line_io, delimiter=args.csv_delimiter)
                    row = next(reader)
                    line_id, line = row[0], row[-1]
                    if args.csv_voice:
                        line_voice = row[1]

            process_line(line, state, line_id=line_id, line_voice=line_voice)
            result_idx += 1

    except KeyboardInterrupt:
        if state.result_queue is not None:
            # Draw audio playback queue
            while not state.result_queue.empty():
                state.result_queue.get()
    finally:
        # Wait for raw stream to finish
        if state.result_queue is not None:
            state.result_queue.put(None)

        if state.result_thread is not None:
            state.result_thread.join()

    # -------------------------------------------------------------------------

    # Write combined audio to stdout
    if state.all_audio:
        _LOGGER.debug("Writing WAV audio to stdout")

        if sys.stdout.isatty() and (not state.args.stdout):
            with io.BytesIO() as wav_io:
                wav_file_play: wave.Wave_write = wave.open(wav_io, "wb")
                with wav_file_play:
                    wav_file_play.setframerate(state.sample_rate_hz)
                    wav_file_play.setsampwidth(state.sample_width_bytes)
                    wav_file_play.setnchannels(state.num_channels)
                    wav_file_play.writeframes(state.all_audio)

                play_wav_bytes(state.args, wav_io.getvalue())
        else:
            # Write output directly to stdout
            wav_file_write: wave.Wave_write = wave.open(sys.stdout.buffer, "wb")
            with wav_file_write:
                wav_file_write.setframerate(state.sample_rate_hz)
                wav_file_write.setsampwidth(state.sample_width_bytes)
                wav_file_write.setnchannels(state.num_channels)
                wav_file_write.writeframes(state.all_audio)

            sys.stdout.buffer.flush()


def shutdown_tts(state: CommandLineInterfaceState):
    if state.tts:
        state.tts.shutdown()
        state.tts = None


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


def print_voices(state: CommandLineInterfaceState):
    if state.tts:
        # Local TTS
        voices = list(state.tts.get_voices())
        voices = sorted(voices, key=lambda v: v.key)
    else:
        # Remove TTS
        voices = get_remote_voices(state)

    writer = csv.writer(sys.stdout, delimiter="\t")
    writer.writerow(("KEY", "LANGUAGE", "NAME", "DESCRIPTION", "LOCATION"))
    for voice in voices:
        writer.writerow(
            (voice.key, voice.language, voice.name, voice.description, voice.location)
        )


# -----------------------------------------------------------------------------


def get_remote_voices(state: CommandLineInterfaceState) -> typing.List:
    import requests

    from mimic3_tts import Voice

    args = state.args

    url = f"{args.remote}/api/voices"
    _LOGGER.debug("Getting voices from remote server at %s", url)

    voices_json = requests.get(url).json()

    return [Voice(**voice_args) for voice_args in voices_json]


def get_remote_wav_bytes(
    state: CommandLineInterfaceState,
    text: str,
    voice: typing.Optional[str] = None,
) -> bytes:
    import requests

    args = state.args

    if args.ssml:
        headers = {"Content-Type": "application/ssml+xml"}
    else:
        headers = {"Content-Type": "text/plain"}

    params: typing.Dict[str, str] = {}

    if voice:
        params["voice"] = voice
    elif args.voice:
        if args.speaker:
            params["voice"] = f"{args.voice}#{args.speaker}"
        else:
            params["voice"] = args.voice

    if args.length_scale:
        params["lengthScale"] = args.length_scale

    if args.noise_scale:
        params["noiseScale"] = args.noise_scale

    if args.noise_w:
        params["noiseW"] = args.noise_w

    url = f"{args.remote}/api/tts"
    _LOGGER.debug("Synthesizing text remotely at %s", url)

    wav_bytes = requests.post(url, headers=headers, params=params, data=text).content

    return wav_bytes


# -----------------------------------------------------------------------------


def get_args(argv=None):
    """Parse command-line arguments"""
    parser = argparse.ArgumentParser(
        prog=_PACKAGE, description="Mimic 3 command-line interface"
    )
    parser.add_argument(
        "text", nargs="*", help="Text to convert to speech (default: stdin)"
    )
    parser.add_argument(
        "--remote",
        nargs="?",
        const="http://localhost:59125",
        help="Connect to Mimic 3 HTTP web server for synthesis (default: localhost)",
    )
    parser.add_argument(
        "--stdin-format",
        choices=[str(v.value) for v in StdinFormat],
        default=StdinFormat.AUTO,
        help="Format of stdin text (default: auto)",
    )
    parser.add_argument(
        "--voice",
        "-v",
        help="Name of voice (expected in <voices-dir>/<language>)",
    )
    parser.add_argument(
        "--speaker",
        "-s",
        help="Name or number of speaker (default: first speaker)",
    )
    parser.add_argument(
        "--voices-dir",
        action="append",
        help="Directory with voices (format is <language>/<voice_name>)",
    )
    parser.add_argument("--voices", action="store_true", help="List available voices")
    parser.add_argument("--output-dir", help="Directory to write WAV file(s)")
    parser.add_argument(
        "--output-naming",
        choices=[v.value for v in OutputNaming],
        default="text",
        help="Naming scheme for output WAV files (requires --output-dir)",
    )
    parser.add_argument(
        "--id-delimiter",
        default="|",
        help="Delimiter between id and text in lines (default: |). Requires --output-naming id",
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Play audio after each input line (see --play-program)",
    )
    parser.add_argument("--csv", action="store_true", help="Input format is id|text")
    parser.add_argument(
        "--csv-delimiter", default="|", help="Delimiter used with --csv (default: |)"
    )
    parser.add_argument(
        "--csv-voice",
        action="store_true",
        help="Input format is id|voice|text or id|#speaker|text",
    )
    parser.add_argument(
        "--mark-file",
        help="File to write mark names to as they're encountered (--ssml only)",
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

    # Miscellaneous
    parser.add_argument(
        "--result-queue-size",
        default=5,
        help="Maximum number of sentences to maintain in output queue (default: 5)",
    )
    parser.add_argument(
        "--process-on-blank-line",
        action="store_true",
        help="Process text only after encountering a blank line",
    )
    parser.add_argument("--ssml", action="store_true", help="Input text is SSML")
    parser.add_argument(
        "--stdout",
        action="store_true",
        help="Force audio output to stdout even if a tty is detected",
    )
    parser.add_argument(
        "--preload-voice", action="append", help="Preload voice when starting up"
    )
    parser.add_argument(
        "--play-program",
        action="append",
        default=_DEFAULT_PLAY_PROGRAMS,
        help="Program(s) used to play WAV files",
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
    parser.add_argument("--seed", type=int, help="Set random seed (default: not set)")
    parser.add_argument("--version", action="store_true", help="Print version and exit")
    parser.add_argument(
        "--debug", action="store_true", help="Print DEBUG messages to the console"
    )

    return parser.parse_args(args=argv)


# -----------------------------------------------------------------------------

if __name__ == "__main__":
    main()
