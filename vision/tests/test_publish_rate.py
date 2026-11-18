"""fusedTracks 전송 간격 제한: 프레임마다 쓰지 않고 최대 4건/초, 보낼 때는 가장 최신 프레임."""
import time

from vision4iot.publisher import OneM2MPublisher


class FakeClient:
    def __init__(self):
        self.posts = []

    def create_ae(self, ae, api):
        return 409, None

    def create_cnt(self, ae, cnt, mni):
        return 409, None

    def url(self, path):
        return path

    def post_cin(self, path, msg):
        self.posts.append((time.monotonic(), msg["frame"]))
        return 201, None


def test_publish_is_capped_and_sends_the_latest_frame():
    client = FakeClient()
    pub = OneM2MPublisher(client, "AE-VisionAI/fusedTracks", log=lambda s: None, min_interval_s=0.25)
    for frame in range(40):                 # 1초 동안 40프레임
        pub.publish({"frame": frame})
        time.sleep(0.025)
    time.sleep(0.4)
    pub.close()
    times = [t for t, _ in client.posts]
    assert 3 <= len(client.posts) <= 6
    assert all(b - a >= 0.24 for a, b in zip(times, times[1:]))
    assert client.posts[-1][1] == 39        # 마지막으로 보낸 것은 가장 최신 프레임
