"""Outcome-blind BTC ladder settlement-rule regime validation.

This module validates only settlement-rule semantics and raw lineage. It never
reads or materializes market outcomes, prices, volume, or liquidity fields.

The key research lesson is that a Kalshi Series ticker is not automatically one
stationary settlement contract through time. The parser therefore recognizes a
small, explicit set of settlement mechanisms and lets callers partition sampled
events by semantic signature instead of forcing one full-history template.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
import hashlib
import json
import re
from typing import Any, Iterable, Mapping, Sequence


class BtcRuleTemplateError(RuntimeError):
    """Raised when rule semantics or raw lineage cannot be proven safely."""


_TARGET_SERIES = ("KXBTC", "KXBTCD")
_DEFAULT_RELATION = {"KXBTC": "between", "KXBTCD": "above"}
_ALLOWED_RELATIONS = {"KXBTC": {"below", "between", "above"}, "KXBTCD": {"above"}}
_STRIKE_TYPE_RELATION = {"less": "below", "between": "between", "greater": "above"}

_TRIMMED_MECHANISM_RE = re.compile(
    r"average of the (?P<window>five minutes|sixty seconds|60 seconds) of "
    r"CF Benchmarks['’] Bitcoin Real-Time Index \(BRTI\) before "
    r"(?P<measurement_time>[^,]+), excluding the top 20% and bottom 20% of values",
    re.IGNORECASE,
)

_SIMPLE_PRIMARY_MECHANISM_RE = re.compile(
    r"simple average of the (?:sixty|60) seconds of "
    r"CF Benchmarks['’] Bitcoin Real-Time Index \(BRTI\) before "
    r"(?P<measurement_time>.+?)\s+is\s+(?:between|above|below)\b",
    re.IGNORECASE,
)

_MODERN_TRIMMED_SECONDARY_RE = re.compile(
    r"CF Benchmarks['’] corresponding Real Time Index \(RTI\).*?"
    r"last minute before expiration,\s*60 RTI prices are\s*collected\.\s*"
    r"The official and final value is the average of these prices,\s*"
    r"excluding the top 20%(?: \(12\))? and bottom 20%(?: \(12\))? "
    r"of collected prices",
    re.IGNORECASE,
)

_SIMPLE_SECONDARY_RE = re.compile(
    r"CF Benchmarks['’] corresponding Real Time Index \(RTI\).*?"
    r"last minute before expiration,\s*60 RTI prices are\s*collected\.\s*"
    r"The official and final value is the average of these prices",
    re.IGNORECASE,
)

_BETWEEN_RE = re.compile(
    r"is between\s+(?P<lower>-?\d+(?:\.\d+)?)-(?P<upper>-?\d+(?:\.\d+)?)\s+"
    r"at\s+(?P<settlement_time>.+?)\s+on\s+(?P<settlement_date>.+?),\s*"
    r"then the market resolves to Yes\.?(?:\s|$)",
    re.IGNORECASE,
)

_ABOVE_RE = re.compile(
    r"is above\s+(?P<threshold>-?\d+(?:\.\d+)?)\s+"
    r"at\s+(?P<settlement_time>.+?)\s+on\s+(?P<settlement_date>.+?),\s*"
    r"then the market resolves to Yes\.?(?:\s|$)",
    re.IGNORECASE,
)

_BELOW_RE = re.compile(
    r"is below\s+(?P<threshold>-?\d+(?:\.\d+)?)\s+"
    r"at\s+(?P<settlement_time>.+?)\s+on\s+(?P<settlement_date>.+?),\s*"
    r"then the market resolves to Yes\.?(?:\s|$)",
    re.IGNORECASE,
)

_RELATION_RE = {
    "between": _BETWEEN_RE,
    "above": _ABOVE_RE,
    "below": _BELOW_RE,
}


@dataclass(frozen=True)
class RuleSemanticSignature:
    index_provider: str
    index_name: str
    window_seconds: int
    statistic: str
    trim_top_pct: int
    trim_bottom_pct: int
    payoff_relation: str

    @property
    def regime_id(self) -> str:
        trim = (
            f"trim{self.trim_bottom_pct}_{self.trim_top_pct}"
            if self.statistic == "trimmed_mean"
            else "untrimmed"
        )
        return (
            f"brti_{self.window_seconds}s_{self.statistic}_{trim}_"
            f"{self.payoff_relation}"
        )


@dataclass(frozen=True)
class RuleValidationSample:
    series_ticker: str
    sample_position: str
    event_ticker: str
    market_ticker: str
    close_time: str
    raw_source: str
    raw_session_id: str
    raw_request_id: str
    route_tier: str
    primary_sha256: str
    secondary_sha256: str
    measurement_clock_label: str
    settlement_date_label: str
    signature: RuleSemanticSignature

    def as_json(self) -> dict[str, Any]:
        result = asdict(self)
        result["signature"] = asdict(self.signature)
        result["regime_id"] = self.signature.regime_id
        return result


@dataclass(frozen=True)
class RuleRegimeSummary:
    regime_id: str
    signature: RuleSemanticSignature
    sample_count: int
    earliest_observed_close_time: str
    latest_observed_close_time: str
    event_tickers: tuple[str, ...]

    def as_json(self) -> dict[str, Any]:
        return {
            "regime_id": self.regime_id,
            "signature": asdict(self.signature),
            "sample_count": self.sample_count,
            "earliest_observed_close_time": self.earliest_observed_close_time,
            "latest_observed_close_time": self.latest_observed_close_time,
            "event_tickers": list(self.event_tickers),
        }


def normalize_rule_text(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise BtcRuleTemplateError("rule text must be non-empty")
    return " ".join(value.replace("’", "'").split())


def parse_rule_semantics(
    *,
    series_ticker: str,
    rules_primary: str,
    rules_secondary: str,
    expected_relation: str | None = None,
) -> tuple[RuleSemanticSignature, str, str]:
    """Parse one ladder contract without using its outcome.

    Returns ``(semantic_signature, measurement_clock_label, date_label)``.
    Dynamic clock/date/strike values are validated for internal consistency but
    are excluded from the semantic signature.

    Recognized settlement mechanisms are intentionally narrow:
    * 5-minute BRTI trimmed mean, dropping top/bottom 20%;
    * 60-second BRTI trimmed mean, dropping top/bottom 20%;
    * 60-second simple BRTI/RTI mean with 60 final-minute RTI observations.

    Any other wording/mechanism fails closed instead of being guessed into one
    of these regimes.
    """

    if series_ticker not in _ALLOWED_RELATIONS:
        raise BtcRuleTemplateError(f"unsupported BTC ladder series: {series_ticker}")
    if expected_relation is None:
        expected_relation = _DEFAULT_RELATION[series_ticker]
    if expected_relation not in _ALLOWED_RELATIONS[series_ticker]:
        raise BtcRuleTemplateError(
            f"unsupported payoff relation {expected_relation!r} for {series_ticker}"
        )

    primary = normalize_rule_text(rules_primary)
    secondary = normalize_rule_text(rules_secondary)

    relation_match = _RELATION_RE[expected_relation].search(primary)
    if relation_match is None:
        raise BtcRuleTemplateError(
            f"{series_ticker} primary rule no longer proves payoff relation "
            f"{expected_relation!r}"
        )
    settlement_time = _norm_label(relation_match.group("settlement_time"))

    signature, measurement_time = _parse_measurement_mechanism(
        series_ticker=series_ticker,
        primary=primary,
        secondary=secondary,
        payoff_relation=expected_relation,
    )

    if settlement_time != measurement_time:
        raise BtcRuleTemplateError(
            f"{series_ticker} measurement and payoff settlement clock labels "
            f"disagree: {measurement_time!r} vs {settlement_time!r}"
        )

    return (
        signature,
        measurement_time,
        relation_match.group("settlement_date").strip(),
    )


def _parse_measurement_mechanism(
    *,
    series_ticker: str,
    primary: str,
    secondary: str,
    payoff_relation: str,
) -> tuple[RuleSemanticSignature, str]:
    primary_trimmed = _TRIMMED_MECHANISM_RE.search(primary)
    secondary_trimmed = _TRIMMED_MECHANISM_RE.search(secondary)
    modern_secondary_trimmed = _MODERN_TRIMMED_SECONDARY_RE.search(secondary)

    if secondary_trimmed is not None:
        secondary_window = _window_seconds(secondary_trimmed.group("window"))
        secondary_time = _norm_label(secondary_trimmed.group("measurement_time"))

        if primary_trimmed is not None:
            primary_window = _window_seconds(primary_trimmed.group("window"))
            primary_time = _norm_label(primary_trimmed.group("measurement_time"))
            if primary_window != secondary_window or primary_time != secondary_time:
                raise BtcRuleTemplateError(
                    f"{series_ticker} primary/secondary trimmed-average mechanism "
                    "disagrees"
                )

        # Some older KXBTC primary rules state only "price of Bitcoin" while
        # the secondary rule supplies the authoritative BRTI measurement.
        return (
            RuleSemanticSignature(
                index_provider="CF Benchmarks",
                index_name="Bitcoin Real-Time Index (BRTI)",
                window_seconds=secondary_window,
                statistic="trimmed_mean",
                trim_top_pct=20,
                trim_bottom_pct=20,
                payoff_relation=payoff_relation,
            ),
            secondary_time,
        )

    if primary_trimmed is not None and modern_secondary_trimmed is not None:
        # A later wording variant keeps the full BRTI/window/clock definition
        # in the primary rule while the secondary rule describes the same
        # final-minute sample as 60 RTI prices and states the 20%/20% trim.
        # The source has appeared with "prices arecollected"; ``are\s*collected``
        # deliberately tolerates only that whitespace defect, not semantic drift.
        primary_window = _window_seconds(primary_trimmed.group("window"))
        if primary_window != 60:
            raise BtcRuleTemplateError(
                f"{series_ticker} modern trimmed secondary proves a 60-second "
                f"window but primary states {primary_window} seconds"
            )
        primary_time = _norm_label(primary_trimmed.group("measurement_time"))
        return (
            RuleSemanticSignature(
                index_provider="CF Benchmarks",
                index_name="Bitcoin Real-Time Index (BRTI)",
                window_seconds=60,
                statistic="trimmed_mean",
                trim_top_pct=20,
                trim_bottom_pct=20,
                payoff_relation=payoff_relation,
            ),
            primary_time,
        )

    simple_primary = _SIMPLE_PRIMARY_MECHANISM_RE.search(primary)
    simple_secondary = _SIMPLE_SECONDARY_RE.search(secondary)
    if simple_primary is not None and simple_secondary is not None:
        if "excluding the top" in primary.lower() or "excluding the top" in secondary.lower():
            raise BtcRuleTemplateError(
                f"{series_ticker} simple-average rule unexpectedly also contains trimming language"
            )
        measurement_time = _norm_label(simple_primary.group("measurement_time"))
        return (
            RuleSemanticSignature(
                index_provider="CF Benchmarks",
                index_name="Bitcoin Real-Time Index (BRTI)",
                window_seconds=60,
                statistic="simple_mean",
                trim_top_pct=0,
                trim_bottom_pct=0,
                payoff_relation=payoff_relation,
            ),
            measurement_time,
        )

    raise BtcRuleTemplateError(
        f"{series_ticker} rule does not match any validated BRTI settlement regime"
    )


def select_temporal_representatives(
    market_rows: Sequence[Mapping[str, str]],
    *,
    series_ticker: str,
) -> list[tuple[str, Mapping[str, str]]]:
    """Select deterministic early/middle/late sampled events for diagnostics."""

    selected_events = select_all_event_representatives(
        market_rows, series_ticker=series_ticker
    )
    if len(selected_events) < 3:
        raise BtcRuleTemplateError(
            f"{series_ticker} needs at least 3 sampled events for temporal validation"
        )
    indices = (0, len(selected_events) // 2, len(selected_events) - 1)
    labels = ("early", "middle", "late")
    return [(label, selected_events[index][1]) for label, index in zip(labels, indices)]


def select_all_event_representatives(
    market_rows: Sequence[Mapping[str, str]],
    *,
    series_ticker: str,
) -> list[tuple[str, Mapping[str, str]]]:
    """Select exactly one deterministic market from every sampled event.

    The inventory already sampled events outcome-blindly. Rule-regime detection
    should therefore inspect every sampled event, not only three temporal points,
    because an intermediate settlement regime could otherwise be missed.
    """

    by_event: dict[str, list[Mapping[str, str]]] = {}
    for row in market_rows:
        if row.get("series_ticker") != series_ticker:
            continue
        event_ticker = _required(row, "event_ticker")
        _parse_utc(_required(row, "close_time"), "close_time")
        by_event.setdefault(event_ticker, []).append(row)

    if not by_event:
        raise BtcRuleTemplateError(f"{series_ticker} has no sampled events")

    events = sorted(
        by_event.items(),
        key=lambda item: (
            min(
                _parse_utc(_required(row, "close_time"), "close_time")
                for row in item[1]
            ),
            item[0],
        ),
    )

    selected: list[tuple[str, Mapping[str, str]]] = []
    for index, (_event_ticker, rows) in enumerate(events, start=1):
        representative = sorted(rows, key=lambda row: _required(row, "ticker"))[0]
        selected.append((f"event_{index:03d}", representative))
    return selected


def extract_market_from_exact_raw_record(
    raw_records: Iterable[Mapping[str, Any]],
    *,
    raw_request_id: str,
    market_ticker: str,
) -> Mapping[str, Any]:
    """Resolve one derived row back to its exact raw request record."""

    matches = [
        record
        for record in raw_records
        if _nested_text(record, "request", "request_id") == raw_request_id
    ]
    if len(matches) != 1:
        raise BtcRuleTemplateError(
            f"expected exactly one raw record for request_id {raw_request_id}; "
            f"found {len(matches)}"
        )

    record = matches[0]
    response = record.get("response")
    if not isinstance(response, Mapping) or response.get("status_code") != 200:
        raise BtcRuleTemplateError(
            f"raw request {raw_request_id} is not a successful HTTP response"
        )
    body_text = response.get("body_text")
    if not isinstance(body_text, str) or not body_text:
        raise BtcRuleTemplateError(f"raw request {raw_request_id} has no response body")
    try:
        payload = json.loads(body_text)
    except json.JSONDecodeError as exc:
        raise BtcRuleTemplateError(
            f"raw request {raw_request_id} body is not valid JSON"
        ) from exc

    markets: list[Mapping[str, Any]] = []
    if isinstance(payload, Mapping):
        if isinstance(payload.get("market"), Mapping):
            markets = [payload["market"]]
        elif isinstance(payload.get("markets"), list):
            markets = [
                item for item in payload["markets"] if isinstance(item, Mapping)
            ]

    market_matches = [item for item in markets if item.get("ticker") == market_ticker]
    if len(market_matches) != 1:
        raise BtcRuleTemplateError(
            f"raw request {raw_request_id} contains {len(market_matches)} matches "
            f"for market {market_ticker}"
        )
    return market_matches[0]


def validate_sample(
    *,
    series_ticker: str,
    sample_position: str,
    derived_row: Mapping[str, str],
    raw_market: Mapping[str, Any],
) -> RuleValidationSample:
    """Validate one raw contract against derived identity and rule semantics."""

    market_ticker = _required(derived_row, "ticker")
    event_ticker = _required(derived_row, "event_ticker")
    if (
        raw_market.get("ticker") != market_ticker
        or raw_market.get("event_ticker") != event_ticker
    ):
        raise BtcRuleTemplateError(f"raw/derived identity mismatch for {market_ticker}")

    rules_primary = raw_market.get("rules_primary")
    rules_secondary = raw_market.get("rules_secondary")
    if not isinstance(rules_primary, str) or not isinstance(rules_secondary, str):
        raise BtcRuleTemplateError(f"raw market {market_ticker} is missing rule text")

    expected_relation = _resolve_payoff_relation(
        series_ticker=series_ticker,
        market_ticker=market_ticker,
        derived_strike_type=derived_row.get("strike_type"),
        raw_strike_type=raw_market.get("strike_type"),
        rules_primary=rules_primary,
    )

    try:
        signature, clock_label, date_label = parse_rule_semantics(
            series_ticker=series_ticker,
            rules_primary=rules_primary,
            rules_secondary=rules_secondary,
            expected_relation=expected_relation,
        )
    except BtcRuleTemplateError as exc:
        close_time = str(derived_row.get("close_time") or "[missing]").strip()
        raise BtcRuleTemplateError(
            f"{exc}\n"
            f"Offending sample: series={series_ticker} | position={sample_position} | "
            f"ticker={market_ticker} | event={event_ticker} | close_time={close_time}\n"
            f"RULES_PRIMARY: {rules_primary}\n"
            f"RULES_SECONDARY: {rules_secondary}"
        ) from exc

    primary_hash = hashlib.sha256(rules_primary.encode("utf-8")).hexdigest()
    secondary_hash = hashlib.sha256(rules_secondary.encode("utf-8")).hexdigest()
    derived_primary_hash = _required(derived_row, "rules_primary_sha256")
    derived_secondary_hash = _required(derived_row, "rules_secondary_sha256")
    if primary_hash != derived_primary_hash or secondary_hash != derived_secondary_hash:
        raise BtcRuleTemplateError(f"rule hash lineage mismatch for {market_ticker}")

    return RuleValidationSample(
        series_ticker=series_ticker,
        sample_position=sample_position,
        event_ticker=event_ticker,
        market_ticker=market_ticker,
        close_time=_required(derived_row, "close_time"),
        raw_source=_required(derived_row, "raw_source"),
        raw_session_id=_required(derived_row, "raw_session_id"),
        raw_request_id=_required(derived_row, "raw_request_id"),
        route_tier=_required(derived_row, "route_tier"),
        primary_sha256=primary_hash,
        secondary_sha256=secondary_hash,
        measurement_clock_label=clock_label,
        settlement_date_label=date_label,
        signature=signature,
    )


def validate_signature_stability(
    samples: Sequence[RuleValidationSample],
) -> RuleSemanticSignature:
    """Require one signature; retained for callers that truly need stationarity."""

    if not samples:
        raise BtcRuleTemplateError("no rule-validation samples supplied")
    series = {sample.series_ticker for sample in samples}
    if len(series) != 1:
        raise BtcRuleTemplateError("signature stability must be checked within one Series")
    signatures = {sample.signature for sample in samples}
    if len(signatures) != 1:
        raise BtcRuleTemplateError(
            f"{next(iter(series))} rule semantics changed across sampled events"
        )
    return next(iter(signatures))


def summarize_rule_regimes(
    samples: Sequence[RuleValidationSample],
) -> list[RuleRegimeSummary]:
    """Group one Series' validated samples into semantic settlement regimes."""

    if not samples:
        raise BtcRuleTemplateError("no rule-validation samples supplied")
    series = {sample.series_ticker for sample in samples}
    if len(series) != 1:
        raise BtcRuleTemplateError("rule regimes must be summarized within one Series")

    grouped: dict[RuleSemanticSignature, list[RuleValidationSample]] = {}
    for sample in samples:
        grouped.setdefault(sample.signature, []).append(sample)

    summaries: list[RuleRegimeSummary] = []
    for signature, items in grouped.items():
        ordered = sorted(items, key=lambda item: (_parse_utc(item.close_time, "close_time"), item.event_ticker))
        summaries.append(
            RuleRegimeSummary(
                regime_id=signature.regime_id,
                signature=signature,
                sample_count=len(ordered),
                earliest_observed_close_time=ordered[0].close_time,
                latest_observed_close_time=ordered[-1].close_time,
                event_tickers=tuple(item.event_ticker for item in ordered),
            )
        )

    return sorted(
        summaries,
        key=lambda item: (
            _parse_utc(item.earliest_observed_close_time, "earliest_observed_close_time"),
            item.regime_id,
        ),
    )


def observed_regime_transitions(
    samples: Sequence[RuleValidationSample],
) -> list[dict[str, str]]:
    """Report sampled chronology points where the observed signature changes.

    These are *sample brackets*, not exact production rule-change timestamps.
    """

    ordered = sorted(
        samples,
        key=lambda item: (_parse_utc(item.close_time, "close_time"), item.event_ticker),
    )
    transitions: list[dict[str, str]] = []
    for previous, current in zip(ordered, ordered[1:]):
        if previous.signature != current.signature:
            transitions.append(
                {
                    "from_regime_id": previous.signature.regime_id,
                    "to_regime_id": current.signature.regime_id,
                    "last_observed_from_close_time": previous.close_time,
                    "first_observed_to_close_time": current.close_time,
                    "last_observed_from_event_ticker": previous.event_ticker,
                    "first_observed_to_event_ticker": current.event_ticker,
                }
            )
    return transitions


def _window_seconds(value: str) -> int:
    normalized = _norm_label(value)
    if normalized == "five minutes":
        return 300
    if normalized in {"sixty seconds", "60 seconds"}:
        return 60
    raise BtcRuleTemplateError(f"unsupported BRTI averaging window: {value!r}")


def _resolve_payoff_relation(
    *,
    series_ticker: str,
    market_ticker: str,
    derived_strike_type: Any,
    raw_strike_type: Any,
    rules_primary: str,
) -> str:
    """Resolve payoff shape from exact rule text, cross-checking metadata.

    Historical Kalshi market objects may omit ``strike_type``. Missing optional
    metadata is therefore not enough to make the settlement rule unresolved when
    the preserved primary rule uniquely proves the payoff relation. When strike
    metadata is present, however, it must agree with the rule text.
    """

    if series_ticker not in _ALLOWED_RELATIONS:
        raise BtcRuleTemplateError(f"unsupported BTC ladder series: {series_ticker}")

    primary = normalize_rule_text(rules_primary)
    rule_relations = [
        relation
        for relation, pattern in _RELATION_RE.items()
        if pattern.search(primary) is not None
    ]
    allowed_rule_relations = [
        relation for relation in rule_relations if relation in _ALLOWED_RELATIONS[series_ticker]
    ]
    if len(allowed_rule_relations) != 1:
        raise BtcRuleTemplateError(
            f"{series_ticker} primary rule does not uniquely prove one supported "
            f"payoff relation for {market_ticker}: {allowed_rule_relations}"
        )
    rule_relation = allowed_rule_relations[0]

    metadata_relations: list[tuple[str, str, str]] = []
    for source_name, value in (
        ("derived", derived_strike_type),
        ("raw", raw_strike_type),
    ):
        if value is None or not str(value).strip():
            continue
        strike_type = str(value).strip()
        relation = _STRIKE_TYPE_RELATION.get(strike_type)
        if relation is None:
            raise BtcRuleTemplateError(
                f"unsupported {source_name} strike_type {strike_type!r} for {market_ticker}"
            )
        if relation not in _ALLOWED_RELATIONS[series_ticker]:
            raise BtcRuleTemplateError(
                f"{source_name} strike_type {strike_type!r} implies unsupported "
                f"payoff relation {relation!r} for {series_ticker}"
            )
        metadata_relations.append((source_name, strike_type, relation))

    for source_name, strike_type, relation in metadata_relations:
        if relation != rule_relation:
            raise BtcRuleTemplateError(
                f"{source_name} strike_type {strike_type!r} disagrees with primary "
                f"rule payoff relation {rule_relation!r} for {market_ticker}"
            )

    return rule_relation


def _required(row: Mapping[str, Any], field: str) -> str:
    value = row.get(field)
    if value is None or not str(value).strip():
        raise BtcRuleTemplateError(f"required field {field!r} is missing")
    return str(value).strip()


def _nested_text(record: Mapping[str, Any], outer: str, inner: str) -> str | None:
    value = record.get(outer)
    if not isinstance(value, Mapping):
        return None
    nested = value.get(inner)
    return nested if isinstance(nested, str) else None


def _norm_label(value: str) -> str:
    return " ".join(value.strip().lower().split())


def _parse_utc(value: str, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise BtcRuleTemplateError(
            f"{field} is not an ISO timestamp: {value!r}"
        ) from exc
    if parsed.tzinfo is None:
        raise BtcRuleTemplateError(f"{field} must be timezone-aware")
    return parsed

@dataclass(frozen=True)
class LadderClusterSemanticSummary:
    series_ticker: str
    event_ticker: str
    source_cluster_id: str
    market_count: int
    close_time: str
    regime_id: str
    settlement_primitive_id: str
    signature: RuleSemanticSignature
    payoff_relations: tuple[str, ...]

    def as_json(self) -> dict[str, Any]:
        return {
            "series_ticker": self.series_ticker,
            "event_ticker": self.event_ticker,
            "source_cluster_id": self.source_cluster_id,
            "market_count": self.market_count,
            "close_time": self.close_time,
            "regime_id": self.regime_id,
            "settlement_primitive_id": self.settlement_primitive_id,
            "measurement_signature": {
                "index_provider": self.signature.index_provider,
                "index_name": self.signature.index_name,
                "window_seconds": self.signature.window_seconds,
                "statistic": self.signature.statistic,
                "trim_top_pct": self.signature.trim_top_pct,
                "trim_bottom_pct": self.signature.trim_bottom_pct,
            },
            "payoff_relations": list(self.payoff_relations),
        }


def measurement_end_utc(
    *,
    measurement_clock_label: str,
    settlement_date_label: str,
) -> str:
    """Convert an explicit EST/EDT rule clock/date into canonical UTC.

    Kalshi rule text in the sampled ladder history explicitly says EST or EDT.
    We therefore use those fixed offsets rather than guessing a timezone from
    the calendar date. Any other timezone label fails closed.
    """

    clock = _norm_label(measurement_clock_label)
    match = re.fullmatch(r"(?P<hour>\d{1,2})(?::(?P<minute>\d{2}))?\s*(?P<ampm>am|pm)\s*(?P<zone>est|edt)", clock)
    if match is None:
        raise BtcRuleTemplateError(
            f"unsupported settlement clock label: {measurement_clock_label!r}"
        )
    hour = int(match.group("hour"))
    minute = int(match.group("minute") or "0")
    if hour < 1 or hour > 12 or minute < 0 or minute > 59:
        raise BtcRuleTemplateError(
            f"invalid settlement clock label: {measurement_clock_label!r}"
        )
    if match.group("ampm") == "am":
        hour24 = 0 if hour == 12 else hour
    else:
        hour24 = 12 if hour == 12 else hour + 12

    try:
        local_date = datetime.strptime(settlement_date_label.strip(), "%b %d, %Y")
    except ValueError as exc:
        raise BtcRuleTemplateError(
            f"unsupported settlement date label: {settlement_date_label!r}"
        ) from exc

    from datetime import timedelta, timezone

    offset_hours = -5 if match.group("zone") == "est" else -4
    local = local_date.replace(
        hour=hour24,
        minute=minute,
        second=0,
        microsecond=0,
        tzinfo=timezone(timedelta(hours=offset_hours)),
    )
    utc = local.astimezone(timezone.utc)
    return utc.isoformat(timespec="seconds").replace("+00:00", "Z")


def settlement_primitive_id(
    *,
    signature: RuleSemanticSignature,
    measurement_end_utc_value: str,
) -> str:
    """Return a deterministic ID for one validated BTC settlement primitive."""

    _parse_utc(measurement_end_utc_value, "measurement_end_utc")
    payload = "|".join(
        [
            signature.index_provider,
            signature.index_name,
            str(signature.window_seconds),
            signature.statistic,
            str(signature.trim_top_pct),
            str(signature.trim_bottom_pct),
            measurement_end_utc_value,
        ]
    )
    return "btcprim_" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:20]


def build_raw_market_index(
    raw_records: Iterable[Mapping[str, Any]],
) -> dict[str, dict[str, Mapping[str, Any]]]:
    """Index successful raw market responses by exact request and market ticker."""

    index: dict[str, dict[str, Mapping[str, Any]]] = {}
    for record in raw_records:
        request_id = _nested_text(record, "request", "request_id")
        if request_id is None:
            continue
        if request_id in index:
            raise BtcRuleTemplateError(
                f"duplicate raw request_id in archive: {request_id}"
            )
        response = record.get("response")
        if not isinstance(response, Mapping) or response.get("status_code") != 200:
            index[request_id] = {}
            continue
        body_text = response.get("body_text")
        if not isinstance(body_text, str) or not body_text:
            index[request_id] = {}
            continue
        try:
            payload = json.loads(body_text)
        except json.JSONDecodeError as exc:
            raise BtcRuleTemplateError(
                f"raw request {request_id} body is not valid JSON"
            ) from exc
        markets: list[Mapping[str, Any]] = []
        if isinstance(payload, Mapping):
            if isinstance(payload.get("market"), Mapping):
                markets = [payload["market"]]
            elif isinstance(payload.get("markets"), list):
                markets = [item for item in payload["markets"] if isinstance(item, Mapping)]
        by_ticker: dict[str, Mapping[str, Any]] = {}
        for market in markets:
            ticker = market.get("ticker")
            if not isinstance(ticker, str) or not ticker:
                continue
            if ticker in by_ticker:
                raise BtcRuleTemplateError(
                    f"raw request {request_id} contains duplicate market {ticker}"
                )
            by_ticker[ticker] = market
        index[request_id] = by_ticker
    return index


def settlement_measurement_key(signature: RuleSemanticSignature) -> tuple[Any, ...]:
    """Return settlement-measurement semantics, deliberately excluding payoff shape."""

    return (
        signature.index_provider,
        signature.index_name,
        signature.window_seconds,
        signature.statistic,
        signature.trim_top_pct,
        signature.trim_bottom_pct,
    )


def measurement_regime_id(signature: RuleSemanticSignature) -> str:
    trim = (
        f"trim{signature.trim_bottom_pct}_{signature.trim_top_pct}"
        if signature.statistic == "trimmed_mean"
        else "untrimmed"
    )
    return f"brti_{signature.window_seconds}s_{signature.statistic}_{trim}"


def validate_all_ladder_cluster_semantics(
    market_rows: Sequence[Mapping[str, str]],
    raw_records: Iterable[Mapping[str, Any]],
    *,
    series_tickers: Sequence[str] = _TARGET_SERIES,
) -> list[LadderClusterSemanticSummary]:
    """Validate every sampled ladder market and resolve event settlement primitives.

    Every derived market in the selected Series is traced to its exact raw
    request, its rule hashes are revalidated, and its rule semantics are parsed.
    All markets inside one Event must share exactly one semantic signature,
    close timestamp, and source candidate cluster ID. The rule-local clock/date
    must also map exactly to the derived UTC close timestamp.
    """

    target = set(series_tickers)
    raw_index = build_raw_market_index(raw_records)
    grouped: dict[tuple[str, str], list[tuple[Mapping[str, str], RuleValidationSample]]] = {}
    seen_tickers: set[str] = set()

    for row in market_rows:
        series = row.get("series_ticker")
        if series not in target:
            continue
        ticker = _required(row, "ticker")
        if ticker in seen_tickers:
            raise BtcRuleTemplateError(f"duplicate derived market ticker: {ticker}")
        seen_tickers.add(ticker)
        request_id = _required(row, "raw_request_id")
        raw_markets = raw_index.get(request_id)
        if raw_markets is None:
            raise BtcRuleTemplateError(
                f"derived market {ticker} references missing raw request {request_id}"
            )
        raw_market = raw_markets.get(ticker)
        if raw_market is None:
            raise BtcRuleTemplateError(
                f"derived market {ticker} is absent from exact raw request {request_id}"
            )
        event = _required(row, "event_ticker")
        sample = validate_sample(
            series_ticker=series,
            sample_position="all_markets",
            derived_row=row,
            raw_market=raw_market,
        )
        rule_end = measurement_end_utc(
            measurement_clock_label=sample.measurement_clock_label,
            settlement_date_label=sample.settlement_date_label,
        )
        derived_close = _parse_utc(_required(row, "close_time"), "close_time")
        if derived_close.isoformat(timespec="seconds").replace("+00:00", "Z") != rule_end:
            raise BtcRuleTemplateError(
                f"rule/derived settlement timestamp mismatch for {ticker}: "
                f"rule={rule_end}, derived={row.get('close_time')}"
            )
        grouped.setdefault((series, event), []).append((row, sample))

    if not grouped:
        raise BtcRuleTemplateError("no sampled BTC ladder markets were found")

    summaries: list[LadderClusterSemanticSummary] = []
    for (series, event), items in sorted(grouped.items()):
        measurement_keys = {settlement_measurement_key(sample.signature) for _, sample in items}
        payoff_relations = {sample.signature.payoff_relation for _, sample in items}
        close_times = {_required(row, "close_time") for row, _ in items}
        source_clusters = {_required(row, "settlement_cluster_id") for row, _ in items}
        if len(measurement_keys) != 1:
            raise BtcRuleTemplateError(
                f"{series} event {event} contains multiple settlement measurement regimes"
            )
        if not payoff_relations.issubset(_ALLOWED_RELATIONS[series]):
            raise BtcRuleTemplateError(
                f"{series} event {event} contains unsupported payoff relations: "
                f"{sorted(payoff_relations)}"
            )
        if len(close_times) != 1:
            raise BtcRuleTemplateError(
                f"{series} event {event} contains multiple close timestamps"
            )
        if len(source_clusters) != 1:
            raise BtcRuleTemplateError(
                f"{series} event {event} contains multiple source candidate clusters"
            )
        signature = items[0][1].signature
        close_time = next(iter(close_times))
        primitive = settlement_primitive_id(
            signature=signature,
            measurement_end_utc_value=(
                _parse_utc(close_time, "close_time")
                .isoformat(timespec="seconds")
                .replace("+00:00", "Z")
            ),
        )
        summaries.append(
            LadderClusterSemanticSummary(
                series_ticker=series,
                event_ticker=event,
                source_cluster_id=next(iter(source_clusters)),
                market_count=len(items),
                close_time=close_time,
                regime_id=measurement_regime_id(signature),
                settlement_primitive_id=primitive,
                signature=signature,
                payoff_relations=tuple(sorted(payoff_relations)),
            )
        )
    return sorted(
        summaries,
        key=lambda item: (_parse_utc(item.close_time, "close_time"), item.series_ticker, item.event_ticker),
    )
