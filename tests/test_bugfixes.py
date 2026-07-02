"""
Regression tests for the audit bug-fixes.

Covers:
  jh_storage_manager.save_rejected_vacancy  — _rejected_urls set stays in sync
                                               with the 50-item capped file.
  jh_ai_engine._geo_match                    — whole-word matching, no loose
                                               substring false positives.
  jh_ai_engine.clean_and_parse_json          — mixed-quote repair no longer
                                               corrupts apostrophes in values.
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import jh_storage_manager as storage
from jh_ai_engine import _geo_match, clean_and_parse_json


# ─────────────────────────────────────────────────────────────────────────────
# _rejected_urls set / capped-file sync
# ─────────────────────────────────────────────────────────────────────────────

class TestRejectedUrlSetSync:

    def _isolate(self, tmp_path, monkeypatch):
        """Point the rejected DB at a temp file and reset the in-memory set."""
        rej_file = tmp_path / "rejected.json"
        monkeypatch.setattr(storage, "REJECTED_FILE", str(rej_file))
        with storage._url_lock:
            storage._rejected_urls.clear()
        return rej_file

    def test_set_matches_file_after_cap_eviction(self, tmp_path, monkeypatch):
        self._isolate(tmp_path, monkeypatch)

        # Save 60 unique rejections; the file caps at the last 50.
        for i in range(60):
            storage.save_rejected_vacancy(
                company=f"C{i}", title=f"T{i}", url=f"https://x/{i}", reason="r"
            )

        on_disk = {v["url"] for v in storage.get_all_rejected()}
        assert len(on_disk) == 50
        # The in-memory dedup set must exactly mirror the capped file.
        with storage._url_lock:
            assert set(storage._rejected_urls) == on_disk

    def test_evicted_url_is_no_longer_reported_rejected(self, tmp_path, monkeypatch):
        self._isolate(tmp_path, monkeypatch)

        for i in range(60):
            storage.save_rejected_vacancy(
                company=f"C{i}", title=f"T{i}", url=f"https://x/{i}", reason="r"
            )

        # url 0..9 were evicted by the cap → must NOT be treated as duplicates,
        # otherwise they could never be re-evaluated.
        assert storage.vacancy_url_in_rejected("https://x/0") is False
        assert storage.vacancy_url_in_rejected("https://x/9") is False
        # A surviving url is still reported as rejected.
        assert storage.vacancy_url_in_rejected("https://x/59") is True

    def test_set_does_not_grow_unbounded(self, tmp_path, monkeypatch):
        self._isolate(tmp_path, monkeypatch)
        for i in range(200):
            storage.save_rejected_vacancy(
                company="C", title="T", url=f"https://x/{i}", reason="r"
            )
        with storage._url_lock:
            assert len(storage._rejected_urls) == 50


# ─────────────────────────────────────────────────────────────────────────────
# _geo_match — whole-word, not substring
# ─────────────────────────────────────────────────────────────────────────────

class TestGeoMatch:

    def test_alias_and_country_match(self):
        assert _geo_match("USA", ["United States"]) is True
        assert _geo_match("рф", ["Russia"]) is True
        assert _geo_match("uk", ["United Kingdom"]) is True

    def test_token_subset_match(self):
        assert _geo_match("United States", ["United States of America"]) is True
        assert _geo_match("Korea", ["South Korea"]) is True

    def test_no_loose_substring_false_positive(self):
        # The classic substring bugs must not match.
        assert _geo_match("India", ["Indiana"]) is False
        assert _geo_match("Oman", ["Romania"]) is False

    def test_unrelated_countries_do_not_match(self):
        assert _geo_match("Germany", ["France", "Spain"]) is False

    def test_empty_inputs(self):
        assert _geo_match("", ["Russia"]) is False
        assert _geo_match("Russia", []) is False


# ─────────────────────────────────────────────────────────────────────────────
# clean_and_parse_json — mixed-quote repair keeps apostrophes intact
# ─────────────────────────────────────────────────────────────────────────────

class TestJsonRepairApostrophe:

    def test_apostrophe_in_double_quoted_value_preserved(self):
        # Valid JSON already; apostrophe inside a value must survive untouched.
        raw = '{"reject_reason": "the company doesn\'t disclose salary"}'
        parsed = clean_and_parse_json(raw)
        assert parsed["reject_reason"] == "the company doesn't disclose salary"

    def test_single_quoted_object_still_repaired(self):
        # Level 4: only single quotes present → convert wholesale.
        raw = "{'is_relevant_profession': true, 'extracted_title': 'Dev'}"
        parsed = clean_and_parse_json(raw)
        assert parsed["is_relevant_profession"] is True
        assert parsed["extracted_title"] == "Dev"

    def test_markdown_wrapper_stripped(self):
        raw = '```json\n{"extracted_company": "Acme"}\n```'
        parsed = clean_and_parse_json(raw)
        assert parsed["extracted_company"] == "Acme"

    def test_trailing_comma_repaired(self):
        raw = '{"a": 1, "b": 2,}'
        parsed = clean_and_parse_json(raw)
        assert parsed == {"a": 1, "b": 2}
