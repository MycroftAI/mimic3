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
# Formats, lints, and typechecks code.
#
set -eo pipefail

# Directory of *this* script
this_dir="$( cd "$( dirname "$0" )" && pwd )"

# Kebab to snake case
module_name="$(basename "${this_dir}" | sed -e 's/-/_/g')"
base_dir="$(realpath "${this_dir}/..")"
src_dir="${this_dir}/${module_name}"

# Path to virtual environment
: "${venv:=${base_dir}/.venv}"

if [ -d "${venv}" ]; then
    # Activate virtual environment if available
    source "${venv}/bin/activate"
fi

# Format code
black "${src_dir}"
isort "${src_dir}"

# Check
flake8 "${src_dir}"
pylint "${src_dir}"
mypy "${src_dir}"

echo 'OK'
