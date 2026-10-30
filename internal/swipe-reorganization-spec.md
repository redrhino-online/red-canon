# Swipe file grouping spec

## Goal

Make related swipe cards easy to find together without changing the source
backup layout or its files.

## User-visible behavior

- A new internal catalog groups cards by shared product or theme.
- The catalog links to the original card folders under `swipe/`.
- Strong title matches are separated from likely or theme-based groupings.
- Duplicate and untitled cards are called out instead of silently merged.
- The Authority Amplifier (AA) video/page is listed with matching ads and
  landing pages when their card titles confirm the same product.

```mermaid
flowchart LR
    A[Swipe backup] --> B[Grouped catalog] --> C[Original cards]
```

## Non-goals

- Moving or renaming list folders, card folders, or files in `swipe/`.
- Editing exported card text, images, or attachment links.
- Claiming a shared campaign where names only suggest a relationship.
- Changing the Trello exporter or public site content.

## Acceptance criteria

1. Given a reader opens the internal swipe catalog, when they look for a
   product with matching titles, then its ads, landing pages, AA video/page,
   downloads, and other matching cards are linked together where present.
2. Given two card titles do not establish an exact match, when they are grouped
   by subject, then the catalog labels the relationship as likely or thematic.
3. Given the backup has duplicate or untitled cards, when the catalog is read,
   then those entries are identified and not silently dropped.
4. Given the Trello exporter runs against the existing layout, when it reads
   `swipe/`, then list folders remain direct children and card folders remain
   inside their original list folders.
5. Given the repository structure is documented, when the catalog is added,
   then the README points to it and every catalog link resolves.
6. Given this change is reviewed, when comparing tracked swipe files to the
   base branch, then no source backup file has been moved, renamed, or edited.

## Constraints

- Preserve all existing repository work and keep the swipe export layout
  compatible with `tools/export_trello_board.py`.
- Do not edit `framework-canon/` or any exported files under `swipe/`.
- Keep the catalog and spec in `internal/`, outside the public site.
- Use relative links and plain, readable Markdown.

## Assumptions and open questions

- ASSUMPTION: “Reorganize the swipe files” means adding a grouped navigation
  catalog, not physically moving exported cards. The exporter and backup spec
  depend on the current list/card folder structure.
- ASSUMPTION: A matching title is enough to group assets as a confirmed
  product match; a shared campaign is not implied unless the card data shows it.
- Open questions: None. The catalog can clearly separate confirmed matches
  from plausible thematic links.

## Plan

1. Add `internal/swipe-reorganization-spec.md` with this scope and acceptance
   criteria. Verify the file stays internal and its references resolve.
2. Add `internal/swipe-catalog.md` with concept clusters, links to the original
   cards, remaining cards grouped by source list, and duplicate/untitled notes.
   Verify every linked card folder exists and title-match claims against
   `card.txt`.
3. Update the [README](../README.md) to link to the catalog. Verify the link resolves and the
   existing swipe backup/export contract is unchanged.
4. Run Markdown-link checks, `git diff --check`, and the offline exporter test
   suite. Compare `swipe/` to the base branch to prove no exported file changed.

## Rollback

Remove the new catalog and spec, then revert only the README catalog link. Do
not alter or remove any existing swipe backup files.
