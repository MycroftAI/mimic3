#!/usr/bin/env bash
set -eo pipefail

# Directory of *this* script
this_dir="$( cd "$( dirname "$0" )" && pwd )"

# Path to virtual environment
: "${venv:=${this_dir}/.venv}"

# Python binary to use
: "${PYTHON=python3}"

# pip install command
: "${PIP_INSTALL=install}"

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
pip3 ${PIP_INSTALL} -e "${this_dir}/opentts-abc"

# Include support for languages besides English
pushd "${this_dir}/mimic3-tts" 2>/dev/null
pip3 ${PIP_INSTALL} -e '.[de,fr,it,nl,ru,sw]'
popd 2>/dev/null

pip3 ${PIP_INSTALL} -e "${this_dir}/mimic3-http"

# -----------------------------------------------------------------------------

echo "OK"
