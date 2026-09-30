# Dev-only static server: like `python -m http.server`, plus Cache-Control: no-cache so edited css/js show up on a normal reload.
import sys
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer, test
from pathlib import Path


class NoCacheHandler(SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cache-Control", "no-cache")
        super().end_headers()


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 5500
    directory = str(Path(__file__).resolve().parent / "prototype")
    test(HandlerClass=partial(NoCacheHandler, directory=directory), ServerClass=ThreadingHTTPServer, port=port, bind="127.0.0.1")
