#!/usr/bin/env python3
from pathlib import Path

_DIR = Path(__file__).parent

__author__ = "Michael Hansen"
__version__ = (_DIR / "VERSION").read_text().strip()
