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
    from mimic3_tts import Mimic3TextToSpeechSystem


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

    raw_queue: typing.Optional["Queue[typing.Optional[bytes]]"] = None
    raw_stream_thread: typing.Optional[threading.Thread] = None


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
    else:
        state.mark_writer = sys.stderr

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

    # TODO: voice/speaker
    state.tts = Mimic3TextToSpeechSystem(Mimic3Settings())

    if state.args.voice:
        state.tts.voice = state.args.voice

    # max_thread_workers: typing.Optional[int] = None

    # if args.max_thread_workers is not None:
    #     max_thread_workers = (
    #         None if args.max_thread_workers < 1 else args.max_thread_workers
    #     )
    # elif args.raw_stream:
    #     # Faster time to first audio
    #     max_thread_workers = 2

    # executor = ThreadPoolExecutor(max_workers=max_thread_workers)

    # if os.isatty(sys.stdout.fileno()):
    #     if (not args.output_dir) and (not args.raw_stream):
    #         # No where else for the audio to go
    #         args.interactive = True

    if args.raw_stream:
        # Output in a separate thread to avoid blocking audio processing
        state.raw_queue = Queue(maxsize=args.raw_stream_queue_size)

        def output_raw_stream():
            while True:
                audio = state.raw_queue.get()
                if audio is None:
                    break

                _LOGGER.debug(
                    "Writing %s byte(s) of 16-bit 22050Hz mono PCM to stdout",
                    len(audio),
                )
                sys.stdout.buffer.write(audio)
                sys.stdout.buffer.flush()

        state.raw_stream_thread = threading.Thread(
            target=output_raw_stream, daemon=True
        )
        state.raw_stream_thread.start()


def process_line(line_id: str, line: str, state: CommandLineInterfaceState):
    from mimic3_tts import AudioResult, MarkResult

    args = state.args
    assert state.tts is not None

    # TODO: SSML
    state.tts.begin_utterance()

    # TODO: text language
    state.tts.speak_text(line)

    # TODO: CSV
    text_id = ""
    result_idx = 0

    for result in state.tts.end_utterance():
        if isinstance(result, AudioResult):
            if args.raw_stream:
                assert state.raw_queue is not None
                state.raw_queue.put(result.audio_bytes)
            elif args.interactive or args.output_dir:
                # Convert to WAV audio
                wav_bytes: typing.Optional[bytes] = None
                if args.interactive:
                    if not wav_bytes:
                        wav_bytes = result.to_wav_bytes()

                    play_wav_bytes(wav_bytes)

                if args.output_dir:
                    if not wav_bytes:
                        wav_bytes = result.to_wav_bytes()

                    # Determine file name
                    if args.output_naming == OutputNaming.TEXT:
                        # Use text itself
                        file_name = line.strip().replace(" ", "_")
                        file_name = file_name.translate(
                            str.maketrans("", "", string.punctuation.replace("_", ""))
                        )
                    elif args.output_naming == OutputNaming.TIME:
                        # Use timestamp
                        file_name = str(time.time())
                    elif args.output_naming == OutputNaming.ID:
                        if not text_id:
                            text_id = line_id
                        else:
                            text_id = f"{line_id}_{result_idx + 1}"

                        file_name = text_id

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

            result_idx += 1
        elif isinstance(result, MarkResult):
            if state.mark_writer:
                print(result.name, file=state.mark_writer)

    # text_id = ""

    # for result_idx, result in enumerate(tts_results):
    #     text = result.text

    #     # Write before marks
    #     if result.marks_before and state.mark_writer:
    #         for mark_name in result.marks_before:
    #             print(mark_name, file=state.mark_writer)

    # if args.raw_stream:
    #     assert raw_queue is not None
    #     raw_queue.put(result.audio.tobytes())
    # elif args.interactive or args.output_dir:
    #     # Convert to WAV audio
    #     with io.BytesIO() as wav_io:
    #         wav_write(wav_io, result.sample_rate, result.audio)
    #         wav_data = wav_io.getvalue()

    #     assert wav_data is not None

    #     if args.interactive:

    #         # Play audio
    #         _LOGGER.debug("Playing audio with play command")
    #         try:
    #             subprocess.run(
    #                 play_command,
    #                 input=wav_data,
    #                 stdout=subprocess.DEVNULL,
    #                 stderr=subprocess.DEVNULL,
    #                 check=True,
    #             )
    #         except FileNotFoundError:
    #             _LOGGER.error(
    #                 "Unable to play audio with command '%s'. set with --play-command or redirect stdout",
    #                 args.play_command,
    #             )
    #             with open("output.wav", "wb") as output_file:
    #                 output_file.write(wav_data)

    #             _LOGGER.warning("stdout not redirected. Wrote audio to output.wav.")

    # else:
    #     # Combine all audio and output to stdout at the end
    #     all_audios.append(result.audio)

    # # Write after marks
    # if result.marks_after and state.mark_writer:
    #     for mark_name in result.marks_after:
    #         print(mark_name, file=state.mark_writer)


def process_lines(state: CommandLineInterfaceState):
    assert state.texts is not None

    args = state.args
    start_time_to_first_audio = time.perf_counter()

    try:
        for line in state.texts:
            line_id = ""
            line = line.strip()
            if not line:
                continue

            if args.output_naming == OutputNaming.ID:
                # Line has the format id|text instead of just text
                line_id, line = line.split(args.id_delimiter, maxsplit=1)

            process_line(line_id, line, state)

    except KeyboardInterrupt:
        if state.raw_queue is not None:
            # Draw audio playback queue
            while not state.raw_queue.empty():
                state.raw_queue.get()
    finally:
        # Wait for raw stream to finish
        if state.raw_queue is not None:
            state.raw_queue.put(None)

        if state.raw_stream_thread is not None:
            state.raw_stream_thread.join()

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
        default=0.333,
        help="Noise scale (default: 0.333)",
    )
    parser.add_argument(
        "--length-scale",
        type=float,
        default=1.0,
        help="Length scale (default: 1.0)",
    )
    parser.add_argument(
        "--noise-w",
        type=float,
        default=1.0,
        help="Variation in cadence (default: 1.0)",
    )

    # Miscellaneous
    parser.add_argument(
        "--max-thread-workers",
        type=int,
        help="Maximum number of threads to concurrently load models and run sentences through TTS/Vocoder",
    )
    parser.add_argument(
        "--raw-stream",
        action="store_true",
        help="Stream raw 16-bit 22050Hz mono PCM audio to stdout",
    )
    parser.add_argument(
        "--raw-stream-queue-size",
        default=5,
        help="Maximum number of sentences to maintain in output queue with --raw-stream (default: 5)",
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

    # # Directories to search for voices
    # voices_dirs = get_voices_dirs(args.voices_dir)

    # def list_voices_vocoders():
    #     """Print all vocoders and voices"""
    #     # (type, name) -> location
    #     local_info = {}

    #     # Search for downloaded voices/vocoders
    #     for voices_dir in voices_dirs:
    #         if not voices_dir.is_dir():
    #             continue

    #         for voice_dir in voices_dir.iterdir():
    #             if not voice_dir.is_dir():
    #                 continue

    #             if voice_dir.name in VOCODER_DIR_NAMES:
    #                 # Vocoder
    #                 for vocoder_model_dir in voice_dir.iterdir():
    #                     if not valid_voice_dir(vocoder_model_dir):
    #                         continue

    #                     full_vocoder_name = f"{voice_dir.name}-{vocoder_model_dir.name}"
    #                     local_info[("vocoder", full_vocoder_name)] = str(
    #                         vocoder_model_dir
    #                     )
    #             else:
    #                 # Voice
    #                 voice_lang = voice_dir.name
    #                 for voice_model_dir in voice_dir.iterdir():
    #                     if not valid_voice_dir(voice_model_dir):
    #                         continue

    #                     local_info[("voice", voice_model_dir.name)] = str(
    #                         voice_model_dir
    #                     )

    #     # (type, lang, name, downloaded, aliases, location)
    #     voices_and_vocoders = []
    #     with open(_DIR / "VOCODERS", "r", encoding="utf-8") as vocoders_file:
    #         for line in vocoders_file:
    #             line = line.strip()
    #             if not line:
    #                 continue

    #             *vocoder_aliases, full_vocoder_name = line.split()
    #             downloaded = False

    #             location = local_info.get(("vocoder", full_vocoder_name), "")
    #             if location:
    #                 downloaded = True

    #             voices_and_vocoders.append(
    #                 (
    #                     "vocoder",
    #                     " ",
    #                     "*" if downloaded else " ",
    #                     full_vocoder_name,
    #                     ",".join(vocoder_aliases),
    #                     location,
    #                 )
    #             )

    #     with open(_DIR / "VOICES", "r", encoding="utf-8") as voices_file:
    #         for line in voices_file:
    #             line = line.strip()
    #             if not line:
    #                 continue

    #             *voice_aliases, full_voice_name, download_name = line.split()
    #             voice_lang = download_name.split("_", maxsplit=1)[0]

    #             downloaded = False

    #             location = local_info.get(("voice", full_voice_name), "")
    #             if location:
    #                 downloaded = True

    #             voices_and_vocoders.append(
    #                 (
    #                     "voice",
    #                     voice_lang,
    #                     "*" if downloaded else " ",
    #                     full_voice_name,
    #                     ",".join(voice_aliases),
    #                     location,
    #                 )
    #             )

    #     headers = ("TYPE", "LANG", "LOCAL", "NAME", "ALIASES", "LOCATION")

    #     # Get widths of columns
    #     col_widths = [0] * len(voices_and_vocoders[0])
    #     for item in voices_and_vocoders:
    #         for col in range(len(col_widths)):
    #             col_widths[col] = max(
    #                 col_widths[col], len(item[col]) + 1, len(headers[col]) + 1
    #             )

    #     # Print results
    #     print(*(h.ljust(col_widths[col]) for col, h in enumerate(headers)))

    #     for item in sorted(voices_and_vocoders):
    #         print(*(v.ljust(col_widths[col]) for col, v in enumerate(item)))

    # if args.list:
    #     list_voices_vocoders()
    #     sys.exit(0)

    return args


# -----------------------------------------------------------------------------

if __name__ == "__main__":
    main()
