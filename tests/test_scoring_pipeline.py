"""
Unit tests for the text-scoring pipeline in src/jh_ai_engine.py.

Covers:
  pack_paragraphs_to_budget()  — strict buffer math, oversized-skip, delimiter invariant.
  extract_relevant_context()   — noise cleaning, score-based selection, Narrative Rule
                                 (selected paragraphs restored to document order),
                                 hard len(result) <= max_chars postcondition.
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from jh_ai_engine import pack_paragraphs_to_budget, extract_relevant_context


# ─────────────────────────────────────────────────────────────────────────────
# pack_paragraphs_to_budget()
# ─────────────────────────────────────────────────────────────────────────────

class TestPackParagraphsToBudget:

    # ── Empty / trivial inputs ────────────────────────────────────────────────

    def test_empty_list_returns_empty_string(self):
        assert pack_paragraphs_to_budget([], max_chars=1000) == ""

    def test_single_paragraph_no_delimiter_charged(self):
        """First (and only) paragraph must not be charged a leading delimiter."""
        assert pack_paragraphs_to_budget(["hello"], max_chars=5) == "hello"

    def test_single_paragraph_exactly_fills_budget(self):
        result = pack_paragraphs_to_budget(["12345"], max_chars=5)
        assert result == "12345"
        assert len(result) == 5

    # ── Delimiter math invariant: total = Σlen(p_i) + (n-1) * len(delimiter) ─

    def test_two_paragraphs_exact_fit(self):
        # "ab" + "\n\n" + "cd" = 2 + 2 + 2 = 6
        result = pack_paragraphs_to_budget(["ab", "cd"], max_chars=6)
        assert result == "ab\n\ncd"
        assert len(result) == 6

    def test_two_paragraphs_one_char_under_fit(self):
        # budget 5: "ab"(2) + "\n\n"(2) + "cd"(2) = 6 > 5 → only first fits
        result = pack_paragraphs_to_budget(["ab", "cd"], max_chars=5)
        assert result == "ab"

    def test_three_paragraphs_delimiter_math(self):
        # 10-char each: 10 + 2 + 10 + 2 + 10 = 34; budget 22 fits exactly two
        scored = ["1234567890", "abcdefghij", "ABCDEFGHIJ"]
        result = pack_paragraphs_to_budget(scored, max_chars=22)
        assert result == "1234567890\n\nabcdefghij"
        assert len(result) == 22

    def test_third_paragraph_one_char_over_budget(self):
        # 10 + 2 + 10 = 22; adding third (10+2=12) → 34 > 33 → skip third
        result = pack_paragraphs_to_budget(
            ["1234567890", "abcdefghij", "ABCDEFGHIJ"], max_chars=33
        )
        assert "ABCDEFGHIJ" not in result
        assert len(result) == 22

    # ── Oversized-skip contract ───────────────────────────────────────────────

    def test_single_oversized_paragraph_skipped(self):
        """A paragraph larger than max_chars alone must be skipped; loop continues."""
        result = pack_paragraphs_to_budget(["X" * 200, "small text"], max_chars=50)
        assert result == "small text"

    def test_multiple_oversized_skipped_small_collected(self):
        result = pack_paragraphs_to_budget(
            ["L" * 300, "M" * 300, "fits fine", "also fits"], max_chars=25
        )
        parts = set(result.split("\n\n"))
        assert "fits fine" in parts
        assert "also fits" in parts
        assert not any(len(p) > 25 for p in parts)

    def test_all_oversized_returns_empty_string(self):
        result = pack_paragraphs_to_budget(["A" * 100, "B" * 100], max_chars=10)
        assert result == ""

    # ── Custom delimiter ──────────────────────────────────────────────────────

    def test_custom_delimiter_accounted_in_budget(self):
        # "ab" + " | " + "cd" = 2 + 3 + 2 = 7; budget 6 → only first fits
        result = pack_paragraphs_to_budget(["ab", "cd"], max_chars=6, delimiter=" | ")
        assert result == "ab"

    def test_custom_delimiter_both_fit(self):
        result = pack_paragraphs_to_budget(["ab", "cd"], max_chars=7, delimiter=" | ")
        assert result == "ab | cd"
        assert len(result) == 7

    # ── Hard postcondition: len(result) <= max_chars ──────────────────────────

    def test_result_never_exceeds_max_chars(self):
        paragraphs = ["word " * i for i in range(1, 20)]
        for budget in [50, 100, 200, 500]:
            result = pack_paragraphs_to_budget(paragraphs, max_chars=budget)
            assert len(result) <= budget, (
                f"len={len(result)} exceeded budget={budget}"
            )


# ─────────────────────────────────────────────────────────────────────────────
# extract_relevant_context()
# ─────────────────────────────────────────────────────────────────────────────

class TestExtractRelevantContext:

    # ── Basic postconditions ──────────────────────────────────────────────────

    def test_empty_input_returns_empty_string(self):
        assert extract_relevant_context("", max_chars=1000) == ""

    def test_result_never_exceeds_max_chars(self):
        raw = "\n\n".join([
            "Introduction to our company and our global mission.",
            "Key requirements: Python, Go, Kubernetes, AWS, PostgreSQL, Redis.",
            "Responsibilities: design and maintain distributed microservices.",
            "We offer remote work, stock options, and comprehensive benefits.",
            "About our engineering culture, values, and team structure.",
        ])
        for budget in [50, 100, 200, 500, 10_000]:
            result = extract_relevant_context(raw, max_chars=budget)
            assert len(result) <= budget, (
                f"len={len(result)} exceeded budget={budget}"
            )

    def test_returns_string(self):
        result = extract_relevant_context("Hello world.", max_chars=1000)
        assert isinstance(result, str)

    # ── Narrative Rule: output is in original document order ─────────────────

    def test_narrative_order_preserved_when_high_score_last(self):
        """The highest-scoring paragraph appears last in source — must appear last in output."""
        raw = (
            "Welcome to our company. We are a global leader.\n\n"
            "About our engineering culture and our values.\n\n"
            "Key requirements: Python, Kubernetes, PostgreSQL, Redis, AWS, experience."
        )
        result = extract_relevant_context(raw, max_chars=10_000)
        parts = result.split("\n\n")
        assert parts[-1].startswith("Key requirements"), (
            f"High-score paragraph must come last (doc order). Got: {parts[-1]!r}"
        )
        assert parts[0].startswith("Welcome"), (
            f"First doc paragraph must come first. Got: {parts[0]!r}"
        )

    def test_narrative_order_three_paragraphs_all_fit(self):
        # Single-word short strings like "First." are correctly stripped by the
        # nav-noise filter (≤2 words AND ≤25 chars, no vacancy keyword).
        # Use full sentences so all three paragraphs survive the filter.
        raw = (
            "First section of the company overview and background.\n\n"
            "Second section covering requirements and qualifications for the role.\n\n"
            "Third section on team culture, values, and working environment."
        )
        result = extract_relevant_context(raw, max_chars=10_000)
        parts = result.split("\n\n")
        idx_first  = next(i for i, p in enumerate(parts) if p.startswith("First"))
        idx_second = next(i for i, p in enumerate(parts) if "requirements" in p)
        idx_third  = next(i for i, p in enumerate(parts) if p.startswith("Third"))
        assert idx_first < idx_second < idx_third, (
            "Paragraphs must appear in original document order"
        )

    # ── Score-based selection ─────────────────────────────────────────────────

    def test_high_relevance_paragraph_included_in_tight_budget(self):
        """When budget is tight, the keyword-rich paragraph must be preferred."""
        # The keyword paragraph must fit within max_chars on its own.
        # "Requirements: Python, Docker. Responsibilities: build APIs. Experience required."
        # is 80 chars; budget=90 fits it alone but not the 60-char intro too.
        raw = (
            "Generic company introduction with no special meaning at all.\n\n"
            "Requirements: Python, Docker. Responsibilities: build APIs. Experience required."
        )
        result = extract_relevant_context(raw, max_chars=90)
        assert "Requirements" in result or "requirements" in result, (
            "Keyword-rich paragraph must be selected under tight budget"
        )

    def test_low_relevance_paragraph_dropped_under_budget(self):
        """Navigation noise that fails the keyword test must not appear in output."""
        raw = (
            "Sign In\n\n"
            "Register\n\n"
            "Requirements: Python, Kubernetes. Responsibilities: build microservices."
        )
        result = extract_relevant_context(raw, max_chars=200)
        # Nav noise lines are 1–2 words ≤25 chars and carry no vacancy keyword
        assert "Sign In" not in result
        assert "Register" not in result

    # ── Delimiter budget contract inside extract_relevant_context ─────────────

    def test_two_paragraphs_exact_budget_match(self):
        """Both paragraphs must fit when their combined length exactly equals max_chars."""
        # "Alpha." (1 word, 6 chars) is stripped by the nav-noise filter.
        # Use a sentence long enough to survive: >2 words OR >25 chars.
        # "Alpha section overview text here." (5 words, 33 chars) + "\n\n" +
        # "Beta requirements." (2 words but matches keyword → kept) = 33+2+18 = 53.
        raw = "Alpha section overview text here.\n\nBeta requirements."
        result = extract_relevant_context(raw, max_chars=53)
        assert "Alpha section overview text here." in result
        assert "Beta requirements." in result
        assert len(result) <= 53

    # ── Edge cases ────────────────────────────────────────────────────────────

    def test_single_paragraph_fits(self):
        raw = "Only paragraph with requirements."
        result = extract_relevant_context(raw, max_chars=1000)
        assert "Only paragraph" in result

    def test_single_paragraph_exceeds_budget_skipped(self):
        """A single paragraph larger than max_chars must result in empty output."""
        raw = "A" * 200
        result = extract_relevant_context(raw, max_chars=50)
        assert result == ""

    def test_whitespace_normalization_applied(self):
        raw = "First   paragraph.\r\n\r\nSecond  requirements   paragraph."
        result = extract_relevant_context(raw, max_chars=10_000)
        # Multiple spaces should be collapsed; no \r\n
        assert "   " not in result
        assert "\r" not in result

    # ── Stage 1 / Stage 2 coherence ──────────────────────────────────────────

    def test_stage2_result_shorter_or_equal_to_stage1(self):
        raw = "\n\n".join([
            "Company background and mission statement.",
            "Requirements: Python, Go, Rust, TypeScript, Kubernetes.",
            "What you will do: build distributed systems and APIs.",
            "We offer remote work, equity, and learning budget.",
            "About our engineering process and team rituals.",
        ])
        s1 = extract_relevant_context(raw, max_chars=400)
        s2 = extract_relevant_context(raw, max_chars=200)
        assert len(s2) <= len(s1), (
            f"Stage 2 (len={len(s2)}) must not be longer than Stage 1 (len={len(s1)})"
        )
        assert len(s1) <= 400
        assert len(s2) <= 200

    def test_paragraphs_in_stage2_appear_in_stage1(self):
        """
        Because both stages score the same text, the highest-scoring paragraphs
        selected for Stage 2 (tighter budget) should also appear in Stage 1.
        """
        raw = "\n\n".join([
            "Introduction to the company and our global engineering mission.",
            "Key requirements: Python, Go, Kubernetes, PostgreSQL, Redis, AWS.",
            "What you will do: design APIs and scalable backend microservices.",
            "We offer remote work, stock options, and full health benefits.",
            "About our engineering culture, values, and team diversity.",
        ])
        s1_parts = set(extract_relevant_context(raw, max_chars=500).split("\n\n"))
        s2_parts = set(extract_relevant_context(raw, max_chars=200).split("\n\n"))
        s1_parts.discard("")
        s2_parts.discard("")
        assert s2_parts.issubset(s1_parts), (
            f"Stage 2 paragraphs not in Stage 1.\nDiff: {s2_parts - s1_parts}"
        )
