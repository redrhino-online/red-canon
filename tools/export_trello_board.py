#!/usr/bin/env python3
"""Export publicly visible Trello board content to local folders."""

import argparse
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

BOARD_ID = "D9aJMBDh"
BOARD_URL = f"https://trello.com/b/{BOARD_ID}.json"
URL_RE = re.compile(r"https?://[^\s<>]+", re.IGNORECASE)
VIDEO_RE = re.compile(r"\.(?:mp4|mov|webm|m3u8)(?:[?#]|$)", re.IGNORECASE)
IMAGE_RE = re.compile(r"\.(?:jpe?g|png|gif|webp|bmp|tiff?)(?:[?#]|$)", re.IGNORECASE)
UNSAFE_RE = re.compile(r"[^A-Za-z0-9._ -]+")


def safe_name(value):
    name = UNSAFE_RE.sub("_", str(value)).strip(" ._")
    return name[:100] or "untitled"


def unique_path(parent, name, used):
    base = safe_name(name)
    candidate = base
    suffix = 2
    while candidate.casefold() in used or (parent / candidate).exists():
        candidate = f"{base} ({suffix})"
        suffix += 1
    used.add(candidate.casefold())
    return parent / candidate


def fetch_json(url):
    request = urllib.request.Request(url, headers={"User-Agent": "public-trello-backup/1.0"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def save_text(card, comments, comments_available, path):
    lines = [f"Card: {card.get('name', '')}", f"Card ID: {card.get('id', '')}", "", "Description:", card.get("desc") or ""]
    lines.extend(["", "Comments:"])
    lines.extend(comments if comments else (["(No comments.)"] if comments_available else ["(Comments unavailable in the public export.)"]))
    text_urls = set(URL_RE.findall((card.get("desc") or "") + " " + " ".join(comments)))
    links = {url for url in text_urls if VIDEO_RE.search(url)}
    for attachment in card.get("attachments", []):
        link = attachment.get("url")
        if link:
            if VIDEO_RE.search(link):
                links.add(link)
            is_image = (str(attachment.get("mimeType") or "").lower().startswith("image/")
                        or bool(IMAGE_RE.search(attachment.get("name") or ""))
                        or bool(IMAGE_RE.search(link)))
            if not is_image:
                lines.extend(["", f"Attachment: {attachment.get('name') or link}", link])
    lines.extend(["", "Links:"])
    lines.extend(sorted(text_urls) or ["(None found)"])
    lines.extend(["", "Video links:"])
    lines.extend(sorted(links) or ["(None found)"])
    text = "\n".join(lines)
    path.write_text("\n".join(line.rstrip() for line in text.splitlines()) + "\n", encoding="utf-8")


def export(board, output):
    failures = []
    output.mkdir(parents=True, exist_ok=True)
    lists = {item["id"]: item for item in board.get("lists", [])}
    list_paths = {}
    used = set()
    for item in lists.values():
        list_id = str(item["id"])
        list_name = item.get("name", "untitled")
        path = next((entry for entry in output.iterdir()
                     if entry.is_dir() and (entry / ".list-id").exists()
                     and (entry / ".list-id").read_text(encoding="utf-8").strip() == list_id), None)
        if path is None:
            path = next((entry for entry in output.iterdir()
                         if entry.is_dir() and entry.name.casefold() == safe_name(list_name).casefold()
                         and entry not in used), None)
        if path is None:
            path = unique_path(output, list_name, used)
        path.mkdir(parents=True, exist_ok=True)
        (path / ".list-id").write_text(list_id + "\n", encoding="utf-8")
        used.add(path)
        list_paths[item["id"]] = path

    comments_by_card = {}
    actions = board.get("actions")
    comments_available = isinstance(actions, list)
    if not comments_available and board.get("cards", []):
        failures.append("Comments unavailable: public export has no actions list")
    for action in actions if comments_available else []:
        if action.get("type") == "commentCard":
            card_id = (action.get("data", {}).get("card") or {}).get("id")
            text = (action.get("data", {}).get("text") or "").strip()
            if card_id and text:
                comments_by_card.setdefault(card_id, []).append(text)

    cards = board.get("cards", [])
    used_folders = set()
    for card in cards:
        parent = list_paths.get(card.get("idList"))
        if parent is None:
            failures.append(f"Card {card.get('name', card.get('id', 'unknown'))}: list unavailable")
            continue
        card_id = str(card.get("id") or "unknown")
        base = safe_name(card.get("name", "untitled"))
        folder = next((entry for entry in parent.iterdir()
                       if entry.is_dir() and (entry / "card.txt").exists()
                       and f"Card ID: {card_id}" in (entry / "card.txt").read_text(encoding="utf-8", errors="replace").splitlines()), None)
        if folder is None:
            # Reuse folders from an earlier version that did not write card IDs.
            folder = next((entry for entry in parent.iterdir()
                           if entry.is_dir() and entry not in used_folders
                           and (entry / "card.txt").exists()
                           and f"Card: {card.get('name', '')}" in (entry / "card.txt").read_text(encoding="utf-8", errors="replace").splitlines()), None)
        if folder is None:
            folder = parent / base
            if folder.exists():
                folder = parent / f"{base} ({safe_name(card_id)})"
            suffix = 2
            while folder.exists():
                folder = parent / f"{base} ({safe_name(card_id)} {suffix})"
                suffix += 1
        used_folders.add(folder)
        folder.mkdir(parents=True, exist_ok=True)
        try:
            save_text(card, comments_by_card.get(card.get("id"), []), comments_available, folder / "card.txt")
        except OSError as error:
            failures.append(f"Card {card.get('name')}: could not write text: {error}")
        used_images = set()
        for attachment in card.get("attachments", []):
            url = attachment.get("url", "")
            image_hint = (str(attachment.get("mimeType") or "").lower().startswith("image/")
                          or bool(IMAGE_RE.search(attachment.get("name") or ""))
                          or bool(IMAGE_RE.search(url)))
            if not image_hint or not url:
                continue
            filename = safe_name(attachment.get("name") or Path(urllib.parse.urlparse(url).path).name or "image")
            candidate = filename
            suffix = 2
            while candidate.casefold() in used_images:
                stem = Path(filename).stem
                extension = Path(filename).suffix
                candidate = f"{stem} ({suffix}){extension}"
                suffix += 1
            used_images.add(candidate.casefold())
            image_path = folder / candidate
            try:
                request = urllib.request.Request(url, headers={"User-Agent": "public-trello-backup/1.0"})
                with urllib.request.urlopen(request, timeout=30) as response:
                    image_path.write_bytes(response.read())
            except (OSError, urllib.error.URLError) as error:
                failures.append(f"Image {url}: download failed: {error}")
    return failures


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("swipe"))
    args = parser.parse_args(argv)
    try:
        board = fetch_json(BOARD_URL)
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as error:
        print(f"Board unavailable: {error}", file=sys.stderr)
        return 1
    if not isinstance(board, dict) or not board.get("lists"):
        print("Board unavailable or public export contains no lists", file=sys.stderr)
        return 1
    failures = export(board, args.output)
    for failure in failures:
        print(f"Incomplete: {failure}", file=sys.stderr)
    print(f"Exported {len(board.get('cards', []))} cards; {len(failures)} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
