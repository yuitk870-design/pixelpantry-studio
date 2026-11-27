"""Upload a video to the Pixel Pantry YouTube channel with the YouTube Data API.

Needs env: YT_CLIENT_ID, YT_CLIENT_SECRET, YT_REFRESH_TOKEN
Usage:
  python scripts/yt_upload.py --file docs/daily/2026-11-26.mp4 --title-file docs/daily/latest_title.txt \
      --desc-file docs/daily/latest_caption.txt --tags "a,b" --publish-at 2026-11-26T21:00:00+09:00

--publish-at schedules the video (uploaded private, YouTube makes it public at that time).
If that time is already past (late or re-run job), it is published right away.
A video whose title already exists among the channel's recent uploads is skipped.
"""
import datetime as dt
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


def recent_titles(token, n=25):
    """Titles of the channel's latest uploads (including scheduled/private ones)."""
    h = {"Authorization": f"Bearer {token}"}
    r = requests.get(f"{API}/channels", params={"part": "contentDetails", "mine": "true"}, headers=h, timeout=30)
    if r.status_code != 200 or not r.json().get("items"):
        print(f"could not read channel ({r.status_code}), skipping duplicate check")
        return set()
    up = r.json()["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
    r = requests.get(f"{API}/playlistItems", params={"part": "snippet", "playlistId": up, "maxResults": n},
                     headers=h, timeout=30)
    if r.status_code != 200:
        print(f"could not read uploads ({r.status_code}), skipping duplicate check")
        return set()
    return {it["snippet"]["title"].strip() for it in r.json().get("items", [])}


def upload(token, path, title, desc, tags, privacy, category="20", publish_at=None):
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
    if publish_at:
        meta["status"]["privacyStatus"] = "private"
        meta["status"]["publishAt"] = publish_at
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
    p.add_argument("--title", default="")
    p.add_argument("--title-file")
    p.add_argument("--desc", default="")
    p.add_argument("--desc-file")
    p.add_argument("--tags", default="")
    p.add_argument("--privacy", default="private", choices=["private", "unlisted", "public"])
    p.add_argument("--playlist", default="")
    p.add_argument("--publish-at", default="", help="ISO time with offset, e.g. 2026-11-27T21:00:00+09:00")
    a = p.parse_args()

    desc = a.desc
    if a.desc_file:
        with open(a.desc_file, encoding="utf-8") as f:
            desc = f.read()
    title = a.title
    if a.title_file:
        with open(a.title_file, encoding="utf-8") as f:
            title = f.read().strip()
    if not title:
        sys.exit("no title")
    tags = [t.strip() for t in a.tags.split(",") if t.strip()]

    publish_at, privacy = None, a.privacy
    if a.publish_at:
        when = dt.datetime.fromisoformat(a.publish_at)
        if when > dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=10):
            publish_at = when.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        else:
            privacy = "public"
            print("publish time already passed -> publishing now")

    token = access_token()
    if title.strip() in recent_titles(token):
        print(f"already on the channel, skipped: {title}")
        return
    video = upload(token, a.file, title, desc, tags, privacy, publish_at=publish_at)
    vid = video["id"]
    status = video.get("status", {}).get("privacyStatus")
    print(f"uploaded: https://www.youtube.com/shorts/{vid} (privacy: {status}, publishAt: {publish_at})")
    if a.playlist:
        add_to_playlist(token, a.playlist, vid)
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a") as f:
            f.write(f"video_id={vid}\n")


if __name__ == "__main__":
    main()
