#!/usr/bin/env python3
"""
upload_render.py — YouTube upload for delivered renders (PUBLISHING-PLAN).

Policy (docs/planning/PUBLISHING-PLAN.md): iteration renders never
upload; delivered episode cuts upload automatically as UNLISTED with
metadata generated from the production report; public/curated uploads
are a human act (pass --privacy public deliberately).

Credentials live in the gitignored `.secrets/` directory and never enter
the tree:
  .secrets/client_secrets.json   OAuth app identity (human places once —
                                 Google Cloud console > APIs > YouTube
                                 Data API v3 > OAuth client, Desktop app)
  .secrets/youtube_token.json    minted by `--auth` (one browser dance),
                                 refreshed automatically afterwards

Usage:
  .venv/bin/python tools/upload_render.py --auth        # one-time, human
  .venv/bin/python tools/upload_render.py \
      --video renders/reviews/pilot_episode.mp4 \
      --episode pilot [--report out/production/pilot/production_report.json] \
      [--privacy unlisted|private|public] [--title ...] [--dry-run]

On success the video URL is appended to the production report's
`uploads` list. Exit codes: 0 uploaded (or dry-run); 2 not configured /
bad input; 3 upload failed.
"""

import argparse
import datetime
import json
import os
import subprocess
import sys

SECRETS_DIR = ".secrets"
CLIENT_SECRETS = os.path.join(SECRETS_DIR, "client_secrets.json")
TOKEN_PATH = os.path.join(SECRETS_DIR, "youtube_token.json")
SCOPES = ["https://www.googleapis.com/auth/youtube"]
CATEGORY_FILM_ANIMATION = "1"


def parse_args():
    p = argparse.ArgumentParser(prog="upload_render")
    p.add_argument("--auth", action="store_true",
                   help="Run the one-time OAuth browser flow and exit")
    p.add_argument("--video")
    p.add_argument("--episode")
    p.add_argument("--report", help="production_report.json for metadata "
                                    "(default: out/production/<episode>/)")
    p.add_argument("--title")
    p.add_argument("--privacy", default="unlisted",
                   choices=["unlisted", "private", "public"])
    p.add_argument("--playlist", help="Playlist title (default: episode id)")
    p.add_argument("--dry-run", action="store_true")
    return p.parse_args()


def head_hash():
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                              capture_output=True, text=True,
                              check=True).stdout.strip()
    except Exception:
        return "unknown"


def get_credentials(interactive):
    """Load/refresh stored credentials; mint them if `interactive`."""
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request

    if os.path.isfile(TOKEN_PATH):
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
        if creds.valid:
            return creds
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            with open(TOKEN_PATH, "w") as f:
                f.write(creds.to_json())
            return creds

    if not interactive:
        print(f"[upload] NOT CONFIGURED: no usable token at {TOKEN_PATH}.\n"
              f"  1. Place the OAuth client file at {CLIENT_SECRETS}\n"
              f"     (Google Cloud console: enable YouTube Data API v3, "
              f"create an OAuth 'Desktop app' client, download JSON)\n"
              f"  2. Run: .venv/bin/python tools/upload_render.py --auth",
              file=sys.stderr)
        sys.exit(2)

    if not os.path.isfile(CLIENT_SECRETS):
        print(f"[upload] ERROR: {CLIENT_SECRETS} not found — download the "
              f"OAuth Desktop-app client JSON from the Google Cloud console "
              f"first.", file=sys.stderr)
        sys.exit(2)
    from google_auth_oauthlib.flow import InstalledAppFlow
    flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRETS, SCOPES)
    creds = flow.run_local_server(port=0)
    os.makedirs(SECRETS_DIR, exist_ok=True)
    with open(TOKEN_PATH, "w") as f:
        f.write(creds.to_json())
    print(f"[upload] token stored at {TOKEN_PATH}")
    return creds


def build_metadata(args, report, rev):
    date = datetime.date.today().isoformat()
    title = args.title or f"OEB {args.episode} — production run {date}"
    lines = [f"Orlando El Bastardo — automated production-run render.",
             f"Episode: {args.episode}   Commit: {rev}   Date: {date}", ""]
    if report:
        lines.append(f"Script: {report.get('script', '?')}")
        lines.append(f"Scenes: {report.get('delivered', '?')} delivered, "
                     f"{report.get('blocked', '?')} blocked, "
                     f"{report.get('failed', '?')} failed")
        for sid, entry in sorted(report.get("scenes", {}).items()):
            lines.append(f"  {sid}: {entry.get('status')}")
        kinds = set()
        for vf in report.get("vocabulary", {}).values():
            for note in vf.get("notes", []) + vf.get("blocking", []):
                kinds.add(note.get("kind", "?"))
        if kinds:
            lines.append(f"Open vocabulary/tickets: {', '.join(sorted(kinds))}")
        lines.append("")
    lines.append("Deterministic pipeline (Blender + local LLM as constrained "
                 "translator; no generative video).")
    lines.append("https://github.com/twgmichael/Orlando-El-Bastardo")
    return {
        "snippet": {
            "title": title[:100],
            "description": "\n".join(lines)[:4900],
            "tags": ["OrlandoElBastardo", "3danimation", "blender",
                     "proceduralpipeline"],
            "categoryId": CATEGORY_FILM_ANIMATION,
        },
        "status": {
            "privacyStatus": args.privacy,
            "selfDeclaredMadeForKids": False,
        },
    }


def ensure_playlist(youtube, title, privacy):
    """Find a playlist by exact title on the channel, or create it."""
    page = None
    while True:
        resp = youtube.playlists().list(part="snippet", mine=True,
                                        maxResults=50,
                                        pageToken=page).execute()
        for item in resp.get("items", []):
            if item["snippet"]["title"] == title:
                return item["id"]
        page = resp.get("nextPageToken")
        if not page:
            break
    resp = youtube.playlists().insert(
        part="snippet,status",
        body={"snippet": {"title": title,
                          "description": "OEB production runs"},
              "status": {"privacyStatus": privacy}}).execute()
    return resp["id"]


def record_upload(report_path, entry):
    if not report_path or not os.path.isfile(report_path):
        return
    report = json.load(open(report_path))
    report.setdefault("uploads", []).append(entry)
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)
        f.write("\n")


def main():
    args = parse_args()
    if args.auth:
        get_credentials(interactive=True)
        return

    if not args.video or not args.episode:
        print("[upload] ERROR: --video and --episode are required "
              "(or use --auth)", file=sys.stderr)
        sys.exit(2)
    if not os.path.isfile(args.video):
        print(f"[upload] ERROR: video not found: {args.video}",
              file=sys.stderr)
        sys.exit(2)

    report_path = args.report or os.path.join(
        "out", "production", args.episode, "production_report.json")
    report = None
    if os.path.isfile(report_path):
        report = json.load(open(report_path))

    rev = head_hash()
    body = build_metadata(args, report, rev)
    playlist_title = args.playlist or f"OEB {args.episode}"
    size_mb = os.path.getsize(args.video) / 1e6

    if args.dry_run:
        print(f"[upload] DRY RUN — would upload {args.video} "
              f"({size_mb:.1f} MB) as {args.privacy}")
        print(f"[upload]   playlist: {playlist_title}")
        print(f"[upload]   title: {body['snippet']['title']}")
        print("[upload]   description:")
        for line in body["snippet"]["description"].splitlines():
            print(f"     {line}")
        return

    creds = get_credentials(interactive=False)
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    youtube = build("youtube", "v3", credentials=creds)

    print(f"[upload] uploading {args.video} ({size_mb:.1f} MB) "
          f"as {args.privacy} …")
    try:
        media = MediaFileUpload(args.video, mimetype="video/mp4",
                                resumable=True)
        request = youtube.videos().insert(part="snippet,status",
                                          body=body, media_body=media)
        response = None
        while response is None:
            _status, response = request.next_chunk()
        video_id = response["id"]
        url = f"https://youtu.be/{video_id}"
        playlist_id = ensure_playlist(youtube, playlist_title, args.privacy)
        youtube.playlistItems().insert(
            part="snippet",
            body={"snippet": {
                "playlistId": playlist_id,
                "resourceId": {"kind": "youtube#video",
                               "videoId": video_id}}}).execute()
    except Exception as exc:
        print(f"[upload] FAILED: {exc}", file=sys.stderr)
        sys.exit(3)

    record_upload(report_path, {
        "video_id": video_id, "url": url,
        "title": body["snippet"]["title"], "privacy": args.privacy,
        "playlist": playlist_title, "commit": rev,
        "uploaded": datetime.datetime.now().isoformat(timespec="seconds"),
    })
    print(f"[upload] DONE — {url}  (playlist '{playlist_title}', "
          f"{args.privacy}); recorded in {report_path}")


if __name__ == "__main__":
    main()
