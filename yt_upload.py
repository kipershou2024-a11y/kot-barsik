#!/usr/bin/env python
"""Upload Shorts / videos to a YouTube channel via the Data API v3.

One-time auth:
  python yt_upload.py url                      -> prints the Google consent URL
  python yt_upload.py exchange "<pasted_url>" -> saves yt_token.json

Usage:
  python yt_upload.py status
  python yt_upload.py upload <file> --title "..." --desc "..." \
      --tags "a,b,c" --category 23 [--thumb thumb.jpg] [--private]
"""
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CRED_PATH = Path(r"C:\Users\odino\Downloads\client_secret_309133304446_gcqk6tj338pbqmrblo5rfoslf3qnnddj_apps.json")
TOKEN_PATH = ROOT / "yt_token.json"

TOKEN_URI = "https://oauth2.googleapis.com/token"
AUTH_URI = "https://accounts.google.com/o/oauth2/v2/auth"
YT_API = "https://www.googleapis.com/youtube/v3"
YT_UPLOAD = "https://www.googleapis.com/upload/youtube/v3"
REDIRECT = "urn:ietf:wg:oauth:2.0:oob"
SCOPES = "https://www.googleapis.com/auth/youtube.upload https://www.googleapis.com/auth/youtube.readonly"
UA = "curl/8.21.0"


def creds():
    j = json.loads(CRED_PATH.read_text(encoding="utf-8"))
    install = j.get("installed") or j.get("web")
    return install["client_id"], install["client_secret"]


def _request(url, method="GET", headers=None, data=None, binary=None, raw=False):
    h = {"User-Agent": UA}
    if headers:
        h.update(headers)
    body = binary
    if body is None and data is not None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        h.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(url, data=body, headers=h, method=method)
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            payload = r.read()
            out_headers = dict(r.headers)
            return r.status, payload, out_headers
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")
        raise RuntimeError(f"HTTP {e.code} {method} {url}\n{detail[:800]}")


def _api_headers():
    tok = load_token(refresh=True)
    return {"Authorization": f"Bearer {tok['access_token']}"}


def auth_url():
    cid, _ = creds()
    return AUTH_URI + "?" + urllib.parse.urlencode({
        "client_id": cid, "redirect_uri": REDIRECT, "response_type": "code",
        "scope": SCOPES, "access_type": "offline", "prompt": "consent",
    })


def exchange(pasted):
    cid, secret = creds()
    if "code=" in pasted:
        code = urllib.parse.parse_qs(urllib.parse.urlsplit(pasted).query)["code"][0]
    else:
        code = pasted.strip()
    payload = urllib.parse.urlencode({
        "code": code, "client_id": cid, "client_secret": secret,
        "redirect_uri": REDIRECT, "grant_type": "authorization_code",
    })
    st, body, _ = _request(TOKEN_URI, method="POST",
                           headers={"Content-Type": "application/x-www-form-urlencoded"},
                           binary=payload.encode("ascii"))
    tok = json.loads(body.decode("utf-8"))
    tok["obtained_at"] = time.time()
    if "refresh_token" not in tok:
        raise RuntimeError("no refresh_token received: " + body.decode()[:400])
    TOKEN_PATH.write_text(json.dumps(tok, ensure_ascii=False, indent=2), encoding="utf-8")
    return tok


def load_token(refresh=False):
    if not TOKEN_PATH.exists():
        raise SystemExit("No token yet. Run:  python yt_upload.py url")
    tok = json.loads(TOKEN_PATH.read_text(encoding="utf-8"))
    expires = tok.get("obtained_at", 0) + tok.get("expires_in", 3600) - 60
    if refresh and (time.time() > expires or "refresh_token" in tok):
        cid, secret = creds()
        payload = urllib.parse.urlencode({
            "refresh_token": tok["refresh_token"], "client_id": cid,
            "client_secret": secret, "grant_type": "refresh_token",
        })
        st, body, _ = _request(TOKEN_URI, method="POST",
                               headers={"Content-Type": "application/x-www-form-urlencoded"},
                               binary=payload.encode("ascii"))
        nt = json.loads(body.decode("utf-8"))
        tok.update({"access_token": nt["access_token"],
                    "expires_in": nt.get("expires_in", 3600),
                    "obtained_at": time.time()})
        TOKEN_PATH.write_text(json.dumps(tok, ensure_ascii=False, indent=2), encoding="utf-8")
    return tok


def whoami():
    _, body, _ = _request(f"{YT_API}/channels?part=snippet&mine=true",
                          headers=_api_headers())
    items = json.loads(body.decode("utf-8")).get("items", [])
    if not items:
        return "No channel found on this account"
    it = items[0]
    return f"{it['snippet']['title']} (id {it['id']})"


def upload_video(file, title, desc, tags, category, thumb=None, privacy="public"):
    path = Path(file)
    size = path.stat().st_size
    meta = {
        "snippet": {
            "title": title, "description": desc,
            "tags": tags, "categoryId": str(category),
        },
        "status": {
            "privacyStatus": privacy,
            "selfDeclaredMadeForKids": False,
        },
    }
    init_q = urllib.parse.urlencode({"uploadType": "resumable", "part": "snippet,status"})
    headers = dict(_api_headers())
    headers.update({
        "Content-Type": "application/json; charset=UTF-8",
        "X-Upload-Content-Type": "video/mp4",
        "X-Upload-Content-Length": str(size),
    })
    st, body, outh = _request(f"{YT_UPLOAD}/videos?{init_q}", method="POST",
                              headers=headers, data=meta)
    location = outh.get("Location")
    if not location:
        raise RuntimeError("no upload URL returned: " + body.decode()[:400])
    print(f"[upload] init ok ({size} bytes), PUT to storage...", flush=True)
    st, body, _ = _request(location, method="PUT",
                           headers=dict(_api_headers()),
                           binary=path.read_bytes())
    res = json.loads(body.decode("utf-8"))
    vid = res["id"]
    print(f"[upload] video id {vid} -> https://youtu.be/{vid}")
    if thumb:
        thumb_path = Path(thumb)
        th_headers = dict(_api_headers())
        th_headers["Content-Type"] = "image/jpeg"
        st, body, _ = _request(
            f"{YT_UPLOAD}/thumbnails/set?videoId={vid}", method="POST",
            headers=th_headers, binary=thumb_path.read_bytes())
        print(f"[upload] thumbnail set ({st})")
    return vid


def main():
    args = sys.argv[1:]
    cmd = args[0] if args else "help"
    if cmd == "url":
        print("OPEN THIS URL IN YOUR BROWSER, LOG IN, THEN PASTE THE ADDRESS BAR URL BACK TO ME:\n\n" + auth_url())
    elif cmd == "exchange":
        if len(args) < 2:
            raise SystemExit("usage: yt_upload.py exchange <pasted_url>")
        tok = exchange(args[1])
        print("token saved")
        print("channel:", whoami())
    elif cmd == "status":
        print("channel:", whoami())
    elif cmd == "upload":
        if len(args) < 2:
            raise SystemExit("usage: yt_upload.py upload <file> --title ... --desc ... --tags a,b,c --category N [--thumb p] [--private]")
        file = args[1]
        title = None; desc = ""; tags = []; category = 23; thumb = None; privacy = "public"
        i = 2
        while i < len(args):
            a = args[i]
            if a in ("--title", "--desc", "--tags", "--category", "--thumb"):
                v = args[i + 1]; i += 2
                if a == "--title": title = v
                elif a == "--desc": desc = v
                elif a == "--tags": tags = [t.strip() for t in v.split(",") if t.strip()]
                elif a == "--category": category = int(v)
                elif a == "--thumb": thumb = v
            elif a == "--private":
                privacy = "private"; i += 1
            else:
                raise SystemExit(f"unknown arg {a}")
        if not title:
            raise SystemExit("--title required")
        whoami()
        vid = upload_video(file, title, desc, tags, category, thumb, privacy)
        print("LIVE:", f"https://youtu.be/{vid}")
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main()