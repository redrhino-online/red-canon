# Trello swipe board backup spec

## Goal

Save the accessible content from the requested Trello board under `swipe/`.
Each Trello list becomes a folder. Each card becomes a folder in its list.
Keep text and image attachments with the matching card.

## User-visible behavior

- A backup tool reads all lists and cards in the public board data without asking for Trello credentials, including archived items exposed by the public export.
- It creates `swipe/<list>/<card>/` folders with safe, readable names.
- Each card folder has a text file with its description, comments, and any video
  links found in card text or attachment links.
- Image attachments are downloaded into that card folder.
- Non-image attachments remain as links in the text file.
- The tool reports inaccessible or failed items and exits with a failure status
  if it could not complete the backup.

## Non-goals

- Bypassing board privacy or downloading content that public access does not show.
- Backing up votes, member profiles, activity history, or board settings.
- Saving video files; save video links only.
- Editing or deleting Trello content.

## Acceptance criteria

1. Given the public board endpoint is reachable, when the backup runs, then all
   lists and cards exposed by the public export are represented as list and card folders under
   `swipe/`.
2. Given a card has a description, comments, or video links, when the backup
   runs, then those values appear in that card's text file.
3. Given a card has image attachments that are publicly downloadable, when the
   backup runs, then the image files are saved in that card's folder.
4. Given content is not available through public access, when the backup runs,
   then the tool reports that gap and does not claim a complete backup.
5. Given names contain path separators or unsafe characters, when folders are
   made, then the output remains inside `swipe/` and names remain readable.
6. Given the output folder already exists, when the tool runs, then it updates
   matching export files without deleting unrelated files.

## Constraints

- Use only public board access, as selected by the user.
- Do not store credentials or add them to the repo.
- Preserve existing repository changes; do not alter unrelated work.
- Do not touch `framework-canon/`.

## Assumptions and open questions

- ASSUMPTION: The board's public JSON export contains the content Trello makes
  available without login. Comments or images not exposed there will be noted
  as unavailable rather than retrieved through private APIs.
- ASSUMPTION: List and card folder names may be cleaned and disambiguated to
  avoid unsafe paths and collisions.
- Open question: None. The user chose public access after being told that it
  may not expose all comments or attachment data.

## Plan

1. Add a small Python exporter that reads public board JSON and writes the
   folder and file layout above. Verify with offline fixtures.
2. Run the exporter against the requested board. Check list/card counts, file
   types, download failures, and the final git status.
3. Roll back by removing only the newly added exporter, spec, and `swipe/`
   output. Never remove unrelated pre-existing files.
