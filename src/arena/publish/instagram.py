"""Publish a Reel through the Instagram API (Instagram Login flavour).

Flow: create a resumable REELS container -> upload the mp4 bytes to
rupload.facebook.com -> wait until processing is FINISHED -> (wait for the
post time) -> media_publish.

Uses graph.facebook.com with a never-expiring Meta Business system-user
token. Credentials: IG_ACCESS_TOKEN env var (required); the Instagram
account ID comes from config.yaml (IG_USER_ID env overrides). The token is
never printed.
"""
from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

RUPLOAD = "https://rupload.facebook.com/ig-api-upload/{ver}/{container}"


class InstagramError(RuntimeError):
    pass


class Instagram:
    def __init__(self, token: str, user_id: str = "me", host: str = "https://graph.instagram.com",
                 version: str = "v23.0", log=print):
        if not token:
            raise InstagramError("IG_ACCESS_TOKEN is not set")
        self.token = token
        self.user = user_id or "me"
        self.host = host.rstrip("/")
        self.ver = version
        self.log = log

    @classmethod
    def from_env(cls, cfg: dict, log=print) -> "Instagram":
        ig = cfg.get("instagram", {})
        user = os.environ.get("IG_USER_ID") or str(ig.get("user_id") or "me")
        return cls(os.environ.get("IG_ACCESS_TOKEN", ""), user,
                   ig.get("api_host", "https://graph.facebook.com"), ig.get("api_version", "v23.0"), log)

    def whoami(self) -> dict:
        """Cheap read-only call to verify the token can see the Instagram account."""
        r = requests.get(self._url(self.user), timeout=30,
                         params={"fields": "id,username", "access_token": self.token})
        return self._check(r, "account lookup")

    # -------------------------------------------------------------- helpers
    def _url(self, path: str) -> str:
        return f"{self.host}/{self.ver}/{path.lstrip('/')}"

    def _check(self, r: requests.Response, what: str) -> dict:
        try:
            data = r.json()
        except ValueError:
            data = {"raw": r.text[:300]}
        if r.status_code >= 400 or "error" in data:
            err = data.get("error", data)
            msg = err.get("message") if isinstance(err, dict) else str(err)
            raise InstagramError(f"{what} failed (HTTP {r.status_code}): {msg}")
        return data

    # -------------------------------------------------------------- steps
    def create_container(self, caption: str) -> tuple[str, str]:
        r = requests.post(self._url(f"{self.user}/media"), timeout=60, data={
            "media_type": "REELS", "upload_type": "resumable", "caption": caption,
            "share_to_feed": "true", "access_token": self.token})
        d = self._check(r, "create container")
        cid = d["id"]
        uri = d.get("uri") or RUPLOAD.format(ver=self.ver, container=cid)
        self.log(f"[ig] container {cid} created")
        return cid, uri

    def upload(self, uri: str, video: Path):
        data = Path(video).read_bytes()
        r = requests.post(uri, data=data, timeout=600, headers={
            "Authorization": f"OAuth {self.token}", "offset": "0", "file_size": str(len(data))})
        self._check(r, "video upload")
        self.log(f"[ig] uploaded {len(data) / 1e6:.1f} MB")

    def wait_ready(self, cid: str, timeout_s: float = 1200, poll_s: float = 10):
        start = time.time()
        while time.time() - start < timeout_s:
            r = requests.get(self._url(cid), timeout=30,
                             params={"fields": "status_code,status", "access_token": self.token})
            d = self._check(r, "container status")
            code = d.get("status_code")
            if code == "FINISHED":
                self.log("[ig] processing finished")
                return
            if code in ("ERROR", "EXPIRED"):
                raise InstagramError(f"container {cid} {code}: {d.get('status')}")
            time.sleep(poll_s)
        raise InstagramError(f"container {cid} not ready after {timeout_s:.0f}s")

    def publish(self, cid: str) -> str:
        r = requests.post(self._url(f"{self.user}/media_publish"), timeout=60,
                          data={"creation_id": cid, "access_token": self.token})
        d = self._check(r, "publish")
        self.log(f"[ig] published media {d.get('id')}")
        return d["id"]

    def refresh_token(self) -> tuple[str, int]:
        r = requests.get(f"{self.host}/refresh_access_token", timeout=30,
                         params={"grant_type": "ig_refresh_token", "access_token": self.token})
        d = self._check(r, "token refresh")
        return d["access_token"], int(d.get("expires_in", 0))


def sleep_until(when_utc: datetime, log=print):
    while True:
        left = (when_utc - datetime.now(timezone.utc)).total_seconds()
        if left <= 0:
            return
        if left > 60:
            log(f"[ig] waiting {left / 60:.1f} min until post time")
        time.sleep(min(left, 300))


def post_reel(video: Path, caption: str, cfg: dict, post_at_utc: datetime | None = None, log=print) -> str:
    ig = Instagram.from_env(cfg, log)
    cid, uri = ig.create_container(caption)
    ig.upload(uri, video)
    ig.wait_ready(cid, timeout_s=cfg.get("instagram", {}).get("publish_wait_timeout_minutes", 20) * 60)
    if post_at_utc:
        sleep_until(post_at_utc, log)
    return ig.publish(cid)
