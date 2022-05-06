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
from collections import defaultdict
from pathlib import Path

import setuptools
from setuptools import setup

this_dir = Path(__file__).parent
module_dir = this_dir / "mimic3_tts"

# -----------------------------------------------------------------------------

# Load README in as long description
long_description: str = ""
readme_path = this_dir / "README.md"
if readme_path.is_file():
    long_description = readme_path.read_text(encoding="utf-8")

requirements = []
requirements_path = this_dir / "requirements.txt"
if requirements_path.is_file():
    with open(requirements_path, "r", encoding="utf-8") as requirements_file:
        requirements = requirements_file.read().splitlines()

version_path = module_dir / "VERSION"
with open(version_path, "r", encoding="utf-8") as version_file:
    version = version_file.read().strip()

# -----------------------------------------------------------------------------

# dependency => [tags]
extras = {}

# Create language-specific extras
for lang in [
    "de",
    "es",
    "fa",
    "fr",
    "it",
    "nl",
    "ru",
    "sw",
]:
    extras[f"gruut[{lang}]"] = [lang]


# Add "all" tag
for tags in extras.values():
    tags.append("all")

# Invert for setup
extras_require = defaultdict(list)
for dep, tags in extras.items():
    for tag in tags:
        extras_require[tag].append(dep)

# -----------------------------------------------------------------------------

setup(
    name="mycroft_mimic3_tts",
    version=version,
    description="A fast and local neural text to speech system for Mycroft",
    url="http://github.com/MycroftAI/mimic3",
    author="Michael Hansen",
    author_email="michael.hansen@mycroft.ai",
    license="AGPLv3+",
    packages=setuptools.find_packages(),
    package_data={
        "mimic3_tts": ["VERSION", "py.typed", "voices.json"],
        "mimic3_http": [
            "VERSION",
            "py.typed",
            "templates/index.html",
            "css/bootstrap.min.css",
            "img/favicon.png",
            "img/Mimic_color.png",
            "img/Mycroft_logo_two_typeonly.png",
            "swagger.yaml",
        ],
        "opentts_abc": ["VERSION", "py.typed"],
    },
    install_requires=requirements,
    extras_require={':python_version<"3.9"': ["importlib_resources"], **extras_require},
    entry_points={
        "console_scripts": [
            "mimic3 = mimic3_tts.__main__:main",
            "mimic3-download = mimic3_tts.download:main",
            "mimic3-server = mimic3_http.__main__:main",
        ]
    },
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "Topic :: Text Processing :: Linguistic",
        "License :: OSI Approved :: GNU Affero General Public License v3",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
    ],
    keywords="mycroft tts speech mimic",
)
