"""jpfdevs.pentest Instagram auto-poster.

Usage:
  python -m bot preview [--market us|br] [--id POST_ID]   render cards to ./preview/
  python -m bot next --market us|br                        show which post would go out next
  python -m bot post --market us|br [--id POST_ID] [--dry-run]
  python -m bot check                                      verify token, account and quota
  python -m bot refresh-token                              print a refreshed long-lived token

Environment:
  IG_ACCESS_TOKEN   long-lived Instagram User access token (Instagram Login)
  IG_USER_ID        Instagram professional account ID
  IMAGE_HOSTING     "github" (default in GitHub Actions) or "base_url"
  IMAGE_BASE_URL    when IMAGE_HOSTING=base_url: public URL that serves ./published/
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import requests
import yaml

from .instagram import Instagram, InstagramError
from .render import render_post, render_story

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "state" / "posted.json"
PUBLISHED = ROOT / "published"


# ── helpers ─────────────────────────────────────────────────────
def load_cfg() -> dict:
    return yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))


def load_posts() -> list[dict]:
    posts = yaml.safe_load((ROOT / "content" / "posts.yaml").read_text(encoding="utf-8"))
    ids = [p["id"] for p in posts]
    dupes = {i for i in ids if ids.count(i) > 1}
    if dupes:
        sys.exit(f"Duplicate post ids in content/posts.yaml: {dupes}")
    return posts


def load_state() -> dict:
    return json.loads(STATE.read_text()) if STATE.exists() else {"history": []}


def save_state(state: dict) -> None:
    STATE.parent.mkdir(exist_ok=True)
    STATE.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n")


def build_caption(post: dict, cfg: dict) -> str:
    c = cfg["contact"]
    m = cfg["markets"][post["market"]]
    text = post["caption"].format(cta=m["cta"], email=c.get("email", ""),
                                  website=c.get("website", ""), whatsapp=c.get("whatsapp_br", ""))
    text = "\n".join(l for l in text.splitlines() if l.strip() not in ("📧", "🌐", "📱"))
    caption = f"{text.strip()}\n\n{post.get('hashtags', '').strip()}".strip()
    if len(caption) > 2200:
        sys.exit(f"Caption for {post['id']} exceeds Instagram's 2200-character limit")
    if caption.count("#") > 30:
        sys.exit(f"Caption for {post['id']} has more than 30 hashtags")
    return caption


def pick_next(posts: list[dict], state: dict, market: str, cfg: dict) -> dict | None:
    pool = [p for p in posts if p["market"] == market]
    last_used = {}
    for h in state["history"]:
        last_used[h["id"]] = h["published_at"]
    unused = [p for p in pool if p["id"] not in last_used]
    if unused:
        return unused[0]
    pub = cfg["publishing"]
    if not pub.get("recycle_when_exhausted"):
        return None
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=pub.get("recycle_min_days", 60))
    eligible = [p for p in pool if dt.datetime.fromisoformat(last_used[p["id"]]) < cutoff]
    return min(eligible, key=lambda p: last_used[p["id"]]) if eligible else None


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, check=True, capture_output=True, text=True).stdout.strip()


def host_images(paths: list[Path]) -> list[str]:
    """Make images publicly reachable and return their URLs (one commit for all in github mode)."""
    mode = os.getenv("IMAGE_HOSTING") or ("github" if os.getenv("GITHUB_ACTIONS") else "base_url")
    if mode == "base_url":
        base = os.getenv("IMAGE_BASE_URL")
        if not base:
            sys.exit("Set IMAGE_BASE_URL (public URL serving ./published/) or IMAGE_HOSTING=github")
        return [f"{base.rstrip('/')}/{p.name}" for p in paths]
    # github: commit the images, push, and use the immutable raw URLs of that commit
    repo = os.getenv("GITHUB_REPOSITORY") or sys.exit("GITHUB_REPOSITORY not set")
    rels = [p.relative_to(ROOT).as_posix() for p in paths]
    git("add", *rels)
    staged = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=ROOT).returncode != 0
    if staged:  # new or changed images -> commit and push
        git("commit", "-m", f"images: {paths[0].stem}")
        git("push")
    # else: identical images already committed by an earlier run; reuse them
    sha = git("rev-parse", "HEAD")
    return [f"https://raw.githubusercontent.com/{repo}/{sha}/{r}" for r in rels]


def wait_public(url: str, timeout: int = 120) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = requests.head(url, timeout=20, allow_redirects=True)
            if r.status_code == 200 and r.headers.get("content-type", "").startswith("image/"):
                return
        except requests.RequestException:
            pass
        time.sleep(5)
    sys.exit(f"Image is not publicly reachable as an image: {url}\n"
             "If you use IMAGE_HOSTING=github, the repository must be public.")


def client(cfg: dict) -> Instagram:
    token, uid = os.getenv("IG_ACCESS_TOKEN"), os.getenv("IG_USER_ID")
    if not token or not uid:
        sys.exit("IG_ACCESS_TOKEN and IG_USER_ID must be set")
    pub = cfg["publishing"]
    return Instagram(token, uid, pub["host"], pub["api_version"])


# ── commands ────────────────────────────────────────────────────
def cmd_preview(a, cfg, posts):
    out = ROOT / "preview"
    sel = [p for p in posts if (not a.market or p["market"] == a.market) and (not a.id or p["id"] == a.id)]
    for p in sel:
        render_post(p, cfg, out / f"{p['id']}.jpg")
        (out / f"{p['id']}.txt").write_text(build_caption(p, cfg), encoding="utf-8")
        print(f"rendered {p['id']}")
    print(f"{len(sel)} card(s) + captions in {out}")


def cmd_next(a, cfg, posts):
    p = pick_next(posts, load_state(), a.market, cfg)
    if not p:
        print("Nothing eligible to post.")
        return
    print(f"Next for {a.market}: {p['id']}\n\n{build_caption(p, cfg)}")


def cmd_post(a, cfg, posts):
    state = load_state()
    if a.id:
        post = next((p for p in posts if p["id"] == a.id), None) or sys.exit(f"No post {a.id}")
    else:
        post = pick_next(posts, state, a.market, cfg)
        if not post:
            print(f"No eligible post for market '{a.market}'. Add content to content/posts.yaml.")
            return
    caption = build_caption(post, cfg)
    stem = f"{post['id']}-{dt.date.today():%Y%m%d}"
    img = render_post(post, cfg, PUBLISHED / f"{stem}.jpg")
    want_story = cfg["publishing"].get("also_story", True) and not a.no_story
    story_img = render_story(img, post, cfg, PUBLISHED / f"{stem}-story.jpg") if want_story else None
    print(f"Selected {post['id']}  ->  {img.name}" + (f" + {story_img.name}" if story_img else ""))
    if a.dry_run:
        print("--- DRY RUN: caption ---\n" + caption)
        return

    ig = client(cfg)
    urls = host_images([img] + ([story_img] if story_img else []))
    for u in urls:
        print(f"Image URL: {u}")
        wait_public(u)

    # feed post
    try:
        cid = ig.create_image_container(urls[0], caption, post.get("alt"))
        ig.wait_until_ready(cid)
        media_id = ig.publish(cid)
    except InstagramError as e:
        sys.exit(f"Publishing failed: {e}")
    link = ""
    try:
        link = ig.permalink(media_id)
    except InstagramError:
        pass
    entry = {"id": post["id"], "market": post["market"], "media_id": media_id, "permalink": link,
             "published_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}
    print(f"✅ Published {post['id']}  media_id={media_id}  {link}")

    # story (a failure here does not undo the feed post)
    if story_img:
        try:
            sid = ig.create_story_container(urls[1])
            ig.wait_until_ready(sid)
            entry["story_id"] = ig.publish(sid)
            print(f"✅ Story published  media_id={entry['story_id']}")
        except InstagramError as e:
            print(f"::warning::Feed post is live, but the story failed: {e}")

    state["history"].append(entry)
    save_state(state)


def cmd_check(a, cfg, posts):
    ig = client(cfg)
    print("Account:", json.dumps(ig.me()))
    print("Quota:  ", json.dumps(ig.publishing_quota()))
    for m in cfg["markets"]:
        n = pick_next(posts, load_state(), m, cfg)
        print(f"Next {m}: {n['id'] if n else '—'}")


def cmd_refresh(a, cfg, posts):
    body = client(cfg).refresh_token(os.getenv("FB_APP_ID"), os.getenv("FB_APP_SECRET"))
    days = int(body.get("expires_in", 0)) // 86400
    print(f"Refreshed. Valid for ~{days} days.", file=sys.stderr)
    print(body["access_token"])


def main():
    ap = argparse.ArgumentParser(prog="bot")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("preview"); p.add_argument("--market"); p.add_argument("--id")
    p = sub.add_parser("next"); p.add_argument("--market", required=True, choices=["us", "br"])
    p = sub.add_parser("post"); p.add_argument("--market", choices=["us", "br"]); p.add_argument("--id")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--no-story", action="store_true", help="feed post only")
    sub.add_parser("check"); sub.add_parser("refresh-token")
    a = ap.parse_args()
    if a.cmd == "post" and not (a.market or a.id):
        ap.error("post needs --market or --id")
    cfg, posts = load_cfg(), load_posts()
    {"preview": cmd_preview, "next": cmd_next, "post": cmd_post, "check": cmd_check,
     "refresh-token": cmd_refresh}[a.cmd](a, cfg, posts)


if __name__ == "__main__":
    main()
