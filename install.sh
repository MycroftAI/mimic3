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
# Creates a virtual environment and installs local Python modules in editable
# mode (-e).
#
# Development dependencies (linters, etc.) will be installed if 'develop' is
# given as an argument.
#
set -eo pipefail

# Directory of *this* script
this_dir="$( cd "$( dirname "$0" )" && pwd )"

# Path to virtual environment
: "${venv:=${this_dir}/.venv}"

# Python binary to use
: "${PYTHON=python3}"

# pip install command
if [ -z "${PIP_INSTALL}" ]; then
    PIP_INSTALL="install -f "${this_dir}/wheels" -f https://synesthesiam.github.io/prebuilt-apps/"
fi

python_version="$(${PYTHON} --version)"

# Create virtual environment
echo "Creating virtual environment at ${venv} (${python_version})"
rm -rf "${venv}"
"${PYTHON}" -m venv "${venv}"
source "${venv}/bin/activate"

# Install Python dependencies
echo 'Installing Python dependencies'
pip3 ${PIP_INSTALL} --upgrade pip
pip3 ${PIP_INSTALL} --upgrade wheel setuptools

# Install Mimic 3
pushd "${this_dir}/" 2>/dev/null
pip3 ${PIP_INSTALL} -e '.[all]'
popd 2>/dev/null

if [ "$1" = 'develop' ]; then
    pip3 ${PIP_INSTALL} -r "${this_dir}/requirements_dev.txt"
fi

# -----------------------------------------------------------------------------

echo "OK"
