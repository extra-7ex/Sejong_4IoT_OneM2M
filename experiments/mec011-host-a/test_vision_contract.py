"""Use repository Vision functions on synthetic inputs; no camera or real sensor."""
import json
import unittest
from types import SimpleNamespace
from fused_freshness import assess
from vision4iot.fusion import CamPerson, fuse, message

class VisionContractTests(unittest.TestCase):
    def envelope(self, radar, cameras, cam_ok=True):
        tracks = fuse(radar, cameras, cam_ok=cam_ok, in_view=lambda x, y: True)
        payload = message(100.0, 5, cam_ok, tracks, radar_ok=True, now=100.1)
        return {'m2m:cin': {'con': json.dumps(payload)}}, tracks

    def test_camera_only(self):
        cin, tracks = self.envelope([], [CamPerson(3, 0.2, 2.0, 'crouching', .9)])
        self.assertEqual(assess(cin, 101), 'OK')
        self.assertEqual((tracks[0]['state'], tracks[0]['advice']), ('camera_only', 'raise'))

    def test_confirmed(self):
        radar = [SimpleNamespace(id=1, x=.2, y=2., dist=2.01, v=-.5)]
        cin, tracks = self.envelope(radar, [CamPerson(3, .2, 2., 'standing', .9)])
        self.assertEqual(assess(cin, 101), 'OK')
        self.assertEqual((tracks[0]['state'], tracks[0]['radar_id']), ('confirmed', 1))

    def test_camera_failure(self):
        cin, _ = self.envelope([], [], cam_ok=False)
        self.assertEqual(assess(cin, 101), 'CAMERA_UNAVAILABLE')

    def test_ghost_outside_warning_is_not_output(self):
        radar = [SimpleNamespace(id=1, x=0., y=3.49, dist=3.49, v=-.5)]
        _, tracks = self.envelope(radar, [])
        self.assertEqual(tracks, [])

if __name__ == '__main__': unittest.main(verbosity=2)
