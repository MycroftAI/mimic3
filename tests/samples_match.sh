#!/usr/bin/env bash
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
# Uses cmp to compare byte differences between two samples.
# Exits with an error if differences exceed a threshold.
#
set -o pipefail

if [ -z "$2" ]; then
    echo 'Usage: samples_match.sh WAV1 WAV2 [threshold]';
    exit 1
fi

wav1="$1"
wav2="$2"
threshold="${3:-5000}"

bytes_different="$(cmp -l "${wav1}" "${wav2}" | wc -l)"

if (( ${bytes_different} > ${threshold} )); then
    echo "Samples differ too much (${bytes_different} > ${threshold})";
    exit 1;
fi

echo 'OK'
