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
.PHONY: dist install docker binaries

SHELL := bash

# linux/amd64 linux/arm64 linux/arm/v7
DOCKER_PLATFORM ?= linux/amd64
DOCKER_OUTPUT ?= --load

dist:
	./build-dist.sh

install:
	./install.sh

docker:
	docker buildx build . -f Dockerfile --platform $(DOCKER_PLATFORM) --tag mycroftai/mimic3 $(DOCKER_OUTPUT)

docker-gpu:
	docker buildx build . -f Dockerfile.gpu --tag 'mycroftai/mimic3:gpu' $(DOCKER_OUTPUT)

binaries:
	rm -rf "dist/$(DOCKER_PLATFORM)"
	docker buildx build . -f Dockerfile.binary --platform $(DOCKER_PLATFORM) --output "type=local,dest=dist/$(DOCKER_PLATFORM)"

debian:
