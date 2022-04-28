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
# -----------------------------------------------------------------------------
#
# Compares two WAV files, exiting abnormally if they differ by a percentage.
#
import argparse
import wave

parser = argparse.ArgumentParser()
parser.add_argument("wav1", help="First sample")
parser.add_argument("wav2", help="Second sample")
parser.add_argument(
    "--percent-threshold",
    type=float,
    default=0.1,
    help="Percent of samples allowed to be different",
)
args = parser.parse_args()

with wave.open(args.wav1, "rb") as wav1, wave.open(args.wav2, "rb") as wav2:
    assert wav1.getframerate() == wav2.getframerate(), "Mismatched sample rates"
    assert wav1.getsampwidth() == wav2.getsampwidth(), "Mismatched sample widths"
    assert wav1.getnchannels() == wav2.getnchannels(), "Mismatched channels"

    wav1_samples = wav1.getnframes()
    wav2_samples = wav2.getnframes()

    smaller_samples = min(wav1_samples, wav2_samples)
    assert smaller_samples > 0, "Empty WAV"

    max_different = int(args.percent_threshold * smaller_samples)

    # Mismatched size is starting difference
    num_samples_different = abs(wav1_samples - wav2_samples)

    for _ in range(smaller_samples):
        # Check every sample
        if num_samples_different > max_different:
            break

        if wav1.readframes(1) != wav2.readframes(1):
            num_samples_different += 1

    assert num_samples_different <= max_different, "Different"

    percent_different = num_samples_different / smaller_samples
    print(percent_different)
