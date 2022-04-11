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
# Builds PyInstaller binaries for all platforms.
#
set -eo pipefail

# Directory of *this* script
this_dir="$( cd "$( dirname "$0" )" && pwd )"
src_dir="$(realpath "${this_dir}/..")"

if [ -z "$1" ]; then
    # All platforms
    platforms=('linux/amd64' 'linux/arm64' 'linux/arm/v7')
else
    # Only platforms from command-line arguments
    platforms=("$@")
fi

pushd "${src_dir}"

for platform in "${platforms[@]}"; do
    DOCKER_PLATFORM="${platform}" \
        make binaries
done

popd
