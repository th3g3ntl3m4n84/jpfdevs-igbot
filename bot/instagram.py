"""Minimal client for the Instagram API with Instagram Login (graph.instagram.com)."""
from __future__ import annotations

import time
import requests


class InstagramError(RuntimeError):
    pass


class Instagram:
    def __init__(self, token: str, ig_user_id: str, host: str, version: str):
        self.token = token.strip().strip('"').strip("'")
        self.ig_user_id = ig_user_id.strip()
        # Tokens starting with "EAA" come from Facebook Login (Page/User tokens) and
        # only work on graph.facebook.com; Instagram Login tokens ("IG...") use graph.instagram.com.
        self.facebook = self.token.startswith("EAA")
        if self.facebook:
            host = "https://graph.facebook.com"
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
        info = self._req("GET", f"{self.base}/{self.ig_user_id}", fields="id,username")
        info["token_type"] = "Facebook Login (EAA…)" if self.facebook else "Instagram Login (IG…)"
        return info

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
    def refresh_token(self, app_id: str | None = None, app_secret: str | None = None) -> dict:
        """Extend a long-lived token by 60 days."""
        if self.facebook:
            if not (app_id and app_secret):
                raise InstagramError("Facebook (EAA) tokens need FB_APP_ID and FB_APP_SECRET to refresh")
            r = requests.get(f"{self.base}/oauth/access_token",
                             params={"grant_type": "fb_exchange_token", "client_id": app_id,
                                     "client_secret": app_secret, "fb_exchange_token": self.token},
                             timeout=60)
            body = r.json()
            if "access_token" not in body:
                raise InstagramError(f"Token refresh failed: {body.get('error', body)}")
            body.setdefault("expires_in", 60 * 86400)
            return body
        r = requests.get(f"{self.host}/refresh_access_token",
                         params={"grant_type": "ig_refresh_token", "access_token": self.token},
                         timeout=60)
        body = r.json()
        if "access_token" not in body:
            raise InstagramError(f"Token refresh failed: {body.get('error', body)}")
        return body
