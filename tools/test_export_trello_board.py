import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from io import BytesIO

from export_trello_board import export


class ExportTest(unittest.TestCase):
    def test_exports_lists_cards_comments_and_safe_collisions(self):
        board = {
            "lists": [{"id": "l1", "name": "Ideas/Notes"}],
            "cards": [
                {"id": "c1", "idList": "l1", "name": "A/B", "desc": "See https://video.example/watch and https://media.example/clip.mp4", "attachments": []},
                {"id": "c2", "idList": "l1", "name": "A:B", "desc": "", "attachments": []},
            ],
            "actions": [{"type": "commentCard", "data": {"card": {"id": "c1"}, "text": "A comment"}}],
        }
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "swipe"
            unrelated = output / "keep.txt"
            output.mkdir()
            unrelated.write_text("keep", encoding="utf-8")
            self.assertEqual([], export(board, output))
            folders = [path for path in (output / "Ideas_Notes").iterdir() if path.is_dir()]
            self.assertEqual(2, len(folders))
            text = next(folder for folder in folders if "A_B" == folder.name).joinpath("card.txt").read_text(encoding="utf-8")
            self.assertIn("A comment", text)
            self.assertIn("https://video.example/watch", text)
            self.assertIn("https://media.example/clip.mp4", text)
            video_section = text.split("Video links:", 1)[1]
            self.assertNotIn("https://video.example/watch", video_section)
            self.assertEqual("keep", unrelated.read_text(encoding="utf-8"))

    def test_duplicate_card_names_are_stable_on_rerun(self):
        board = {"lists": [{"id": "l", "name": "List"}], "cards": [
            {"id": "one", "idList": "l", "name": "Same"},
            {"id": "two", "idList": "l", "name": "Same"},
        ], "actions": []}
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            self.assertEqual([], export(board, output))
            names = sorted(path.name for path in (output / "List").iterdir() if path.is_dir())
            self.assertEqual(["Same", "Same (two)"], names)
            self.assertEqual([], export(board, output))
            self.assertEqual(names, sorted(path.name for path in (output / "List").iterdir() if path.is_dir()))

    def test_missing_actions_reports_comments_unavailable(self):
        with tempfile.TemporaryDirectory() as temporary:
            failures = export({"lists": [{"id": "l", "name": "List"}], "cards": [{"id": "c", "idList": "l", "name": "Card"}]}, Path(temporary))
            text = (Path(temporary) / "List" / "Card" / "card.txt").read_text(encoding="utf-8")
            self.assertIn("Comments unavailable", text)
            self.assertTrue(any("Comments unavailable" in failure for failure in failures))

    def test_empty_actions_means_no_comments(self):
        with tempfile.TemporaryDirectory() as temporary:
            failures = export({"lists": [{"id": "l", "name": "List"}], "cards": [{"id": "c", "idList": "l", "name": "Card"}], "actions": []}, Path(temporary))
            text = (Path(temporary) / "List" / "Card" / "card.txt").read_text(encoding="utf-8")
            self.assertIn("(No comments.)", text)
            self.assertEqual([], failures)

    def test_downloads_image_by_mime_type_even_without_image_url_extension(self):
        board = {"lists": [{"id": "l", "name": "List"}], "cards": [{"id": "c", "idList": "l", "name": "Card", "attachments": [
            {"url": "https://files.example/download?id=1", "name": "photo", "mimeType": "image/jpeg", "isUpload": True}
        ]}], "actions": []}
        class Response(BytesIO):
            def __enter__(self): return self
            def __exit__(self, *args): self.close()
        with tempfile.TemporaryDirectory() as temporary, patch("export_trello_board.urllib.request.urlopen", return_value=Response(b"image")):
            self.assertEqual([], export(board, Path(temporary)))
            self.assertEqual(b"image", (Path(temporary) / "List" / "Card" / "photo").read_bytes())

    def test_reports_cards_without_visible_list(self):
        with tempfile.TemporaryDirectory() as temporary:
            failures = export({"lists": [], "cards": [{"id": "c1", "name": "orphan", "idList": "missing"}]}, Path(temporary))
            self.assertEqual(2, len(failures))
            self.assertTrue(any("list unavailable" in failure for failure in failures))


if __name__ == "__main__":
    unittest.main()
