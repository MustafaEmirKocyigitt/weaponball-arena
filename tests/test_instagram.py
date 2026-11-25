from pathlib import Path

import pytest

from arena.publish import instagram as igmod
from arena.publish.instagram import Instagram, InstagramError


class Resp:
    def __init__(self, data, status=200):
        self._d, self.status_code, self.text = data, status, str(data)

    def json(self):
        return self._d


def test_full_publish_flow(monkeypatch, tmp_path: Path):
    video = tmp_path / "v.mp4"
    video.write_bytes(b"x" * 1000)
    calls = []

    def post(url, data=None, headers=None, timeout=None):
        calls.append(("POST", url, headers))
        if url.endswith("/me/media"):
            assert data["media_type"] == "REELS" and data["upload_type"] == "resumable"
            return Resp({"id": "C1", "uri": "https://rupload.facebook.com/ig-api-upload/v23.0/C1"})
        if "rupload" in url:
            assert headers["file_size"] == "1000" and headers["Authorization"] == "OAuth TOKEN"
            return Resp({"success": True})
        if url.endswith("/media_publish"):
            assert data["creation_id"] == "C1"
            return Resp({"id": "M9"})
        raise AssertionError(url)

    states = iter(["IN_PROGRESS", "FINISHED"])

    def get(url, params=None, timeout=None):
        return Resp({"status_code": next(states)})

    monkeypatch.setattr(igmod.requests, "post", post)
    monkeypatch.setattr(igmod.requests, "get", get)
    monkeypatch.setattr(igmod.time, "sleep", lambda s: None)
    monkeypatch.setenv("IG_ACCESS_TOKEN", "TOKEN")
    monkeypatch.delenv("IG_USER_ID", raising=False)
    media = igmod.post_reel(video, "hello", {"instagram": {}}, None, log=lambda *_: None)
    assert media == "M9"
    assert [c[1].rsplit("/", 1)[-1] for c in calls] == ["media", "C1", "media_publish"]


def test_errors_do_not_leak_token(monkeypatch):
    monkeypatch.setattr(igmod.requests, "post",
                        lambda *a, **k: Resp({"error": {"message": "Invalid OAuth access token"}}, 400))
    ig = Instagram("SECRET123", log=lambda *_: None)
    with pytest.raises(InstagramError) as e:
        ig.create_container("x")
    assert "SECRET123" not in str(e.value)


def test_missing_token():
    with pytest.raises(InstagramError):
        Instagram("")
