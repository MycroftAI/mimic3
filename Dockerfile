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
# Dockerfile for Mimic 3 (https://github.com/MycroftAI/mimic3)
#
# Runs an HTTP server on port 59125.
# See scripts in docker/ directory of this repository.
#
# Requires Docker buildx: https://docs.docker.com/buildx/working-with-buildx/
# -----------------------------------------------------------------------------

FROM debian:bullseye as build
ARG TARGETARCH
ARG TARGETVARIANT

ENV LANG C.UTF-8
ENV DEBIAN_FRONTEND=noninteractive

RUN echo "Dir::Cache var/cache/apt/${TARGETARCH}${TARGETVARIANT};" > /etc/apt/apt.conf.d/01cache

COPY debian/control.in.* ./debian/

# Use dependencies from Debian package control file
RUN --mount=type=cache,id=apt-build,target=/var/cache/apt \
    mkdir -p /var/cache/apt/${TARGETARCH}${TARGETVARIANT}/archives/partial && \
    apt-get update && \
    grep 'Depends:' "debian/control.in.${TARGETARCH}${TARGETVARIANT}" | cut -d' ' -f2- | sed -e 's/,/\n/g' | \
    xargs apt-get install --yes --no-install-recommends \
        python3 python3-pip python3-venv \
        build-essential python3-dev


WORKDIR /home/mimic3/app

COPY wheels/ ./wheels/

COPY opentts_abc/ ./opentts_abc/
COPY mimic3_http/ ./mimic3_http/
COPY mimic3_tts/ ./mimic3_tts/
COPY LICENSE MANIFEST.in README.md setup.py requirements.txt ./
COPY install.sh ./

# Install mimic3
RUN --mount=type=cache,id=pip-requirements,target=/root/.cache/pip \
    ./install.sh

# Download default voice
COPY voices/ /root/.local/share/mycroft/mimic3/voices/
RUN .venv/bin/mimic3-download --debug 'en_UK/apope_low'

# -----------------------------------------------------------------------------

FROM debian:bullseye as run
ARG TARGETARCH
ARG TARGETVARIANT

ENV LANG C.UTF-8
ENV DEBIAN_FRONTEND=noninteractive

RUN echo "Dir::Cache var/cache/apt/${TARGETARCH}${TARGETVARIANT};" > /etc/apt/apt.conf.d/01cache

WORKDIR /home/mimic3/app

COPY debian/control.in.* ./debian/

# Use dependencies from Debian package control file
RUN --mount=type=cache,id=apt-run,target=/var/cache/apt \
    mkdir -p /var/cache/apt/${TARGETARCH}${TARGETVARIANT}/archives/partial && \
    apt-get update && \
    grep 'Depends:' "debian/control.in.${TARGETARCH}${TARGETVARIANT}" | cut -d' ' -f2- | sed -e 's/,/\n/g' | \
    xargs apt-get install --yes --no-install-recommends \
        python3 ca-certificates

RUN useradd -ms /bin/bash mimic3

# Copy virtual environment and source code
COPY --from=build /home/mimic3/app/ ./

# Copy pre-downloaded voice(s)
COPY --from=build /root/.local/share/mycroft/mimic3/voices/ /usr/share/mycroft/mimic3/voices/

# Run test
COPY tests/* ./tests/

# Generate sample and check
RUN export expected_sample="tests/apope_sample_${TARGETARCH}${TARGETVARIANT}.wav" && \
    .venv/bin/mimic3 \
    --deterministic \
    --voice 'en_UK/apope_low' \
    < tests/apope_sample.txt \
    > tests/actual_sample.wav && \
    tests/samples_match.py tests/actual_sample.wav "${expected_sample}"

USER mimic3

EXPOSE 59125

ENTRYPOINT ["/home/mimic3/app/.venv/bin/python3", "-m", "mimic3_http"]
