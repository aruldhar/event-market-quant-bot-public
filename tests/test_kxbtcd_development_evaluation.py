from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import unittest

from src.kxbtcd_baseline_design import EXPERIMENT_ID, TIME_BANDS, design_fingerprint
from src.kxbtcd_development_evaluation import (
    KxbtcdDevelopmentEvaluationError,
    OUTCOME_FIELDS,
    PreOutcomeFreeze,
    collect_development_outcomes,
    development_request_plan,
    evaluate_development,
    validate_preoutcome_freeze,
)


@dataclass(frozen=True)
class _Raw:
    source: str
    session_id: str
    request_id: str


@dataclass(frozen=True)
class _Response:
    payload: dict
    raw_record: _Raw


class _Client:
    def __init__(self, labels, events):
        self.labels = labels
        self.events = events
        self.paths = []

    def get_json(self, path, *, params=None):
        self.paths.append(path)
        ticker = path.rsplit('/', 1)[-1]
        return _Response(
            payload={
                'market': {
                    'ticker': ticker,
                    'event_ticker': self.events[ticker],
                    'status': 'finalized',
                    'result': self.labels[ticker],
                }
            },
            raw_record=_Raw('kalshi_public_rest', 'session', f'req-{len(self.paths)}'),
        )


def _freeze() -> PreOutcomeFreeze:
    clusters = []
    sections = []
    fingerprint = design_fingerprint()
    roles = ('q25', 'q50', 'q75')
    for i in range(12):
        partition = 'development' if i < 8 else 'holdout'
        cluster_id = f'cluster-{i:02d}'
        event = f'KXBTCD-EVENT-{i:02d}'
        clusters.append(
            {
                'design_fingerprint': fingerprint,
                'source_cluster_id': cluster_id,
                'event_ticker': event,
                'primary_eligible': 'true',
                'partition': partition,
            }
        )
        for band_index, band in enumerate(TIME_BANDS):
            cross_id = f'{cluster_id}-{band}'
            for role_index, role in enumerate(roles):
                ticker = f'{event}-{role}'
                q = ('0.70', '0.80', '0.20')[role_index]
                sections.append(
                    {
                        'design_fingerprint': fingerprint,
                        'event_ticker': event,
                        'source_cluster_id': cluster_id,
                        'partition': partition,
                        'time_band': band,
                        'cross_section_id': cross_id,
                        'selected_end_period_ts': str(1_700_000_000 + i * 10000 + band_index * 60),
                        'selected_normalized_time_remaining': ('0.83', '0.50', '0.16')[band_index],
                        'ticker': ticker,
                        'probe_role': role,
                        'functional_strike': str(50000 + role_index * 1000),
                        'q_raw': q,
                        'quote_route_tier': 'historical',
                    }
                )
    return PreOutcomeFreeze(
        receipt_path=Path('receipt.json'),
        receipt_sha256='a' * 64,
        receipt={'experiment_id': EXPERIMENT_ID},
        clusters_path=Path('clusters.csv'),
        cross_sections_path=Path('sections.csv'),
        clusters=tuple(clusters),
        cross_sections=tuple(sections),
    )


class KxbtcdDevelopmentEvaluationTests(unittest.TestCase):
    def test_freeze_and_plan_are_exactly_development_only(self):
        freeze = _freeze()
        validate_preoutcome_freeze(freeze)
        plan = development_request_plan(freeze)
        self.assertEqual(24, len(plan))
        self.assertTrue(all('EVENT-0' in row['event_ticker'] for row in plan))
        self.assertFalse(any('EVENT-08' in row['event_ticker'] for row in plan))
        self.assertFalse(any('EVENT-09' in row['event_ticker'] for row in plan))
        self.assertFalse(any('EVENT-10' in row['event_ticker'] for row in plan))
        self.assertFalse(any('EVENT-11' in row['event_ticker'] for row in plan))

    def test_collection_requests_no_holdout_ticker(self):
        freeze = _freeze()
        plan = development_request_plan(freeze)
        labels = {}
        events = {}
        for item in plan:
            labels[item['ticker']] = 'yes' if item['probe_role'] in {'q25', 'q50'} else 'no'
            events[item['ticker']] = item['event_ticker']
        client = _Client(labels, events)
        outcomes = collect_development_outcomes(client, freeze=freeze)
        self.assertEqual(24, len(outcomes))
        self.assertEqual(24, len(client.paths))
        self.assertTrue(all(path.startswith('/historical/markets/') for path in client.paths))
        self.assertFalse(any('EVENT-08' in path or 'EVENT-09' in path or 'EVENT-10' in path or 'EVENT-11' in path for path in client.paths))
        self.assertTrue(all(tuple(row.keys()) == OUTCOME_FIELDS for row in outcomes))

    def test_evaluation_scores_72_predictions_and_eight_clusters(self):
        freeze = _freeze()
        plan = development_request_plan(freeze)
        labels = {item['ticker']: ('yes' if item['probe_role'] in {'q25', 'q50'} else 'no') for item in plan}
        events = {item['ticker']: item['event_ticker'] for item in plan}
        outcomes = collect_development_outcomes(_Client(labels, events), freeze=freeze)
        result = evaluate_development(freeze=freeze, outcomes=outcomes)
        self.assertEqual(72, len(result.predictions))
        self.assertEqual(8, len(result.cluster_scores))
        self.assertEqual(3, len(result.band_scores))
        self.assertEqual('false', result.summary['holdout_outcomes_materialized'])
        self.assertGreater(float(result.summary['delta_log_loss']), 0.0)
        self.assertGreater(float(result.summary['raw_monotonicity_violation_rate']), 0.0)

    def test_nonmonotone_finalized_outcomes_fail_closed(self):
        freeze = _freeze()
        plan = development_request_plan(freeze)
        labels = {item['ticker']: 'no' for item in plan}
        events = {item['ticker']: item['event_ticker'] for item in plan}
        # Make the first cluster 0,1,0 by role, which is impossible for nested >K events.
        first_cluster = plan[0]['source_cluster_id']
        for item in plan:
            if item['source_cluster_id'] == first_cluster and item['probe_role'] == 'q50':
                labels[item['ticker']] = 'yes'
        with self.assertRaisesRegex(KxbtcdDevelopmentEvaluationError, 'violate threshold ordering'):
            collect_development_outcomes(_Client(labels, events), freeze=freeze)

    def test_result_outside_yes_no_fails_closed(self):
        freeze = _freeze()
        plan = development_request_plan(freeze)
        labels = {item['ticker']: ('yes' if item['probe_role'] in {'q25', 'q50'} else 'no') for item in plan}
        events = {item['ticker']: item['event_ticker'] for item in plan}
        labels[plan[0]['ticker']] = 'void'
        with self.assertRaisesRegex(KxbtcdDevelopmentEvaluationError, 'unsupported finalized result'):
            collect_development_outcomes(_Client(labels, events), freeze=freeze)

    def test_tampered_fingerprint_fails_before_request_plan(self):
        freeze = _freeze()
        rows = list(freeze.clusters)
        rows[0] = {**rows[0], 'design_fingerprint': 'tampered'}
        bad = PreOutcomeFreeze(**{**freeze.__dict__, 'clusters': tuple(rows)})
        with self.assertRaisesRegex(KxbtcdDevelopmentEvaluationError, 'fingerprint mismatch'):
            validate_preoutcome_freeze(bad)


if __name__ == '__main__':
    unittest.main()
