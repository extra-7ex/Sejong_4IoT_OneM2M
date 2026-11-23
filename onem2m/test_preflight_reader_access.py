"""Tests for the read-only deployment preflight."""

import contextlib
import io
import unittest
import urllib.error
from unittest.mock import patch

from onem2m import preflight_reader_access as preflight


class Response:
    def __init__(self, status):
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


class ReaderPreflightTests(unittest.TestCase):
    def test_requests_expected_resources_with_separate_origins(self):
        requests = []

        def open_request(request, timeout):
            requests.append((request.full_url, request.get_header("X-m2m-origin"), request.get_method(), timeout))
            return Response(200)

        with patch.object(preflight.urllib.request, "urlopen", side_effect=open_request), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(preflight.main(["--cse", "http://test/TinyIoT-MN/", "--timeout", "3"]), 0)
        self.assertEqual(requests, [
            ("http://test/TinyIoT-MN/AE-VisionAI/fusedTracks/la", "CmecIPE", "GET", 3),
            ("http://test/TinyIoT-MN/AE-forklift01/radar/la", "Cbridge", "GET", 3),
            ("http://test/TinyIoT-MN/AE-riskengine/events/la", "Cbridge", "GET", 3),
        ])

    def test_forbidden_or_network_failure_blocks_switch(self):
        with patch.object(preflight.urllib.request, "urlopen", side_effect=urllib.error.HTTPError("url", 403, "denied", {}, None)), \
                contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(preflight.main(["--role", "ipe"]), 1)
        with patch.object(preflight.urllib.request, "urlopen", side_effect=urllib.error.URLError("offline")), \
                contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(preflight.main(["--role", "bridge"]), 1)

    def test_rejects_credentials_in_cse_url(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            preflight.main(["--cse", "http://user:password@example.com/TinyIoT-MN"])


if __name__ == "__main__":
    unittest.main()
