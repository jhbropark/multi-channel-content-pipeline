"""Offline checks: no platform calls or workflow dispatch."""
import json
import unittest
from pathlib import Path
from unittest.mock import patch
from scripts import summarize_publish_results as results


class PublishSummaryTests(unittest.TestCase):
    def summarize(self, files, **kwargs):
        def read(path, **unused):
            if path.name not in files:
                raise FileNotFoundError(path)
            return files[path.name]
        with patch.object(Path, "read_text", read):
            return results.summarize(Path("content"), **kwargs)

    def test_published_id(self):
        self.assertEqual(results.inspect_result({"facebook": {"id": "123"}}, "facebook"), "published")

    def test_errors_override_success(self):
        self.assertEqual(results.inspect_result({"facebook": {"id": "123"}, "errors": {"x": {}}}, "facebook"), "API error (see publish-log)")

    def test_missing_channel_not_success(self):
        self.assertEqual(results.inspect_result({"image_urls": ["url"]}, "linkedin"), "missing channel result")

    def test_missing_id_not_success(self):
        self.assertEqual(results.inspect_result({"x": {"id": None}}, "x"), "missing publication ID")

    def test_thread_requires_every_id(self):
        self.assertEqual(results.inspect_result({"x": {"posts": [{"id": "1"}, {}]}}, "x"), "missing publication ID")
        self.assertEqual(results.inspect_result({"x": {"posts": [{"id": "1"}]}}, "x"), "published")

    def test_known_skip(self):
        for reason in ("duplicate_caption", "instagram_activity_cooldown"):
            self.assertEqual(results.inspect_result({"instagram": {"status": "skipped", "reason": reason}}, "instagram"), "skipped")

    def test_invalid_cooldown_is_failure(self):
        self.assertEqual(results.inspect_result({"instagram": {"status": "skipped", "reason": "invalid_instagram_cooldown_until"}}, "instagram"), "unrecognized skip")

    def test_missing_files_after_pages_failure(self):
        rows = self.summarize({})
        self.assertEqual(len(rows), 7)
        self.assertTrue(all(status == "not completed (no result)" for _, status in rows))

    def test_scope_ignores_unselected_channels(self):
        rows = self.summarize({"facebook-publish-results.json": '{"facebook":{"id":"1"}}'}, scope="facebook")
        self.assertEqual(rows, [("facebook", "published")])

    def test_linkedin_english_uses_linkedin_key(self):
        rows = self.summarize({"linkedin-english-publish-results.json": '{"linkedin":{"id":"1"}}'}, scope="linkedin_en")
        self.assertEqual(rows, [("linkedin_en", "published")])

    def test_reel_shared_cooldown(self):
        rows = self.summarize({"instagram-publish-results.json": '{"instagram":{"status":"skipped","reason":"instagram_activity_cooldown"}}'}, scope="instagram_reel", cooldown=True)
        self.assertEqual(rows, [("instagram_reel", "skipped")])

    def test_reel_cooldown_cannot_accept_published_carousel(self):
        rows = self.summarize({"instagram-publish-results.json": '{"instagram":{"id":"1"}}'}, scope="instagram_reel", cooldown=True)
        self.assertEqual(rows, [("instagram_reel", "missing cooldown result")])

    def test_malformed_and_non_object(self):
        for data, status in (("{", "unreadable result"), ("[]", "invalid result")):
            self.assertEqual(self.summarize({"facebook-publish-results.json": data}, scope="facebook"), [("facebook", status)])

    def test_dry_run_does_not_claim_publication(self):
        rows = self.summarize({"github-actions-publish-results.json": '{"image_urls":["url"]}'}, dry_run=True)
        self.assertEqual(rows, [("validation", "validated only")])

    def test_november_15_partial_failure_fixture(self):
        files = {}
        for name, (filename, key) in results.RESULTS.items():
            payload = {key: {"id": "example"}} if name in {"instagram", "instagram_reel", "facebook"} else {"errors": {key: {"message": "failure"}}}
            files[filename] = json.dumps(payload)
        rows = self.summarize(files)
        self.assertEqual(sum(status == "published" for _, status in rows), 3)
        self.assertEqual(sum(status == "API error (see publish-log)" for _, status in rows), 4)

    def test_invalid_scope_rejected(self):
        with self.assertRaises(ValueError):
            self.summarize({}, scope="unexpected")


if __name__ == "__main__":
    unittest.main()
