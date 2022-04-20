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
# Creates source distributions for PyPI.
#
set -euo pipefail

# Directory of *this* script
this_dir="$( cd "$( dirname "$0" )" && pwd )"

dist_dir="${this_dir}/dist"
mkdir -p "${dist_dir}"

for module_dir in opentts-abc mimic3-tts mimic3-http; do
    # Kebab to snake case
    module_name="$(echo "${module_dir}" | sed -e 's/-/_/g')"

    pushd "${this_dir}/${module_dir}"
    python3 setup.py sdist
    cp "dist/${module_name}"-*.tar.gz "${dist_dir}/"
    popd
done
