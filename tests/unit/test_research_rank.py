"""Unit tests for Stage 3.2 deterministic candidate ranking.

Covers the final Step 8 rules: highest total_score first with a
deterministic candidate_id tie-break, the classification requirement
(unclassified / ambiguous excluded, never mapped to ai_news), the
minimum quality threshold (below 4.0 excluded, exact 4.0 accepted),
the symmetric per-cluster cap (ai_news treated like any other cluster,
no CLUSTER_PRIORITY), the shortlist limit with limit_reached reasons,
strict input validation (invalid limit, duplicate candidate_id, invalid
CandidateScore, invalid ClassificationResult), determinism (repeated
calls, input order independence), purity (no input mutation), and
structural guarantees (no network/DB/selection/publishing imports, no
random/time calls, no source preference, no StrategicSelection
construction, no MIN_CONFIDENCE_FOR_SELECTION / CLUSTER_PRIORITY).

All inputs are in-memory; no network access.
"""

from __future__ import annotations

import ast
import copy
import inspect
import unittest

from src.domain.strategy import (
    CandidateScore,
    ContentCluster,
    VerificationStatus,
)
from src.research.classify import ClassificationResult
from src.research.rank import (
    DEFAULT_LIMIT,
    MAX_PER_CLUSTER,
    MIN_RANK_SCORE,
    REASON_AMBIGUOUS,
    REASON_BELOW_QUALITY_THRESHOLD,
    REASON_CLUSTER_CAP,
    REASON_LIMIT_REACHED,
    REASON_UNCLASSIFIED,
    ExcludedCandidate,
    RankableCandidate,
    RankedCandidate,
    RankingResult,
    rank_candidates,
)


def make_score(total: float) -> CandidateScore:
    """CandidateScore whose computed total_score equals ``total``.

    All six components are set to ``total``; because
    ``DEFAULT_SCORING_WEIGHTS`` sum to exactly 1.0, the computed
    ``total_score`` equals ``total`` (valid for 0 <= total <= 10).
    """
    value = round(float(total), 4)
    return CandidateScore(
        novelty=value,
        practical_utility=value,
        free_availability=value,
        audience_interest=value,
        viral_potential=value,
        credibility=value,
    )


def make_classification(
    cluster: str | None = "ai_tools",
    ambiguous: bool = False,
) -> ClassificationResult:
    return ClassificationResult(
        cluster=ContentCluster(cluster) if cluster else None,
        confidence=0.8 if cluster else 0.0,
        scores={},
        matched_rules=(),
        ambiguous=ambiguous,
        reason="classified" if cluster else ("ambiguous_margin" if ambiguous else "no_signals"),
    )


def make_candidate(
    candidate_id: str,
    cluster: str | None = "ai_tools",
    total: float = 8.0,
    ambiguous: bool = False,
    source_name: str = "hacker_news",
    source_url: str | None = "https://example.com/x",
) -> RankableCandidate:
    return RankableCandidate(
        candidate_id=candidate_id,
        classification=make_classification(cluster, ambiguous),
        score=make_score(total),
        source_name=source_name,
        source_url=source_url,
    )


# ══════════════════════════════════════════════════════════════════════
# Ordering and tie-breaks
# ══════════════════════════════════════════════════════════════════════


class TestOrdering(unittest.TestCase):
    def test_highest_score_first(self):
        result = rank_candidates(
            [
                make_candidate("c-low", total=5.0),
                make_candidate("a-high", total=9.0, cluster="vibe_coding"),
                make_candidate("b-mid", total=7.0, cluster="ai_agents"),
            ]
        )
        self.assertEqual(
            [item.candidate_id for item in result.ranked],
            ["a-high", "b-mid", "c-low"],
        )
        self.assertEqual(
            [item.rank for item in result.ranked], [1, 2, 3]
        )
        self.assertEqual(result.ranked[0].final_rank_score, 9.0)

    def test_deterministic_candidate_id_tie_break(self):
        result = rank_candidates(
            [
                make_candidate("zz", total=8.0, cluster="vibe_coding"),
                make_candidate("aa", total=8.0, cluster="ai_agents"),
                make_candidate("mm", total=8.0, cluster="ai_tools"),
            ]
        )
        self.assertEqual(
            [item.candidate_id for item in result.ranked],
            ["aa", "mm", "zz"],
        )

    def test_input_order_does_not_affect_result(self):
        candidates = [
            make_candidate("a", total=9.0, cluster="vibe_coding"),
            make_candidate("b", total=9.0, cluster="ai_agents"),
            make_candidate("c", total=4.5, cluster="ai_tools"),
            make_candidate("d", total=3.0, cluster="automation"),
            make_candidate("e", cluster=None),
            make_candidate("f", total=8.0, cluster="ai_news"),
            make_candidate("g", total=8.5, cluster="ai_news"),
            make_candidate("h", total=7.5, cluster="ai_news"),
        ]
        forward = rank_candidates(candidates)
        backward = rank_candidates(list(reversed(candidates)))
        self.assertEqual(forward, backward)

    def test_stable_repeated_calls(self):
        candidates = [
            make_candidate("a", total=9.0, cluster="vibe_coding"),
            make_candidate("b", total=5.0, cluster=None, ambiguous=True),
            make_candidate("c", total=8.0, cluster="free_ai"),
        ]
        self.assertEqual(rank_candidates(candidates), rank_candidates(candidates))

    def test_no_source_name_ranking_bonus(self):
        # Identical scores, different sources: ranking is source-blind.
        result = rank_candidates(
            [
                make_candidate("n1", total=8.0, cluster="vibe_coding", source_name="hacker_news"),
                make_candidate("n2", total=8.0, cluster="ai_agents", source_name="github"),
                make_candidate("n3", total=8.0, cluster="ai_tools", source_name="official_blog"),
            ]
        )
        self.assertEqual(
            {item.final_rank_score for item in result.ranked}, {8.0}
        )
        # Pure id tie-break, no source influence on the order.
        self.assertEqual(
            [item.candidate_id for item in result.ranked], ["n1", "n2", "n3"]
        )


# ══════════════════════════════════════════════════════════════════════
# Classification requirement and quality threshold
# ══════════════════════════════════════════════════════════════════════


class TestExclusions(unittest.TestCase):
    def test_unclassified_excluded(self):
        result = rank_candidates([make_candidate("a", cluster=None, ambiguous=False)])
        self.assertEqual(result.output_count, 0)
        self.assertEqual(result.excluded[0].reason, REASON_UNCLASSIFIED)

    def test_ambiguous_excluded(self):
        result = rank_candidates([make_candidate("a", cluster=None, ambiguous=True)])
        self.assertEqual(result.output_count, 0)
        self.assertEqual(result.excluded[0].reason, REASON_AMBIGUOUS)

    def test_no_silent_ai_news_fallback(self):
        # Unclassified candidates must never be re-labeled ai_news.
        result = rank_candidates(
            [make_candidate("a", cluster=None), make_candidate("b", cluster=None, ambiguous=True)]
        )
        self.assertTrue(
            all(item.cluster is None for item in result.excluded)
        )
        self.assertEqual(result.output_count, 0)

    def test_below_threshold_excluded(self):
        result = rank_candidates([make_candidate("a", total=3.999)])
        self.assertEqual(result.output_count, 0)
        self.assertEqual(result.excluded[0].reason, REASON_BELOW_QUALITY_THRESHOLD)
        self.assertEqual(result.excluded[0].total_score, 3.999)

    def test_exact_threshold_accepted(self):
        result = rank_candidates([make_candidate("a", total=MIN_RANK_SCORE)])
        self.assertEqual(result.output_count, 1)
        self.assertEqual(result.ranked[0].final_rank_score, MIN_RANK_SCORE)

    def test_threshold_constant_visible(self):
        self.assertEqual(MIN_RANK_SCORE, 4.0)


# ══════════════════════════════════════════════════════════════════════
# Cluster diversity
# ══════════════════════════════════════════════════════════════════════


class TestClusterDiversity(unittest.TestCase):
    def test_max_two_per_cluster(self):
        result = rank_candidates(
            [
                make_candidate("a1", total=9.0, cluster="vibe_coding"),
                make_candidate("a2", total=8.0, cluster="vibe_coding"),
                make_candidate("a3", total=7.0, cluster="vibe_coding"),
            ]
        )
        self.assertEqual(result.output_count, MAX_PER_CLUSTER)
        self.assertEqual(
            [item.candidate_id for item in result.ranked], ["a1", "a2"]
        )
        self.assertEqual(result.excluded[0].candidate_id, "a3")
        self.assertEqual(result.excluded[0].reason, REASON_CLUSTER_CAP)

    def test_multiple_clusters_preserved(self):
        result = rank_candidates(
            [
                make_candidate("v1", total=9.0, cluster="vibe_coding"),
                make_candidate("g1", total=8.5, cluster="ai_agents"),
                make_candidate("t1", total=8.0, cluster="ai_tools"),
                make_candidate("v2", total=7.5, cluster="vibe_coding"),
                make_candidate("g2", total=7.0, cluster="ai_agents"),
                make_candidate("t2", total=6.5, cluster="ai_tools"),
            ]
        )
        self.assertEqual(result.output_count, 6)
        self.assertEqual(
            [item.cluster for item in result.ranked],
            [
                ContentCluster.VIBE_CODING,
                ContentCluster.AI_AGENTS,
                ContentCluster.AI_TOOLS,
                ContentCluster.VIBE_CODING,
                ContentCluster.AI_AGENTS,
                ContentCluster.AI_TOOLS,
            ],
        )

    def test_ai_news_treated_like_any_other_cluster(self):
        # No ban, no hidden penalty: top ai_news candidate ranks first.
        result = rank_candidates(
            [
                make_candidate("n1", total=9.0, cluster="ai_news"),
                make_candidate("t1", total=8.0, cluster="ai_tools"),
            ]
        )
        self.assertEqual(result.ranked[0].candidate_id, "n1")
        self.assertEqual(result.ranked[0].cluster, ContentCluster.AI_NEWS)
        self.assertEqual(result.ranked[0].reason, "ranked:ai_news")

        # And it obeys exactly the same symmetric cap.
        capped = rank_candidates(
            [
                make_candidate("n1", total=9.0, cluster="ai_news"),
                make_candidate("n2", total=8.0, cluster="ai_news"),
                make_candidate("n3", total=7.0, cluster="ai_news"),
            ]
        )
        self.assertEqual(capped.output_count, MAX_PER_CLUSTER)
        self.assertEqual(capped.excluded[0].reason, REASON_CLUSTER_CAP)


# ══════════════════════════════════════════════════════════════════════
# Limit
# ══════════════════════════════════════════════════════════════════════


class TestLimit(unittest.TestCase):
    def _six_eligible(self):
        return [
            make_candidate("a", total=9.0, cluster="vibe_coding"),
            make_candidate("b", total=8.5, cluster="ai_agents"),
            make_candidate("c", total=8.0, cluster="ai_tools"),
            make_candidate("d", total=7.5, cluster="free_ai"),
            make_candidate("e", total=7.0, cluster="automation"),
            make_candidate("f", total=6.5, cluster="free_ai"),
        ]

    def test_limit_respected(self):
        result = rank_candidates(self._six_eligible(), limit=4)
        self.assertEqual(result.output_count, 4)
        self.assertEqual(len(result.ranked), 4)
        self.assertEqual(result.input_count, 6)

    def test_limit_reached_reason(self):
        result = rank_candidates(self._six_eligible(), limit=2)
        self.assertEqual(
            [item.candidate_id for item in result.ranked], ["a", "b"]
        )
        self.assertEqual(
            [(item.candidate_id, item.reason) for item in result.excluded],
            [("c", REASON_LIMIT_REACHED), ("d", REASON_LIMIT_REACHED),
             ("e", REASON_LIMIT_REACHED), ("f", REASON_LIMIT_REACHED)],
        )

    def test_default_limit_is_ten(self):
        self.assertEqual(DEFAULT_LIMIT, 10)
        many = [
            make_candidate(f"c{i:02d}", total=9.0 - i * 0.1,
                           cluster=["vibe_coding", "ai_agents", "ai_tools", "automation",
                                    "free_ai", "practical_experiments", "ai_news"][i % 7])
            for i in range(21)
        ]
        result = rank_candidates(many)
        self.assertEqual(result.output_count, 10)

    def test_invalid_limit_raises(self):
        for bad in (0, -1, 1.5, "10", None, True):
            with self.subTest(limit=bad):
                with self.assertRaises(ValueError):
                    rank_candidates(self._six_eligible(), limit=bad)


# ══════════════════════════════════════════════════════════════════════
# Input validation
# ══════════════════════════════════════════════════════════════════════


class TestInputValidation(unittest.TestCase):
    def test_duplicate_candidate_id_raises(self):
        with self.assertRaises(ValueError):
            rank_candidates(
                [
                    make_candidate("dup", total=9.0, cluster="vibe_coding"),
                    make_candidate("dup", total=5.0, cluster="ai_tools"),
                ]
            )

    def test_invalid_candidate_score_raises(self):
        from src.domain.strategy import validate_score

        bad_score = CandidateScore(
            novelty=99.0,  # out of 0..10 range
            practical_utility=5.0,
            free_availability=5.0,
            audience_interest=5.0,
            viral_potential=5.0,
            credibility=5.0,
        )
        self.assertFalse(validate_score(bad_score)["valid"])
        with self.assertRaises(ValueError):
            rank_candidates(
                [
                    RankableCandidate(
                        candidate_id="bad",
                        classification=make_classification(),
                        score=bad_score,
                    )
                ]
            )

    def test_invalid_classification_type_raises(self):
        # Step 7 style: TypeError for a wrong result-object type.
        with self.assertRaises(TypeError):
            rank_candidates(
                [
                    RankableCandidate(
                        candidate_id="bad",
                        classification="classified",  # type: ignore[arg-type]
                        score=make_score(8.0),
                    )
                ]
            )

    def test_validation_is_fail_fast_whole_input(self):
        # A duplicate id invalidates the whole call even when it appears
        # after otherwise-valid entries.
        with self.assertRaises(ValueError):
            rank_candidates(
                [
                    make_candidate("ok1", total=9.0, cluster="vibe_coding"),
                    make_candidate("ok2", total=8.0, cluster="ai_agents"),
                    make_candidate("ok1", total=7.0, cluster="ai_tools"),
                ]
            )


# ══════════════════════════════════════════════════════════════════════
# Result shape, counts, purity
# ══════════════════════════════════════════════════════════════════════


class TestResultShapeAndPurity(unittest.TestCase):
    def test_empty_input(self):
        result = rank_candidates([])
        self.assertEqual(result.ranked, ())
        self.assertEqual(result.excluded, ())
        self.assertEqual(result.input_count, 0)
        self.assertEqual(result.output_count, 0)

    def test_result_counts_and_shape(self):
        result = rank_candidates(
            [
                make_candidate("a", total=9.0, cluster="vibe_coding"),
                make_candidate("b", total=5.0, cluster=None),
                make_candidate("c", total=3.0, cluster="ai_tools"),
                make_candidate("d", total=8.0, cluster="ai_tools"),
                make_candidate("e", total=7.5, cluster="ai_tools"),
                make_candidate("f", total=7.0, cluster="ai_tools"),  # third ai_tools
            ]
        )
        self.assertIsInstance(result, RankingResult)
        self.assertEqual(result.input_count, 6)
        self.assertEqual(result.output_count, 3)
        self.assertEqual(len(result.ranked) + len(result.excluded), 6)
        self.assertEqual(
            {item.candidate_id for item in result.ranked}, {"a", "d", "e"}
        )
        self.assertEqual(
            {item.reason for item in result.excluded},
            {REASON_UNCLASSIFIED, REASON_BELOW_QUALITY_THRESHOLD, REASON_CLUSTER_CAP},
        )
        self.assertEqual(
            {item.candidate_id for item in result.excluded if item.reason == REASON_CLUSTER_CAP},
            {"f"},
        )
        top = result.ranked[0]
        self.assertIsInstance(top, RankedCandidate)
        self.assertEqual(
            set(top.__dataclass_fields__),
            {"candidate_id", "rank", "score", "cluster", "final_rank_score", "reason"},
        )
        excluded = result.excluded[0]
        self.assertIsInstance(excluded, ExcludedCandidate)
        self.assertEqual(
            set(excluded.__dataclass_fields__),
            {"candidate_id", "reason", "total_score", "cluster"},
        )
        self.assertEqual(
            set(result.__dataclass_fields__),
            {"ranked", "excluded", "input_count", "output_count"},
        )

    def test_to_dict_observable(self):
        result = rank_candidates(
            [make_candidate("a", total=9.0, cluster="vibe_coding")]
        )
        payload = result.to_dict()
        self.assertEqual(payload["input_count"], 1)
        self.assertEqual(payload["output_count"], 1)
        self.assertEqual(payload["ranked"][0]["candidate_id"], "a")
        self.assertEqual(payload["ranked"][0]["cluster"], "vibe_coding")

    def test_input_objects_not_mutated(self):
        candidates = [
            make_candidate("a", total=9.0, cluster="vibe_coding", source_url="https://x.io/a"),
            make_candidate("b", total=3.0, cluster="ai_tools"),
            make_candidate("c", total=8.0, cluster="ai_tools"),
            make_candidate("d", total=8.5, cluster="ai_tools"),
        ]
        snapshot = copy.deepcopy(candidates)
        rank_candidates(candidates, limit=2)
        self.assertEqual(candidates, snapshot)


# ══════════════════════════════════════════════════════════════════════
# Structural guarantees (whole module, docstrings stripped)
# ══════════════════════════════════════════════════════════════════════


class TestStructuralGuarantees(unittest.TestCase):
    """AST-level guarantees about the rank module's CODE.

    Docstrings are stripped before text scans: the module legitimately
    documents forbidden concepts; the guarantee is that code never uses
    them.
    """

    @classmethod
    def _module_source(cls) -> str:
        from src.research import rank as rank_module

        return inspect.getsource(rank_module)

    @classmethod
    def _code_source(cls) -> str:
        tree = ast.parse(cls._module_source())
        for node in ast.walk(tree):
            if isinstance(
                node,
                (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef),
            ):
                body = node.body
                if (
                    body
                    and isinstance(body[0], ast.Expr)
                    and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)
                ):
                    node.body = body[1:]
        return ast.unparse(tree)

    def _imports(self) -> set:
        imported = set()
        for node in ast.walk(ast.parse(self._module_source())):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imported.add(node.module or "")
        return imported

    def _names(self) -> set:
        return {
            node.id
            for node in ast.walk(ast.parse(self._code_source()))
            if isinstance(node, ast.Name)
        }

    def _calls(self) -> set:
        calls = set()
        for node in ast.walk(ast.parse(self._code_source())):
            if isinstance(node, ast.Call):
                target = node.func
                if isinstance(target, ast.Name):
                    calls.add(target.id)
                elif isinstance(target, ast.Attribute):
                    calls.add(target.attr)
        return calls

    def test_no_network_db_selection_publishing_imports(self):
        imported = self._imports()
        forbidden = {
            "requests", "urllib", "urllib.request", "socket", "http", "httpx",
            "sqlite3", "subprocess", "os", "pathlib", "random", "time",
            "src.main", "src.storage", "src.factory", "src.agents", "src.integrations",
            "src.research.verify", "src.research.normalize",
            "src.research.adapters",
        }
        self.assertFalse(imported & forbidden)

    def test_no_random_or_time_calls(self):
        source = self._code_source()
        self.assertNotIn("random", source)
        self.assertNotIn("datetime.now", source)
        self.assertNotIn("utcnow", source)
        self.assertEqual(self._calls() & {"random", "now", "utcnow", "time"}, set())

    def test_no_strategic_selection_or_selection_constant(self):
        self.assertNotIn("StrategicSelection", self._names())
        self.assertNotIn("MIN_CONFIDENCE_FOR_SELECTION", self._code_source())

    def test_no_cluster_priority(self):
        self.assertNotIn("CLUSTER_PRIORITY", self._code_source())

    def test_no_component_weight_recomputation(self):
        # Ranking must not recompute scoring internals: no scoring-module
        # import, no DEFAULT_SCORING_WEIGHTS use.
        self.assertNotIn("src.research.score", self._imports())
        self.assertNotIn("DEFAULT_SCORING_WEIGHTS", self._names())
        self.assertNotIn("score_candidate", self._names())

    def test_base_score_is_total_score(self):
        source = self._code_source()
        self.assertIn("total_score", source)
        self.assertIn("MIN_RANK_SCORE", source)


if __name__ == "__main__":
    unittest.main()
