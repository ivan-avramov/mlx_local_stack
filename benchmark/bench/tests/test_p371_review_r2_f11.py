"""P371 review r2 F11: `HttpReceiptSource.check()` accepts only 2xx and 405 as "the route exists"; every other status and
every transport error refuses before any spawn (404 / transport name P372, the rest name the status)."""
from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from bench import worker_receipts as wr


class H(BaseHTTPRequestHandler):
    status = 200

    def do_GET(self):
        self.send_response(type(self).status)
        self.end_headers()

    def log_message(self, *a):
        pass


@pytest.fixture
def endpoint():
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield "http://127.0.0.1:%d" % httpd.server_address[1]
    httpd.shutdown()
    httpd.server_close()


@pytest.mark.parametrize("status", [200, 204, 405])
def test_a_2xx_or_405_means_the_route_exists(endpoint, status):
    H.status = status
    wr.HttpReceiptSource(endpoint, timeout_s=2).check()


@pytest.mark.parametrize("status", [400, 401, 403, 500, 502, 503])
def test_every_other_status_refuses_naming_the_status(endpoint, status):
    H.status = status
    with pytest.raises(wr.ReceiptUnavailable, match=str(status)):
        wr.HttpReceiptSource(endpoint, timeout_s=2).check()


def test_404_and_a_dead_worker_name_p372(endpoint):
    H.status = 404
    with pytest.raises(wr.ReceiptUnavailable, match="P372"):
        wr.HttpReceiptSource(endpoint, timeout_s=2).check()
    with pytest.raises(wr.ReceiptUnavailable, match="P372"):
        wr.HttpReceiptSource("http://127.0.0.1:9", timeout_s=1).check()
