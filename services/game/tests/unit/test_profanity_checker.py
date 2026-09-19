"""BetterProfanityChecker tests, against the real library (no fake)."""

from __future__ import annotations

from infrastructure.profanity_checker import BetterProfanityChecker


class TestBetterProfanityChecker:
    def test_flags_a_clear_slur(self) -> None:
        checker = BetterProfanityChecker()
        assert checker.is_offensive("fuck you") is True

    def test_does_not_flag_a_clean_technical_answer(self) -> None:
        checker = BetterProfanityChecker()
        answer = "groups related database changes into one transactional unit"
        assert checker.is_offensive(answer) is False

    def test_does_not_flag_empty_answer(self) -> None:
        checker = BetterProfanityChecker()
        assert checker.is_offensive("") is False
