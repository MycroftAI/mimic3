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
# Deletes a Github release by tag name, if it exists.
#
# Assumes curl and jq are installed.
#
set -eo pipefail

owner="$1"
repo="$2"
tag="$3"
token="$4"

if [ -z "${token}" ]; then
    echo 'Usage: delete-tagged-release.sh <owner> <repo> <tag> <token>';
    exit 1;
fi

# -----------------------------------------------------------------------------

function get_release_id {
    curl \
        --silent \
        --show-error \
        -H "Authorization: token ${token}" \
        -H 'Accept: application/vnd.github.v3+json' \
        --output - \
        "https://api.github.com/repos/${owner}/${repo}/releases/tags/${tag}" | \
        jq --raw-output '.id'
}

function delete_release {
    release_id="$1"

    curl \
        --silent \
        --show-error \
        -X DELETE \
        -H 'Accept: application/vnd.github.v3+json' \
        -H "Authorization: token ${token}" \
        "https://api.github.com/repos/${owner}/${repo}/releases/${release_id}"
}

export get_release_id

release_id="$(get_release_id)"

if [ -n "${release_id}" ]; then
    delete_release "${release_id}"
    echo "Deleted: ${release_id}"
fi

echo 'OK'
