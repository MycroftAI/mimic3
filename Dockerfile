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

RUN --mount=type=cache,id=apt-build,target=/var/cache/apt \
   mkdir -p /var/cache/apt/${TARGETARCH}${TARGETVARIANT}/archives/partial && \
   apt-get update && \
   apt-get install --yes --no-install-recommends \
       python3 python3-pip python3-venv \
       build-essential python3-dev

WORKDIR /home/mimic3/app

COPY opentts-abc/ ./opentts-abc/
COPY mimic3-http/ ./mimic3-http/
COPY mimic3-tts/ ./mimic3-tts/
COPY install.sh ./

# Install mimic3
RUN --mount=type=cache,id=pip-requirements,target=/root/.cache/pip \
    PIP_INSTALL='install -f https://synesthesiam.github.io/prebuilt-apps/' \
    ./install.sh

# Download default voice
COPY voices/ /root/.local/share/mimic3/voices/
RUN .venv/bin/mimic3-download 'en_UK/apope_low'

# -----------------------------------------------------------------------------

FROM debian:bullseye as run
ARG TARGETARCH
ARG TARGETVARIANT

ENV LANG C.UTF-8
ENV DEBIAN_FRONTEND=noninteractive

RUN echo "Dir::Cache var/cache/apt/${TARGETARCH}${TARGETVARIANT};" > /etc/apt/apt.conf.d/01cache

RUN --mount=type=cache,id=apt-run,target=/var/cache/apt \
    mkdir -p /var/cache/apt/${TARGETARCH}${TARGETVARIANT}/archives/partial && \
    apt-get update && \
    apt-get install --yes --no-install-recommends \
        python3 ca-certificates libespeak-ng1 libatomic1 libgomp1

RUN useradd -ms /bin/bash mimic3

# Copy virtual environment and source code
COPY --from=build /home/mimic3/app/ /home/mimic3/app/

# Copy pre-downloaded voice(s)
COPY --from=build /root/.local/share/mimic3/voices/ /usr/share/mimic3/voices/

WORKDIR /home/mimic3/app

# Run test
COPY tests/apope_sample.txt tests/apope_sample_*.wav tests/

# Generate sample and check
RUN export expected_sample="tests/apope_sample_${TARGETARCH}${TARGETVARIANT}.wav" && \
    .venv/bin/mimic3 \
    --deterministic \
    --voice 'en_UK/apope_low' \
    < tests/apope_sample.txt \
    > tests/actual_sample.wav && \
    diff tests/actual_sample.wav "${expected_sample}"

USER mimic3

EXPOSE 59125

ENTRYPOINT ["/home/mimic3/app/.venv/bin/python3", "-m", "mimic3_http"]
