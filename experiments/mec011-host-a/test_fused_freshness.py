import json
import unittest
from fused_freshness import assess

class FreshnessTests(unittest.TestCase):
    def cin(self, ts=100.0, cam_ok=True, tracks=None, stringify=True):
        value={'ts':ts,'cam_ok':cam_ok,'tracks':[] if tracks is None else tracks}
        return {'m2m:cin':{'con':json.dumps(value) if stringify else value}}
    def test_fresh_empty_and_object(self):
        self.assertEqual(assess(self.cin(), 101), 'OK')
        self.assertEqual(assess(self.cin(stringify=False), 101), 'OK')
    def test_boundary_and_old(self):
        self.assertEqual(assess(self.cin(), 103), 'OK')
        self.assertEqual(assess(self.cin(), 103.01), 'STALE')
    def test_camera_fault(self):
        self.assertEqual(assess(self.cin(cam_ok=False), 101), 'CAMERA_UNAVAILABLE')
    def test_future_clock(self):
        self.assertEqual(assess(self.cin(ts=101), 100), 'CLOCK_UNCERTAIN')
    def test_invalid(self):
        for value in ({}, {'m2m:cin':{'con':'bad'}}, self.cin(ts=True), self.cin(ts=float('nan')), self.cin(cam_ok='true'), self.cin(tracks=[1])):
            with self.subTest(value=value): self.assertEqual(assess(value, 101), 'INVALID')
    def test_stale_precedes_camera_fault(self):
        self.assertEqual(assess(self.cin(cam_ok=False), 104), 'STALE')

if __name__=='__main__': unittest.main(verbosity=2)
