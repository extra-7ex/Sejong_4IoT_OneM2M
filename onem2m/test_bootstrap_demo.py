import unittest

from onem2m.bootstrap_demo import SetupError, ensure_policy, has_create, valid_base


class FakeCse:
    def __init__(self, resources):
        self.resources = resources
        self.calls = []

    def request(self, method, path, ty=None, body=None):
        self.calls.append((method, path, body))
        if method == "GET":
            return (200, self.resources[path]) if path in self.resources else (404, None)
        raise AssertionError(f"unexpected mutation: {method} {path}")


class BootstrapTest(unittest.TestCase):
    def test_existing_policy_must_not_include_extra_permissions(self):
        policy = {"m2m:acp": {
            "pv": {"acr": [{"acor": ["CAdmin"], "acop": 63},
                            {"acor": ["Criskengine"], "acop": 3}]},
            "pvs": {"acr": [{"acor": ["CAdmin"], "acop": 63}]},
        }}
        cse = FakeCse({"/acp": policy})
        with self.assertRaises(SetupError):
            ensure_policy(cse, "TinyIoT", "", "acp",
                          [("CAdmin", 63), ("Criskengine", 1)])
        self.assertEqual([call[0] for call in cse.calls], ["GET"])

    def test_existing_policy_must_not_allow_extra_administrators(self):
        policy = {"m2m:acp": {
            "pv": {"acr": [{"acor": ["CAdmin"], "acop": 63}]},
            "pvs": {"acr": [{"acor": ["CAdmin", "all"], "acop": 63}]},
        }}
        cse = FakeCse({"/acp": policy})
        with self.assertRaises(SetupError):
            ensure_policy(cse, "TinyIoT", "", "acp", [("CAdmin", 63)])
        self.assertEqual([call[0] for call in cse.calls], ["GET"])

    def test_worker_create_permission_is_checked_without_changes(self):
        policy = {"m2m:acp": {"pv": {"acr": [{"acor": ["Criskengine"], "acop": 1}]}}}
        cse = FakeCse({"/AE-worker01/acp-worker01": policy})
        cnt = {"acpi": ["TinyIoT/AE-worker01/acp-worker01"]}
        self.assertTrue(has_create(cse, "TinyIoT", cnt, "Criskengine"))
        self.assertFalse(has_create(cse, "TinyIoT", cnt, "Cother"))
        self.assertTrue(all(call[0] == "GET" for call in cse.calls))

    def test_rejects_credentials_and_non_http_urls(self):
        for url in ("file:///tmp/TinyIoT", "http://user:pass@host/TinyIoT",
                    "http://host/TinyIoT?query=1", "http://host/"):
            with self.subTest(url=url), self.assertRaises(Exception):
                valid_base(url)
        self.assertEqual(valid_base("http://host:3000/TinyIoT/"), "http://host:3000/TinyIoT")


if __name__ == "__main__":
    unittest.main()
