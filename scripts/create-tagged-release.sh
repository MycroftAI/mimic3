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
# Creates a Github release by tag name and uploads assets.
#
# Assumes curl and jq are installed.
#
set -eo pipefail

owner="$1"
repo="$2"
tag="$3"
token="$4"

if [ -z "${token}" ]; then
    echo 'Usage: create-tagged-release.sh <owner> <repo> <tag> <token> [asset] [content-type] [asset] [content-type] ...';
    exit 1;
fi

shift 4

temp_dir="$(mktemp -d)"
function finish {
    rm -rf "${temp_dir}"
}

trap finish EXIT

# -----------------------------------------------------------------------------

function create_release {
    # Creates a new tagged release and saves response JSON
    curl \
        --silent \
        --show-error \
        -X POST \
        -H 'Accept: application/vnd.github.v3+json' \
        -H "Authorization: token ${token}" \
        -d "{\"tag_name\":\"${tag}\",\"target_commitish\":\"master\",\"name\":\"${tag}\",\"body\":\"\",\"draft\":false,\"prerelease\":false,\"generate_release_notes\":false}" \
        --output "${temp_dir}/response.json" \
        "https://api.github.com/repos/${owner}/${repo}/releases"

    echo "${temp_dir}/response.json"
}

function upload_asset {
    # Uploads an asset to a tagged release
    upload_url="$1"
    asset_path="$2"
    asset_content_type="$3"
    asset_name="$(basename "${asset_path}")"

    curl \
        --silent \
        --show-error \
        -X POST \
        -H 'Accept: application/vnd.github.v3+json' \
        -H "Authorization: token ${token}" \
        -H "Content-Type: ${asset_content_type}" \
        --output /dev/null \
        --data-binary "@${asset_path}" \
        "${upload_url}?name=${asset_name}"
}

export create_release
export upload_asset

response_json="$(create_release)"

release_id="$(jq --raw-output '.id' < "${response_json}")"
echo "Created ${release_id}"

# Remove {?name.label} from upload URL
upload_url="$(jq --raw-output '.upload_url' < "${response_json}" | sed -e 's/{[^}]\+}//g')"

# Upload assets
while [ -n "$2" ]; do
    asset_path="$1"
    if [ ! -f "${asset_path}" ]; then
        echo "Missing asset: ${asset_path}"
        exit 1;
    fi

    asset_content_type="$2"
    upload_asset "${upload_url}" "${asset_path}" "${asset_content_type}"

    echo "Uploaded ${asset_path}"
    shift 2
done

echo 'OK'
