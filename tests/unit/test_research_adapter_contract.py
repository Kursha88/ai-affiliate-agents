"""Unit tests for the Researcher 2.0 source-adapter contract (Stage 3.2 Step 2).

Scope: RawDiscovery construction, SourceAdapter contract (explicit
name/source_type, failure isolation via safe_fetch/fetch_result) and the
source-neutrality boundary. All tests are offline — adapters here are
in-memory fakes; no network calls occur.

Out of scope: classification, verification, scoring, ranking, concrete
HN/GitHub/RSS adapters (later steps), any future orchestrator behavior.
"""

import unittest
from dataclasses import FrozenInstanceError

from src.domain.strategy import SourceType
from src.research.adapters import (
    AdapterFetchResult,
    RawDiscovery,
    SourceAdapter,
)


def make_raw_discovery(**overrides) -> RawDiscovery:
    base = dict(
        title="Some new AI tool",
        url="https://example.com/tool?utm_source=x",
        source_name="Example Source",
        discovered_at="2026-09-08T10:00:00Z",
    )
    base.update(overrides)
    return RawDiscovery(**base)


class _StaticAdapter(SourceAdapter):
    """Fake adapter returning canned results without any I/O."""

    def __init__(self, results=None, exc: Exception = None) -> None:
        super().__init__()
        self._results = list(results or [])
        self._exc = exc
        self.fetch_calls = 0

    @property
    def name(self) -> str:
        return "static"

    @property
    def source_type(self) -> SourceType:
        return SourceType.OTHER

    def fetch(self):
        self.fetch_calls += 1
        if self._exc is not None:
            raise self._exc
        return list(self._results)


class TestRawDiscovery(unittest.TestCase):
    def test_minimal_construction(self) -> None:
        record = make_raw_discovery()
        self.assertEqual(record.title, "Some new AI tool")
        self.assertIsNone(record.published_at)
        self.assertEqual(record.summary, "")
        self.assertIsNone(record.raw_score)
        self.assertEqual(record.identifiers, {})
        self.assertEqual(record.metadata, {})

    def test_provenance_fields(self) -> None:
        record = RawDiscovery(
            title="Story",
            url="https://example.com/a",
            source_name="Hacker News",
            discovered_at="2026-09-08T10:00:00Z",
            published_at="2026-09-08T09:00:00Z",
            raw_score=128,
            raw_score_label="hn_points",
            comments_count=45,
            identifiers={"hn_item_id": "12345"},
            metadata={"author": "alice", "age_hours": 2.5},
        )
        self.assertEqual(record.raw_score_label, "hn_points")
        self.assertEqual(record.identifiers["hn_item_id"], "12345")
        self.assertEqual(record.metadata["author"], "alice")

    def test_is_frozen(self) -> None:
        record = make_raw_discovery()
        with self.assertRaises(FrozenInstanceError):
            record.title = "mutated"

    def test_carries_no_classification_fields(self) -> None:
        # A RawDiscovery is deliberately NOT a DiscoveryCandidate: it must
        # have no cluster, verification or quality fields of any kind.
        record = make_raw_discovery()
        for forbidden in (
            "content_cluster",
            "verification",
            "score",
            "selection",
            "stage",
            "candidate_id",
        ):
            self.assertFalse(
                hasattr(record, forbidden),
                f"RawDiscovery must not carry pre-classified field '{forbidden}'",
            )


class TestSourceAdapterContract(unittest.TestCase):
    def test_explicit_name_and_source_type_required(self) -> None:
        # Subclasses must declare both explicitly; there is no default.
        class _Partial(SourceAdapter):
            fetch = SourceAdapter.fetch  # not implemented by subclass

        with self.assertRaises(TypeError):
            _Partial().name  # abstract property not overridden

        class _NoSourceType(SourceAdapter):
            @property
            def name(self) -> str:
                return "no_type"

            def fetch(self):
                return []

        with self.assertRaises(TypeError):
            _NoSourceType()  # source_type left abstract

    def test_contract_boundary_is_abstract(self) -> None:
        with self.assertRaises(TypeError):
            SourceAdapter()  # type: ignore[abstract]

    def test_adapter_returns_raw_discoveries(self) -> None:
        adapter = _StaticAdapter([make_raw_discovery(), make_raw_discovery(title="Two")])
        results = adapter.safe_fetch()
        self.assertEqual(len(results), 2)
        self.assertTrue(all(isinstance(r, RawDiscovery) for r in results))
        self.assertIsNone(adapter.last_error)

    def test_expected_failure_returns_empty_list(self) -> None:
        class _Failing(_StaticAdapter):
            def fetch(self):
                super().fetch()
                return []  # adapter swallowed its own source failure

        adapter = _Failing()
        self.assertEqual(adapter.safe_fetch(), [])
        self.assertIsNone(adapter.last_error)

    def test_safe_fetch_isolates_unexpected_exceptions(self) -> None:
        adapter = _StaticAdapter(exc=RuntimeError("connection reset"))
        results = adapter.safe_fetch()
        self.assertEqual(results, [])
        self.assertIsNotNone(adapter.last_error)
        self.assertIn("RuntimeError", adapter.last_error)
        self.assertIn("connection reset", adapter.last_error)

    def test_safe_fetch_recovers_after_failure(self) -> None:
        adapter = _StaticAdapter([make_raw_discovery()])
        adapter.last_error = "stale error from previous cycle"
        results = adapter.safe_fetch()
        self.assertEqual(len(results), 1)
        self.assertIsNone(adapter.last_error)  # cleared on next successful run

    def test_safe_fetch_rejects_none_return(self) -> None:
        class _ReturnsNone(_StaticAdapter):
            def fetch(self):
                self.fetch_calls += 1
                return None

        adapter = _ReturnsNone()
        self.assertEqual(adapter.safe_fetch(), [])
        self.assertIsNotNone(adapter.last_error)
        self.assertIn("None", adapter.last_error)

    def test_fetch_result_envelope_success(self) -> None:
        adapter = _StaticAdapter([make_raw_discovery()])
        result = adapter.fetch_result()
        self.assertIsInstance(result, AdapterFetchResult)
        self.assertTrue(result.ok)
        self.assertIsNone(result.error)
        self.assertEqual(result.adapter_name, "static")
        self.assertEqual(result.source_type, SourceType.OTHER)
        self.assertEqual(len(result.discoveries), 1)

    def test_fetch_result_envelope_failure(self) -> None:
        adapter = _StaticAdapter(exc=ValueError("bad payload"))
        result = adapter.fetch_result()
        self.assertFalse(result.ok)
        self.assertIsNotNone(result.error)
        self.assertEqual(result.discoveries, ())
        # The orchestrator can still identify the broken source.
        self.assertEqual(result.adapter_name, "static")

    def test_source_neutrality_of_contract(self) -> None:
        # The base contract exposes no classification/verification/scoring
        # hooks — those live in the Researcher pipeline, not in adapters.
        contract_members = set(vars(SourceAdapter))
        for forbidden in (
            "classify",
            "verify",
            "score",
            "rank",
            "deduplicate",
            "select",
        ):
            self.assertNotIn(forbidden, contract_members)


if __name__ == "__main__":
    unittest.main()
