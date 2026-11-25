"""Minimal client for the Instagram API with Instagram Login (graph.instagram.com)."""
from __future__ import annotations

import time
import requests


class InstagramError(RuntimeError):
    pass


class Instagram:
    def __init__(self, token: str, ig_user_id: str, host: str, version: str):
        self.token = token
        self.ig_user_id = ig_user_id
        self.base = f"{host.rstrip('/')}/{version}"
        self.host = host.rstrip("/")

    # ── low level ───────────────────────────────────────────────
    def _req(self, method: str, url: str, **params):
        params["access_token"] = self.token
        r = requests.request(method, url, params=params if method == "GET" else None,
                             data=params if method != "GET" else None, timeout=60)
        try:
            body = r.json()
        except ValueError:
            body = {"raw": r.text}
        if r.status_code >= 400 or "error" in body:
            err = body.get("error", body)
            raise InstagramError(f"{method} {url.replace(self.token, '***')} -> {r.status_code}: {err}")
        return body

    # ── account ─────────────────────────────────────────────────
    def me(self) -> dict:
        return self._req("GET", f"{self.base}/me", fields="user_id,username,account_type")

    def publishing_quota(self) -> dict:
        return self._req("GET", f"{self.base}/{self.ig_user_id}/content_publishing_limit",
                         fields="quota_usage,config")

    # ── publishing ──────────────────────────────────────────────
    def create_image_container(self, image_url: str, caption: str, alt_text: str | None = None) -> str:
        params = {"image_url": image_url, "caption": caption}
        if alt_text:
            params["alt_text"] = alt_text
        return self._req("POST", f"{self.base}/{self.ig_user_id}/media", **params)["id"]

    def create_carousel(self, image_urls: list[str], caption: str) -> str:
        children = [self._req("POST", f"{self.base}/{self.ig_user_id}/media",
                              image_url=u, is_carousel_item="true")["id"] for u in image_urls]
        return self._req("POST", f"{self.base}/{self.ig_user_id}/media", media_type="CAROUSEL",
                         children=",".join(children), caption=caption)["id"]

    def wait_until_ready(self, container_id: str, timeout: int = 300) -> None:
        deadline = time.time() + timeout
        while time.time() < deadline:
            status = self._req("GET", f"{self.base}/{container_id}", fields="status_code,status")
            code = status.get("status_code")
            if code == "FINISHED":
                return
            if code in ("ERROR", "EXPIRED"):
                raise InstagramError(f"Container {container_id} failed: {status}")
            time.sleep(5)
        raise InstagramError(f"Container {container_id} not ready after {timeout}s")

    def publish(self, container_id: str) -> str:
        return self._req("POST", f"{self.base}/{self.ig_user_id}/media_publish",
                         creation_id=container_id)["id"]

    def permalink(self, media_id: str) -> str:
        return self._req("GET", f"{self.base}/{media_id}", fields="permalink").get("permalink", "")

    # ── token ───────────────────────────────────────────────────
    def refresh_token(self) -> dict:
        """Extend a long-lived token by 60 days (token must be >24h old and unexpired)."""
        r = requests.get(f"{self.host}/refresh_access_token",
                         params={"grant_type": "ig_refresh_token", "access_token": self.token},
                         timeout=60)
        body = r.json()
        if "access_token" not in body:
            raise InstagramError(f"Token refresh failed: {body.get('error', body)}")
        return body
