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

RUN mkdir -p /home/mimic3/app
WORKDIR /home/mimic3/app

# Create virtual environment
RUN --mount=type=cache,id=pip-venv,target=/root/.cache/pip \
   python3 -m venv .venv && \
   .venv/bin/pip3 install --upgrade pip && \
   .venv/bin/pip3 install --upgrade wheel setuptools

COPY ./ /home/mimic3/app/

# Install packages in order
RUN --mount=type=cache,id=pip-requirements,target=/root/.cache/pip \
   .venv/bin/pip3 install -e opentts-abc && \
   .venv/bin/pip3 install -e mimic3-tts && \
   .venv/bin/pip3 install -e mimic3-http

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
        python3 ca-certificates

RUN useradd -ms /bin/bash mimic3

# Copy virtual environment and source code
COPY --from=build /home/mimic3/app/ /home/mimic3/app/

USER mimic3
WORKDIR /home/mimic3/app

EXPOSE 59125

ENTRYPOINT ["/home/mimic3/app/.venv/bin/python3", "-m", "mimic3_http"]
