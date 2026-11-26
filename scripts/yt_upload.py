"""Upload a video to the Pixel Pantry YouTube channel with the YouTube Data API.

Needs env: YT_CLIENT_ID, YT_CLIENT_SECRET, YT_REFRESH_TOKEN
Usage:
  python scripts/yt_upload.py --file docs/daily/2026-11-26.mp4 --title "..." \
      --desc-file docs/daily/latest_caption.txt --tags "a,b" --privacy private
"""
import argparse
import json
import os
import sys

import requests

TOKEN_URL = "https://oauth2.googleapis.com/token"
UPLOAD_URL = "https://www.googleapis.com/upload/youtube/v3/videos"
API = "https://www.googleapis.com/youtube/v3"


def access_token():
    r = requests.post(TOKEN_URL, data={
        "client_id": os.environ["YT_CLIENT_ID"],
        "client_secret": os.environ["YT_CLIENT_SECRET"],
        "refresh_token": os.environ["YT_REFRESH_TOKEN"],
        "grant_type": "refresh_token",
    }, timeout=30)
    if r.status_code != 200:
        sys.exit(f"token error {r.status_code}: {r.text[:300]}")
    return r.json()["access_token"]


def upload(token, path, title, desc, tags, privacy, category="20"):
    meta = {
        "snippet": {
            "title": title[:100],
            "description": desc[:5000],
            "tags": tags,
            "categoryId": category,
            "defaultLanguage": "ko",
            "defaultAudioLanguage": "ko",
        },
        "status": {
            "privacyStatus": privacy,
            "selfDeclaredMadeForKids": False,
            "containsSyntheticMedia": False,
        },
    }
    size = os.path.getsize(path)
    r = requests.post(
        UPLOAD_URL,
        params={"uploadType": "resumable", "part": "snippet,status"},
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=UTF-8",
            "X-Upload-Content-Type": "video/mp4",
            "X-Upload-Content-Length": str(size),
        },
        data=json.dumps(meta).encode("utf-8"),
        timeout=60,
    )
    if r.status_code != 200 or "Location" not in r.headers:
        sys.exit(f"upload init error {r.status_code}: {r.text[:500]}")
    with open(path, "rb") as f:
        r2 = requests.put(
            r.headers["Location"],
            headers={"Authorization": f"Bearer {token}", "Content-Type": "video/mp4"},
            data=f,
            timeout=600,
        )
    if r2.status_code not in (200, 201):
        sys.exit(f"upload error {r2.status_code}: {r2.text[:500]}")
    return r2.json()


def add_to_playlist(token, playlist_id, video_id):
    r = requests.post(
        f"{API}/playlistItems",
        params={"part": "snippet"},
        headers={"Authorization": f"Bearer {token}"},
        json={"snippet": {"playlistId": playlist_id,
                          "resourceId": {"kind": "youtube#video", "videoId": video_id}}},
        timeout=30,
    )
    if r.status_code not in (200, 201):
        print(f"playlist warning {r.status_code}: {r.text[:300]}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--file", required=True)
    p.add_argument("--title", required=True)
    p.add_argument("--desc", default="")
    p.add_argument("--desc-file")
    p.add_argument("--tags", default="")
    p.add_argument("--privacy", default="private", choices=["private", "unlisted", "public"])
    p.add_argument("--playlist", default="")
    a = p.parse_args()

    desc = a.desc
    if a.desc_file:
        with open(a.desc_file, encoding="utf-8") as f:
            desc = f.read()
    tags = [t.strip() for t in a.tags.split(",") if t.strip()]

    token = access_token()
    video = upload(token, a.file, a.title, desc, tags, a.privacy)
    vid = video["id"]
    status = video.get("status", {}).get("privacyStatus")
    print(f"uploaded: https://www.youtube.com/shorts/{vid} (privacy: {status})")
    if a.playlist:
        add_to_playlist(token, a.playlist, vid)
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a") as f:
            f.write(f"video_id={vid}\n")


if __name__ == "__main__":
    main()
