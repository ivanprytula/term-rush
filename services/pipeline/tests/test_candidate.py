"""Tests for confidence_rank."""

from __future__ import annotations

from pipeline_service.candidate import Confidence
from pipeline_service.candidate import confidence_rank


def test_confidence_rank_orders_curated_before_high_before_medium_before_low() -> None:
    ranked = sorted(Confidence, key=confidence_rank)

    assert ranked == [
        Confidence.CURATED,
        Confidence.HIGH,
        Confidence.MEDIUM,
        Confidence.LOW,
    ]
