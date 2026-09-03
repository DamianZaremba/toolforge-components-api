from typing import Any

from components.storage.helpers import matches_query
from tests.helpers import cases


class TestMatchesQuery:
    # It's easier to test by itself
    @cases(
        "query,config",
        [
            "Matches direct non-nested key",
            [{"key1": "expected-value-1"}, {"key1": "expected-value-1"}],
        ],
        [
            "Matches direct nested key",
            [{"key1.key2": "expected-value-1"}, {"key1": {"key2": "expected-value-1"}}],
        ],
        [
            "Matches array nested key",
            [
                {"key1[].key2": "expected-value-1"},
                {"key1": [{"key2": "expected-value-1"}]},
            ],
        ],
        [
            "Matches array nested key with non-matching elements",
            [
                {"key1[].key2": "expected-value-1"},
                {
                    "key1": [
                        {"key2": "not expected-value-1"},
                        {"key2": "expected-value-1"},
                    ]
                },
            ],
        ],
    )
    def test_matches_correctly(self, query: dict[str, Any], config: dict[str, Any]):
        assert matches_query(matches=query, config=config)

    @cases(
        "query,config",
        [
            "Does not match direct non-nested key",
            [{"key1": "expected-value-1"}, {"key1": "not expected-value-1"}],
        ],
        [
            "Does not match direct nested key",
            [
                {"key1.key2": "expected-value-1"},
                {"key1": {"key2": "not expected-value-1"}},
            ],
        ],
        [
            "Does not match array nested key",
            [
                {"key1[].key2": "expected-value-1"},
                {"key1": [{"key2": "not expected-value-1"}]},
            ],
        ],
        [
            "Does not match array nested key with non-matching elements",
            [
                {"key1[].key2": "expected-value-1"},
                {
                    "key1": [
                        {"key2": "not expected-value-1"},
                        {"key2": "not expected-value-1"},
                    ]
                },
            ],
        ],
        [
            "Does not match direct non-nested missing key",
            [{"key1": "expected-value-1"}, {"not matching key": "expected-value-1"}],
        ],
        [
            "Does not match direct nested missing key",
            [
                {"key1.key2": "expected-value-1"},
                {"key1": {"not matching key": "expected-value-1"}},
            ],
        ],
        [
            "Does not match array nested missing key",
            [
                {"key1[].key2": "expected-value-1"},
                {"key1": [{"not matching key": "expected-value-1"}]},
            ],
        ],
    )
    def test_does_not_match(self, query: dict[str, Any], config: dict[str, Any]):
        assert not matches_query(matches=query, config=config)
