"""Step 14D unit tests: project selected ProcessedCandidate into ContentCandidate.

Uses the REAL domain models (RawDiscovery, ProcessedCandidate,
ClassificationResult, VerificationResult, CandidateScore,
StrategicSelection, DiscoveryCandidate, ContentCandidate, CandidateStage).
Structural AST tests bind mapping boundaries (explicit
``CandidateStage.SELECTED``, ``content_id=None``, ``dict(raw.metadata)``)
to actual code.
"""

import ast
import unittest
from pathlib import Path

from src.domain.strategy import (
    CandidateScore,
    CandidateStage,
    ContentCandidate,
    ContentCluster,
    ContentFormat,
    DiscoveryCandidate,
    SourceType,
    StrategicSelection,
    TargetPlatform,
    VerificationStatus,
    VerificationResult,
)
from src.research.adapters.base import RawDiscovery
from src.research.classify import ClassificationResult
from src.research.content_candidate import build_selected_content_candidate
from src.research.researcher import ProcessedCandidate

SOURCE_PATH = (
    Path(__file__).resolve().parents[2] / "src" / "research" / "content_candidate.py"
)

# ──────────────────────────────────────────────────────────────────────
# Reusable valid fixture (all real domain models).
# ──────────────────────────────────────────────────────────────────────

RAW_METADATA = {"author": "alice", "matched_queries": ("vibe coding",)}


def _raw_discovery(**overrides):
    fields = dict(
        title="VibeWorks CLI released",
        url="https://github.com/vibeworks/cli",
        source_name="github",
        discovered_at="2026-09-11T12:00:00+00:00",
        published_at="2026-09-11T08:30:00+00:00",
        summary="A CLI for vibe coding workflows.",
        raw_score=42.0,
        raw_score_label="github_stars",
        comments_count=7,
        identifiers={"github_repo": "vibeworks/cli"},
        metadata=dict(RAW_METADATA),
    )
    fields.update(overrides)
    return RawDiscovery(**fields)


def _classification(cluster=ContentCluster.VIBE_CODING):
    return ClassificationResult(
        cluster=cluster,
        confidence=5.0,
        scores={},
        matched_rules=(),
        ambiguous=False,
        reason="test",
    )


def _verification():
    return VerificationResult(
        verification_status=VerificationStatus.VERIFIED,
        primary_source_found=True,
        primary_source_url="https://github.com/vibeworks/cli",
        confidence=0.9,
        notes="primary:github_repository",
    )


def _score():
    return CandidateScore(6, 6, 6, 6, 6, 6)


def _selection(**overrides):
    fields = dict(
        selected=True,
        selection_reason="selected_vibe_coding",
        recommended_format=ContentFormat.PRACTICAL_GUIDE,
        target_platforms=(TargetPlatform.TELEGRAM, TargetPlatform.X),
        research_required=False,
        experiment_required=False,
    )
    fields.update(overrides)
    return StrategicSelection(**fields)


def _processed(**overrides):
    fields = dict(
        candidate_id="cand_test",
        discovery=_raw_discovery(),
        source_type=SourceType.GITHUB,
        classification=_classification(),
        verification=_verification(),
        score=_score(),
        processing_exclusion=None,
    )
    fields.update(overrides)
    return ProcessedCandidate(**fields)


class TestMapping(unittest.TestCase):
    def setUp(self):
        self.processed = _processed()
        self.selection = _selection()
        self.result = build_selected_content_candidate(self.processed, self.selection)

    def test_returns_real_content_candidate(self):
        self.assertIsInstance(self.result, ContentCandidate)

    def test_candidate_is_real_discovery_candidate(self):
        self.assertIsInstance(self.result.candidate, DiscoveryCandidate)

    def test_candidate_id_maps_from_processed(self):
        self.assertEqual(self.result.candidate.candidate_id, "cand_test")

    def test_title_maps_from_raw(self):
        self.assertEqual(
            self.result.candidate.title, "VibeWorks CLI released"
        )

    def test_source_type_maps_from_processed(self):
        self.assertIs(self.result.candidate.source_type, SourceType.GITHUB)

    def test_source_url_maps_from_raw(self):
        self.assertEqual(
            self.result.candidate.source_url, "https://github.com/vibeworks/cli"
        )

    def test_raw_url_none_maps_to_empty_string(self):
        result = build_selected_content_candidate(
            _processed(discovery=_raw_discovery(url=None)), self.selection
        )
        self.assertEqual(result.candidate.source_url, "")

    def test_discovered_at_maps_exactly(self):
        self.assertEqual(
            self.result.candidate.discovered_at, "2026-09-11T12:00:00+00:00"
        )

    def test_content_cluster_maps_from_classification(self):
        self.assertIs(
            self.result.candidate.content_cluster, ContentCluster.VIBE_CODING
        )

    def test_source_name_maps_exactly(self):
        self.assertEqual(self.result.candidate.source_name, "github")

    def test_published_at_maps_exactly(self):
        self.assertEqual(
            self.result.candidate.published_at, "2026-09-11T08:30:00+00:00"
        )

    def test_summary_maps_exactly(self):
        self.assertEqual(
            self.result.candidate.summary, "A CLI for vibe coding workflows."
        )

    def test_raw_score_maps_exactly(self):
        self.assertEqual(self.result.candidate.raw_score, 42.0)

    def test_metadata_values_equal_raw_metadata(self):
        self.assertEqual(self.result.candidate.metadata, RAW_METADATA)

    def test_metadata_is_new_dict_by_identity(self):
        self.assertIsNot(self.result.candidate.metadata, self.processed.discovery.metadata)

    def test_raw_metadata_not_mutated(self):
        self.assertEqual(self.processed.discovery.metadata, RAW_METADATA)

    def test_verification_identity_preserved(self):
        self.assertIs(self.result.verification, self.processed.verification)

    def test_score_identity_preserved(self):
        self.assertIs(self.result.score, self.processed.score)

    def test_selection_identity_preserved(self):
        self.assertIs(self.result.selection, self.selection)


class TestStageRule(unittest.TestCase):
    def test_stage_is_exactly_selected(self):
        result = build_selected_content_candidate(_processed(), _selection())
        self.assertIs(result.stage, CandidateStage.SELECTED)

    def test_content_id_is_none(self):
        result = build_selected_content_candidate(_processed(), _selection())
        self.assertIsNone(result.content_id)

    def test_research_required_selection_still_selected_stage(self):
        result = build_selected_content_candidate(
            _processed(), _selection(research_required=True)
        )
        self.assertIs(result.stage, CandidateStage.SELECTED)

    def test_experiment_required_selection_still_selected_stage(self):
        result = build_selected_content_candidate(
            _processed(), _selection(experiment_required=True)
        )
        self.assertIs(result.stage, CandidateStage.SELECTED)


class TestPreconditions(unittest.TestCase):
    def test_unselected_selection_raises_exact_message(self):
        with self.assertRaises(ValueError) as ctx:
            build_selected_content_candidate(_processed(), _selection(selected=False))
        self.assertEqual(str(ctx.exception), "strategic selection is not selected")

    def test_missing_cluster_raises_exact_message(self):
        with self.assertRaises(ValueError) as ctx:
            build_selected_content_candidate(
                _processed(classification=_classification(cluster=None)), _selection()
            )
        self.assertEqual(
            str(ctx.exception), "selected processed candidate missing content cluster"
        )

    def test_missing_score_raises_exact_message(self):
        with self.assertRaises(ValueError) as ctx:
            build_selected_content_candidate(_processed(score=None), _selection())
        self.assertEqual(str(ctx.exception), "selected processed candidate missing score")

    def test_error_order_selection_checked_first(self):
        # All three preconditions violated -> the selection error wins.
        with self.assertRaises(ValueError) as ctx:
            build_selected_content_candidate(
                _processed(classification=_classification(cluster=None), score=None),
                _selection(selected=False),
            )
        self.assertEqual(str(ctx.exception), "strategic selection is not selected")


class TestNoInventedMetadata(unittest.TestCase):
    def test_identifiers_not_added_to_metadata(self):
        result = build_selected_content_candidate(_processed(), _selection())
        self.assertNotIn("github_repo", result.candidate.metadata)
        self.assertNotIn("identifiers", result.candidate.metadata)

    def test_comments_count_not_added_to_metadata(self):
        result = build_selected_content_candidate(_processed(), _selection())
        self.assertNotIn("comments_count", result.candidate.metadata)

    def test_raw_score_label_not_added_to_metadata(self):
        result = build_selected_content_candidate(_processed(), _selection())
        self.assertNotIn("raw_score_label", result.candidate.metadata)

    def test_metadata_keys_exactly_raw_keys(self):
        result = build_selected_content_candidate(_processed(), _selection())
        self.assertEqual(set(result.candidate.metadata.keys()), set(RAW_METADATA.keys()))


class TestPurity(unittest.TestCase):
    def test_processed_candidate_not_mutated(self):
        processed = _processed()
        snapshot = processed
        build_selected_content_candidate(processed, _selection())
        self.assertEqual(processed, snapshot)  # frozen dataclass equality

    def test_raw_discovery_not_mutated(self):
        raw = _raw_discovery()
        snapshot = raw
        build_selected_content_candidate(
            _processed(discovery=raw), _selection()
        )
        self.assertEqual(raw, snapshot)

    def test_selection_not_mutated(self):
        selection = _selection()
        build_selected_content_candidate(_processed(), selection)
        self.assertEqual(selection, _selection())  # frozen dataclass equality

    def test_source_url_not_string_coerced(self):
        # A normal string must be preserved exactly, no str() round-trip.
        exact_url = "https://example.com/päth?x=1#frag"
        result = build_selected_content_candidate(
            _processed(discovery=_raw_discovery(url=exact_url)), _selection()
        )
        self.assertEqual(result.candidate.source_url, exact_url)

    def test_deterministic_equal_values(self):
        first = build_selected_content_candidate(_processed(), _selection())
        second = build_selected_content_candidate(_processed(), _selection())
        self.assertEqual(first.candidate, second.candidate)
        self.assertEqual(first.verification, second.verification)
        self.assertEqual(first.score, second.score)
        self.assertEqual(first.selection, second.selection)
        self.assertIs(first.stage, second.stage)
        self.assertIsNone(second.content_id)


# ──────────────────────────────────────────────────────────────────────
# Structural AST guarantees (docstring-immune by construction).
# ──────────────────────────────────────────────────────────────────────

def _code_text(path: Path) -> str:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node.body and isinstance(node.body[0], ast.Expr) and \
                    isinstance(node.body[0].value, ast.Constant) and \
                    isinstance(node.body[0].value.value, str):
                node.body = node.body[1:]
    return ast.unparse(tree)


class TestStructuralBoundaries(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = _code_text(SOURCE_PATH)
        cls.tree = ast.parse(SOURCE_PATH.read_text(encoding="utf-8"))

    def _function(self):
        for node in ast.walk(self.tree):
            if isinstance(node, ast.FunctionDef) \
                    and node.name == "build_selected_content_candidate":
                return node
        raise AssertionError("build_selected_content_candidate not found")

    def test_no_ranked_candidate_reference(self):
        self.assertNotIn("RankedCandidate", self.text)

    def test_no_forbidden_tokens(self):
        forbidden = (
            "ResearchResult", "RankingResult", "select_shortlist_winner",
            "select_ranked_candidate", "score_candidate", "verify_provenance",
            "classify", "rank_candidates", "src.main", "src.agents", "Config",
            "sqlite3", "random", "datetime", "open", "requests", "urllib",
            "socket", "os", "yaml",
        )
        for token in forbidden:
            self.assertNotIn(token, self.text)

    def test_stage_explicitly_selected(self):
        fn = self._function()
        stage_values = [
            node.value.attr
            for node in ast.walk(fn)
            if isinstance(node, ast.keyword)
            and node.arg == "stage"
            and isinstance(node.value, ast.Attribute)
        ]
        self.assertEqual(stage_values, ["SELECTED"])

    def test_content_id_explicitly_none(self):
        fn = self._function()
        content_id_values = [
            node.value.value
            for node in ast.walk(fn)
            if isinstance(node, ast.keyword)
            and node.arg == "content_id"
            and isinstance(node.value, ast.Constant)
        ]
        self.assertEqual(content_id_values, [None])

    def test_metadata_copied_with_dict_call(self):
        fn = self._function()
        metadata_copies = [
            node
            for node in ast.walk(fn)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "dict"
            and node.args
            and isinstance(node.args[0], ast.Attribute)
            and node.args[0].attr == "metadata"
        ]
        self.assertEqual(len(metadata_copies), 1)


if __name__ == "__main__":
    unittest.main()
