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

find "${this_dir}" -name 'requirements*.txt' -type f -print0 | \
    xargs -0 -n1 pip3 ${PIP_INSTALL} -r

# -----------------------------------------------------------------------------

echo "OK"
