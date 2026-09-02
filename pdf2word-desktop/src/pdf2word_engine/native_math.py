"""Detection helpers for editable inline Office Math spans."""

from __future__ import annotations

from dataclasses import dataclass
import re


# This deliberately targets the compact fractions used by the current Chinese
# exam source.  Dates and chained path-like values are excluded; more complex
# mathematics must be represented by a dedicated structured formula block.
_STACKED_FRACTION = re.compile(
    r"(?<![0-9A-Za-z])"
    r"(?P<numerator>(?:\d{1,3}|[A-Za-z]))/"
    r"(?P<denominator>(?:\d{1,3}|[A-Za-z])|\((?P<expression>[0-9A-Za-z+\-×÷.%％ ]+)\))"
    r"(?![0-9A-Za-z/])"
)


@dataclass(frozen=True, slots=True)
class FractionSpan:
    start: int
    end: int
    numerator: str
    denominator: str


def iter_stacked_fractions(value: str) -> tuple[FractionSpan, ...]:
    """Return editable stacked-fraction spans in source order."""

    spans: list[FractionSpan] = []
    for match in _STACKED_FRACTION.finditer(value):
        denominator = match.group("expression") or match.group("denominator")
        spans.append(
            FractionSpan(
                start=match.start(),
                end=match.end(),
                numerator=match.group("numerator"),
                denominator=denominator,
            )
        )
    return tuple(spans)


def stacked_fraction_count(value: str | None) -> int:
    return len(iter_stacked_fractions(value or ""))
