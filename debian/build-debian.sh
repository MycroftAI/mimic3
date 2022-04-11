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
# Script for building Debian packages from PyInstaller binaries.
#
# Before running this script, you must build PyInstaller binaries with "make
# binaries" or by manually invoking Dockerfile.binary.
# -----------------------------------------------------------------------------
set -euo pipefail

# Directory of *this* script
this_dir="$( cd "$( dirname "$0" )" && pwd )"
src_dir="$(realpath "${this_dir}/..")"
dist_dir="${src_dir}/dist/linux"

voices_dir="${src_dir}/../mimic3-voices/voices"
src_voice_dir="${voices_dir}/en_UK/apope_low"

version="$(cat "${src_dir}/mimic3-tts/mimic3_tts/VERSION")"

if [ -z "$1" ]; then
    # All platforms
    platforms=('amd64' 'arm64' 'arm/v7')
else
    # Only platforms from command-line arguments
    platforms=("$@")
fi

# Create Debian package for each platform
for platform in "${platforms[@]}"; do
    platform_dir="${dist_dir}/${platform}"
    if [ -d "${platform_dir}" ]; then
        # Create temporary directory for building
        temp_dir="$(mktemp -d)"
        function cleanup {
            rm -rf "${temp_dir}";
        }
        trap cleanup EXIT

        package_dir="${temp_dir}/mimic3-tts"
        mkdir -p "${package_dir}"

        # Fix Debian arch name
        case "${platform}" in
            arm/v7)
                debian_arch='armhf'
                ;;

            *)
                debian_arch="${platform}"
                ;;
        esac

        # Create control file
        mkdir -p "${package_dir}/DEBIAN"
        VERSION="${version}" DEBIAN_ARCH="${debian_arch}" \
            envsubst \
            < "${src_dir}/debian/control.in" \
            > "${package_dir}/DEBIAN/control"

        # Copy artifacts
        mkdir -p "${package_dir}/usr/lib/mimic3-tts"
        rsync -av "${platform_dir}/mimic3/" "${package_dir}/usr/lib/mimic3-tts/"

        # Copy scripts
        mkdir -p "${package_dir}/usr/bin/"
        rsync -av "${this_dir}/bin/" "${package_dir}/usr/bin/"

        # Copy default voice
        dest_voice_dir="${package_dir}/usr/share/mimic3/voices/en_UK/apope_low"
        mkdir -p "${dest_voice_dir}"
        rsync -av "${src_voice_dir}/" "${dest_voice_dir}/"

        # Build Debian package
        pushd "${temp_dir}" 2>/dev/null
        dpkg --build 'mimic3-tts'
        dpkg-name ./*.deb
        cp ./*.deb "${src_dir}/dist/"
        popd 2>/dev/null
    fi
done
