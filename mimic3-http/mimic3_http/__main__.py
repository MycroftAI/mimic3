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
import asyncio
import logging
import tempfile
import threading
from queue import Queue

import hypercorn

from .app import get_app
from .args import get_args
from .synthesis import do_synthesis_proc

_LOGGER = logging.getLogger(__name__)


# -----------------------------------------------------------------------------


def main(argv=None):
    args = get_args(argv)

    if args.debug:
        logging.basicConfig(level=logging.DEBUG)

        # Override epitran
        logging.getLogger().setLevel(logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)

        # Override epitran
        logging.getLogger().setLevel(logging.INFO)

    _LOGGER.debug(args)

    # Run Web Server
    _LOGGER.info("Starting web server")
    request_queue = Queue()
    threads = [
        threading.Thread(
            target=do_synthesis_proc, args=(args, request_queue), daemon=True
        )
        for _ in range(args.num_threads)
    ]
    for thread in threads:
        thread.start()

    hyp_config = hypercorn.config.Config()
    hyp_config.bind = [f"{args.host}:{args.port}"]

    try:
        with tempfile.TemporaryDirectory(prefix="mimic3") as temp_dir:
            app = get_app(args, request_queue, temp_dir)
            asyncio.run(hypercorn.asyncio.serve(app, hyp_config))
    finally:
        # Drain queue
        while not request_queue.empty():
            request_queue.get()

        # Stop request threads
        for _ in range(args.num_threads):
            request_queue.put(None)

        for thread in threads:
            thread.join()


# -----------------------------------------------------------------------------

if __name__ == "__main__":
    main()
