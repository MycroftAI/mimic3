#!/usr/bin/env python3
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
"""Stub for PyInstaller"""
import argparse

parser = argparse.ArgumentParser(add_help=False)
parser.add_argument("--subprogram", choices=["server", "client", "download"])
known_args, rest_args = parser.parse_known_args()


if known_args.subprogram == "server":
    from mimic3_http.__main__ import main as http_main

    http_main(argv=rest_args)
elif known_args.subprogram == "client":
    from mimic3_http.client import main as client_main

    client_main(argv=rest_args)
elif known_args.subprogram == "download":
    from mimic3_tts.download import main as download_main

    download_main(argv=rest_args)
else:
    from mimic3_tts.__main__ import main as tts_main

    tts_main()
