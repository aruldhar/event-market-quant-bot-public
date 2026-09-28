"""21N-Y-A4: additive, bounded snapshot consistency repair planning.

Raw snapshots and paid updates are immutable. Plans are not execution timelines.
"""
from __future__ import annotations

from collections import Counter
import itertools

RULES = {
    "schema": "kxbtcd_snapshot_consistency_rules.v1",
    "ordering": {"maximum_group_size": 4, "preserve_order_within_source": True,
                 "mixed_sources_required": True, "outer_anchors_each_side": 2,
                 "strict_outer_anchor_times": True, "one_order_and_one_cut_chain": True},
    "quarantine": {"one_snapshot_only": True, "both_incident_pairs_originally_failed": True,
                   "two_outer_control_pairs_originally_verified": True,
                   "five_strictly_increasing_timestamps": True,
                   "source_labels_are_metadata_not_authority": True,
                   "one_exact_cut_chain_required": True},
    "maximum_context_span_ms": 120000,
    "maximum_pair_rows": 200000,
    "maximum_pair_cuts": 10000,
    "maximum_pair_rows_times_cuts": 2000000,
    "overlap_policy": "reject_all_proposals_with_intersecting_original_contexts",
    "proposal_basis": "original_Y_A3_only_no_iterative_repair",
    "comparison_epsilon": "0", "paid_rounding": False, "negative_clamping": False,
    "raw_snapshot_deletion": False, "strategy_run": False,
    "cache_builder_status": "not_implemented_in_this_checkpoint",
}


class ReplayWorkBound(RuntimeError):
    pass


def require(condition, message):
    if not condition:
        raise ValueError(message)


def exact_chain(order, pair):
    """Shared snapshots must consume the same paid-update prefix on both sides."""
    states = {None: (1, [])}
    records = []
    for i, j in zip(order, order[1:]):
        record = pair(i, j)
        records.append(record)
        following = {}
        for sc, ec in record["exact_cuts"]:
            for prior, (count, path) in states.items():
                if prior is not None and prior != sc:
                    continue
                next_path = ([sc, ec] if prior is None else path + [ec]) if path is not None else None
                if ec in following:
                    following[ec] = (min(2, following[ec][0] + count), None)
                else:
                    following[ec] = (count, next_path)
        states = following
    count = min(2, sum(n for n, _ in states.values()))
    return {"snapshot_order": list(order), "pair_records": records,
            "cut_chain_count_capped_at_two": count,
            "unique_cut_chain": next(iter(states.values()))[1] if count == 1 else None}


def candidate_jobs(snapshots, failed):
    jobs = []
    i = 0
    while i < len(snapshots):
        j = i + 1
        while j < len(snapshots) and snapshots[j]["timestamp"] == snapshots[i]["timestamp"]:
            j += 1
        if j > i + 1 and any(k in failed for k in range(i, j - 1)):
            jobs.append(("ordering", list(range(i, j))))
        i = j
    jobs.extend(("quarantine", [i]) for i in range(1, len(snapshots) - 1)
                if i - 1 in failed and i in failed)
    return jobs


def evaluate(kind, group, snapshots, failed, pair):
    context = list(range(group[0] - 2, group[-1] + 3))
    result = {"kind": kind, "group": group, "context": context, "status": "REJECTED"}

    def reject(reason):
        result["reason"] = reason
        return result

    if context[0] < 0 or context[-1] >= len(snapshots):
        return reject("two_anchors_each_side_unavailable")
    times = [int(snapshots[i]["timestamp"]) for i in context]
    if times[-1] - times[0] > RULES["maximum_context_span_ms"]:
        return reject("context_exceeds_120_seconds")
    if any(not isinstance(snapshots[i].get("source"), str) or not snapshots[i]["source"] for i in context):
        return reject("missing_source_label")
    try:
        if kind == "ordering":
            if len(group) > RULES["ordering"]["maximum_group_size"]:
                return reject("timestamp_group_too_large")
            by_source = {s: [i for i in group if snapshots[i]["source"] == s]
                         for s in {snapshots[i]["source"] for i in group}}
            if len(by_source) < 2:
                return reject("same_source_order_preserved")
            if not times[0] < times[1] < times[2] < times[-2] < times[-1]:
                return reject("outer_anchor_times_not_strict")
            original = exact_chain(context, pair)
            require(original["cut_chain_count_capped_at_two"] == 0, "Originally failed context unexpectedly reconciles")
            matches = []
            for perm in itertools.permutations(group):
                if any([i for i in perm if snapshots[i]["source"] == s] != ids for s, ids in by_source.items()):
                    continue
                proposed = context[:2] + list(perm) + context[-2:]
                chain = original if proposed == context else exact_chain(proposed, pair)
                if chain["cut_chain_count_capped_at_two"]:
                    matches.append(chain)
            if len(matches) != 1 or matches[0]["cut_chain_count_capped_at_two"] != 1:
                return reject("no_unique_order_and_cut_chain")
            chain = matches[0]
        else:
            require(kind == "quarantine" and len(group) == 1, "Invalid repair kind")
            if any(a >= b for a, b in zip(times, times[1:])):
                return reject("five_snapshot_times_not_strict")
            i = group[0]
            if i - 2 in failed or i + 1 in failed:
                return reject("outer_control_pair_unverified")
            original = exact_chain(context, pair)
            require(original["cut_chain_count_capped_at_two"] == 0, "Originally failed context unexpectedly reconciles")
            chain = exact_chain([k for k in context if k != i], pair)
            if chain["cut_chain_count_capped_at_two"] != 1:
                return reject("no_unique_exact_quarantine_chain")
        result.update({"status": "PROPOSED", "chain": chain,
                       "original_failed_pair_indices": [i for i in range(context[0], context[-1]) if i in failed]})
    except ReplayWorkBound as error:
        return reject("resource_bound:" + str(error))
    return result


def plan_repairs(snapshots, failed, pair):
    failed = set(failed)
    proposals = []
    for number, (kind, group) in enumerate(candidate_jobs(snapshots, failed), 1):
        result = evaluate(kind, group, snapshots, failed, pair)
        result["proposal_id"] = number
        proposals.append(result)
    possible = [p for p in proposals if p["status"] == "PROPOSED"]
    for p in possible:
        overlaps = [q["proposal_id"] for q in possible if q is not p and set(p["context"]) & set(q["context"])]
        p["overlapping_proposal_ids"] = overlaps
        p["status"] = "REJECTED" if overlaps else "ACCEPTED"
        if overlaps:
            p["reason"] = "overlapping_original_contexts"
    return proposals


def revised_order(snapshot_count, proposals, kinds):
    order = list(range(snapshot_count))
    for p in proposals:
        if p["status"] != "ACCEPTED" or p["kind"] not in kinds:
            continue
        before = p["context"]
        after = p["chain"]["snapshot_order"]
        start = order.index(before[0])
        require(order[start:start + len(before)] == before, "Repair contexts overlap or have changed")
        order[start:start + len(before)] = after
    return order


def coverage_variant(snapshots, failed_details, proposals, pair, kinds):
    """Reuse pinned unchanged classifications; replay every changed adjacency.

This incremental gate is not a rebuilt execution cache or a full global cut
assignment. Required cut chains are retained for the later cache implementation.
"""
    failed = {p["pair_index"]: p for p in failed_details}
    selected = [p for p in proposals if p["status"] == "ACCEPTED" and p["kind"] in kinds]
    order = revised_order(len(snapshots), proposals, kinds)
    changed = []
    for p in selected:
        verified = exact_chain(p["chain"]["snapshot_order"], pair)
        require(verified["unique_cut_chain"] == p["chain"]["unique_cut_chain"]
                and verified["cut_chain_count_capped_at_two"] == 1, "Combined repair chain changed")
        changed.append({"proposal_id": p["proposal_id"], "kind": p["kind"],
                        "snapshot_order": verified["snapshot_order"], "required_cut_chain": verified["unique_cut_chain"]})
    covered = {i for p in selected for i in p["original_failed_pair_indices"]}
    remaining = []
    verified_ms = excluded_ms = 0
    bounds = []
    segment_start = int(snapshots[order[0]]["timestamp"])
    for n, (a, b) in enumerate(zip(order, order[1:])):
        span = int(snapshots[b]["timestamp"]) - int(snapshots[a]["timestamp"])
        require(span >= 0, "Repaired view moved backward in time")
        if b == a + 1:
            exact = a not in failed
        else:
            r = pair(a, b)
            require(r["exact_cuts"], "Changed adjacency did not reconcile")
            exact = True
        if exact:
            verified_ms += span
        else:
            excluded_ms += span
            require(a not in covered, "Accepted repair left an affected failure unresolved")
            remaining.append({"revised_pair_index": n, "original_start_snapshot_index": a,
                              "original_end_snapshot_index": b, **{k: v for k, v in failed[a].items() if k != "pair_index"}})
            bounds.append([segment_start, int(snapshots[a]["timestamp"])])
            segment_start = int(snapshots[b]["timestamp"])
    bounds.append([segment_start, int(snapshots[order[-1]]["timestamp"])])
    original_span = int(snapshots[-1]["timestamp"]) - int(snapshots[0]["timestamp"])
    require(verified_ms + excluded_ms == original_span, "Coverage duration accounting failed")
    require({r["original_start_snapshot_index"] for r in remaining} == set(failed) - covered,
            "An unresolved original failure was silently removed")
    quarantined = sorted(set(range(len(snapshots))) - set(order))
    return {"snapshot_order_original_indices": order, "quarantined_snapshot_indices": quarantined,
            "required_local_cut_chains": changed, "pair_count": len(order) - 1,
            "remaining_failed_pair_count": len(remaining), "remaining_failed_pairs": remaining,
            "original_failed_pairs_addressed": sorted(covered),
            "verified_ms": verified_ms, "excluded_ms": excluded_ms, "snapshot_span_ms": original_span,
            "verified_time_fraction": verified_ms / original_span if original_span else None,
            "pairwise_verified_bounds": bounds,
            "interpretation": "incremental_source_consistency_coverage_not_an_execution_timeline"}


def repair_coverage(snapshots, coverage, pair):
    failed = coverage["remaining_unreconciled_pairs"]
    proposals = plan_repairs(snapshots, {p["pair_index"] for p in failed}, pair)
    variants = {name: coverage_variant(snapshots, failed, proposals, pair, kinds)
                for name, kinds in (("ordering_only", {"ordering"}),
                                    ("quarantine_only", {"quarantine"}),
                                    ("combined", {"ordering", "quarantine"}))}
    return {"proposals": proposals, "accepted_counts": dict(Counter(p["kind"] for p in proposals if p["status"] == "ACCEPTED")),
            "rejection_counts": dict(Counter(p["reason"] for p in proposals if p["status"] == "REJECTED")),
            "variants": variants, "original_snapshots_modified": False, "cache_built": False,
            "strategy_run": False}
