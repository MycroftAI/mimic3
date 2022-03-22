#!/usr/bin/env python3
import argparse
import io
import logging
import os
import platform
import shlex
import string
import subprocess
import sys
import threading
import tempfile
import time
import typing
import urllib.parse
import urllib.request
import wave
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from queue import Queue

if typing.TYPE_CHECKING:
    from mimic3_tts import Mimic3TextToSpeechSystem, BaseResult


_DIR = Path(__file__).parent
_PACKAGE = "mimic3_cli"

_LOGGER = logging.getLogger(_PACKAGE)


# -----------------------------------------------------------------------------


@dataclass
class CommandLineInterfaceState:
    args: argparse.Namespace
    texts: typing.Optional[typing.Iterable[str]] = None
    mark_writer: typing.Optional[typing.TextIO] = None
    tts: typing.Optional["Mimic3TextToSpeechSystem"] = None

    all_audio: bytes = field(default_factory=bytes)
    sample_rate_hz: int = 22050
    sample_width_bytes: int = 2
    num_channels: int = 1

    result_queue: typing.Optional["Queue[BaseResult]"] = None
    result_thread: typing.Optional[threading.Thread] = None


@dataclass
class ResultToProcess:
    result: "BaseResult"
    line: str
    line_id: str = ""


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

    # TODO: Print version

    # TODO: CUDA support
    # if args.cuda:
    #     import torch

    #     args.cuda = torch.cuda.is_available()
    #     if not args.cuda:
    #         args.half = False
    #         _LOGGER.warning("CUDA is not available")

    # TODO: Disable Onnx optimizations
    # Handle optimizations.
    # onnxruntime crashes on armv7l if optimizations are enabled.
    # setattr(args, "no_optimizations", False)
    # if args.optimizations == "off":
    #     args.no_optimizations = True
    # elif args.optimizations == "auto":
    #     if platform.machine() == "armv7l":
    #         # Enabling optimizations on 32-bit ARM crashes
    #         args.no_optimizations = True

    # TODO: Backend selection
    # backend: typing.Optional[InferenceBackend] = None
    # if args.backend:
    #     backend = InferenceBackend(args.backend)

    state = CommandLineInterfaceState(args=args)
    initialize_args(state)
    initialize_tts(state)

    try:
        process_lines(state)
    finally:
        shutdown_tts(state)


def initialize_args(state: CommandLineInterfaceState):
    import numpy as np

    args = state.args

    # Create output directory
    if args.output_dir:
        args.output_dir = Path(args.output_dir)
        args.output_dir.mkdir(parents=True, exist_ok=True)

    # Open file for writing the names from <mark> tags in SSML.
    # Each name is printed on a single line.
    if args.mark_file:
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

    if args.csv:
        args.output_naming = "id"

    # Read text from stdin or arguments
    if args.text:
        # Use arguments
        state.texts = args.text
    else:
        # Use stdin
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

        if os.isatty(sys.stdin.fileno()):
            print("Reading text from stdin...", file=sys.stderr)

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


def initialize_tts(state: CommandLineInterfaceState):
    import numpy as np
    from mimic3_tts import (
        Mimic3TextToSpeechSystem,
        Mimic3Settings,
        AudioResult,
        MarkResult,
    )

    args = state.args

    state.tts = Mimic3TextToSpeechSystem(Mimic3Settings())

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
                                    play_wav_bytes(wav_bytes)

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
):
    from mimic3_tts import SSMLSpeaker

    assert state.tts is not None
    assert state.result_queue is not None

    args = state.args

    if args.ssml:
        results = SSMLSpeaker(state.tts).speak(line)
    else:
        state.tts.begin_utterance()

        # TODO: text language
        state.tts.speak_text(line)

        results = state.tts.end_utterance()

    for result in results:
        state.result_queue.put(
            ResultToProcess(
                result=result,
                line=line,
                line_id=line_id,
            )
        )


def process_lines(state: CommandLineInterfaceState):
    assert state.texts is not None

    args = state.args

    try:
        result_idx = 0

        for line in state.texts:
            line_id = ""
            line = line.strip()
            if not line:
                continue

            if args.output_naming == OutputNaming.ID:
                # Line has the format id|text instead of just text
                line_id, line = line.split(args.id_delimiter, maxsplit=1)

            process_line(line, state, line_id=line_id)
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
            print("Waiting for audio to finish...", file=sys.stderr)
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

                play_wav_bytes(wav_io.getvalue())
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
    if state.tts is not None:
        state.tts.shutdown()
        state.tts = None


def play_wav_bytes(wav_bytes: bytes):
    from playsound import playsound

    with tempfile.NamedTemporaryFile(mode="wb+", suffix=".wav") as wav_file:
        wav_file.write(wav_bytes)
        wav_file.seek(0)

        _LOGGER.debug("Playing WAV file: %s", wav_file.name)
        playsound(wav_file.name)


# -----------------------------------------------------------------------------


def get_args():
    """Parse command-line arguments"""
    parser = argparse.ArgumentParser(prog=_PACKAGE)
    # parser.add_argument(
    #     "--language", help="Gruut language for text input (en-us, etc.)"
    # )
    parser.add_argument(
        "text", nargs="*", help="Text to convert to speech (default: stdin)"
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
    # parser.add_argument(
    #     "--voices-dir",
    #     help="Directory with voices (format is <language>/<name_model-type>)",
    # )
    # parser.add_argument(
    #     "--list", action="store_true", help="List available voices/vocoders"
    # )
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
        help="Play audio after each input line (see --play-command)",
    )
    parser.add_argument("--csv", action="store_true", help="Input format is id|text")
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
    # parser.add_argument(
    #     "--optimizations",
    #     choices=["auto", "on", "off"],
    #     default="auto",
    #     help="Enable/disable Onnx optimizations (auto=disable on armv7l)",
    # )

    parser.add_argument(
        "--stdout",
        action="store_true",
        help="Force audio output to stdout even if a tty is detected",
    )
    parser.add_argument(
        "--preload-voice", action="append", help="Preload voice when starting up"
    )
    parser.add_argument("--seed", type=int, help="Set random seed (default: not set)")
    # parser.add_argument("--version", action="store_true", help="Print version and exit")
    parser.add_argument(
        "--debug", action="store_true", help="Print DEBUG messages to the console"
    )
    args = parser.parse_args()

    if args.debug:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)

    # -------------------------------------------------------------------------

    # if args.version:
    #     # Print version and exit
    #     from larynx import __version__

    #     print(__version__)
    #     sys.exit(0)

    # -------------------------------------------------------------------------

    return args


# -----------------------------------------------------------------------------

if __name__ == "__main__":
    main()
