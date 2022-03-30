#!/usr/bin/env bash
set -eo pipefail

# Directory of *this* script
this_dir="$( cd "$( dirname "$0" )" && pwd )"

# Kebab to snake case
module_name="$(basename "${this_dir}" | sed -e 's/-/_/g')"
base_dir="$(realpath "${this_dir}/..")"

# Path to virtual environment
: "${venv:=${base_dir}/.venv}"

if [ -d "${venv}" ]; then
    # Activate virtual environment if available
    source "${venv}/bin/activate"
fi

python3 -m "${module_name}" "$@"
