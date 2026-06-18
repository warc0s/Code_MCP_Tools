from __future__ import annotations

import pytest

from utils.config import CrawlingConfig
from utils.crawling import MAX_CRAWLING_WORKERS, _safe_worker_count


@pytest.mark.parametrize(
    ("raw_workers", "expected"),
    [
        (0, 1),
        (-3, 1),
        (1, 1),
        (9999, MAX_CRAWLING_WORKERS),
    ],
)
def test_safe_worker_count_clamps_extreme_values(raw_workers, expected):
    assert _safe_worker_count(CrawlingConfig(workers=raw_workers)) == expected


def test_safe_worker_count_rejects_non_integer_values():
    with pytest.raises(ValueError, match="workers"):
        _safe_worker_count(CrawlingConfig(workers="many"))
