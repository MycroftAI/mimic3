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
# Runs module check.sh scripts to format/lint/typecheck code.
#
set -eo pipefail

# Directory of *this* script
this_dir="$( cd "$( dirname "$0" )" && pwd )"

# Path to virtual environment
: "${venv:=${this_dir}/.venv}"

if [ -d "${venv}" ]; then
    # Activate virtual environment if available
    source "${venv}/bin/activate"
fi

python_files=("${this_dir}/tests"/*.py)

for module_name in 'mimic3_tts' 'mimic3_http' 'opentts_abc'; do
    python_files+=("${module_name}")
done

# Format code
black "${python_files[@]}"
isort "${python_files[@]}"

# Check
flake8 "${python_files[@]}"
pylint "${python_files[@]}"
mypy "${python_files[@]}"
