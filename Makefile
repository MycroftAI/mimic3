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
.PHONY: dist install docker docker-gpu debian sample plugin-dist

SHELL := bash

# linux/amd64,linux/arm64,linux/arm/v7
DOCKER_PLATFORM ?= linux/amd64
DOCKER_OUTPUT ?=
DOCKER_TAG ?= mycroftai/mimic3

# Build source distributions for PyPI.
# Also tests installation.
dist:
	docker buildx build . -f Dockerfile.dist --platform "$(DOCKER_PLATFORM)" --output 'type=local,dest=dist/'; \

# Create virtual environment and install in editable mode locally.
install:
	./install.sh

# Create self-contained Docker image.
# Also tests functionality.
docker:
	echo "$(DOCKER_TAG)" | sed -e 's/,/\n/g' | \
        while read -r tag; do \
            docker buildx build . -f Dockerfile --platform "$(DOCKER_PLATFORM)" --tag "$${tag}" $(DOCKER_OUTPUT); \
        done

# Create self-container Docker image with GPU support.
# Requires nvidia-docker.
docker-gpu:
	docker buildx build . -f Dockerfile.gpu --tag "$(DOCKER_TAG):gpu" $(DOCKER_OUTPUT)

# Create sample WAV files that are elsewhere for testing.
# These are different per platform (amd64, etc.).
# It's critical that deterministic mode is used to generate and test.
sample:
	docker buildx build . -f Dockerfile.sample --platform "$(DOCKER_PLATFORM)" --output 'type=local,dest=tests/'; \

# Create Debian packages (packaged with apope voice).
# Also tests installation.
debian:
	docker buildx build . -f Dockerfile.debian --platform "$(DOCKER_PLATFORM)" --output 'type=local,dest=dist/'; \

# Build TTS plugin distribution package.
# https://github.com/MycroftAI/plugin-tts-mimic3
#
# Also tests with latest Mycroft.
# Cannot run tests in parallel because of message bus port conflicts.
plugin-dist:
	echo "$(DOCKER_PLATFORM)" | sed -e 's/,/\n/g' | \
        while read -r platform; do \
            docker buildx build . -f Dockerfile.plugin --platform "$${platform}" --output 'type=local,dest=dist/'; \
        done
