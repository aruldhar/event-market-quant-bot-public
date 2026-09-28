# Candidate-E Micro-Production Validation Path — Risk Policy Amendment

## Status

This amendment records the user's intended execution path so future project
handoffs do not revert to a mandatory read-only-week-first roadmap.

Parent closeout receipt:

`4163a6330a568b0a5b40b50de31fdf3cc3350ff7`

Policy-path fingerprint:

`57e7e5c88bd296128927362119c0f3705d4be9ce5f0d8a13c1fd652ddd2e2677`

## Current authorization

Unchanged: **read-only**.

No real-money, demo, paper, order, cancellation, portfolio, or execution write is
authorized by this amendment alone.

## Intended first real-money step

The first intended real-money step after the required safety/demo gates is the
**Candidate-E micro-production validation**, project shorthand:

**"$0.01 contract run"**

This term is defined as **one contract per order at a $0.01 purchase limit price
on the selected side**, plus applicable fees, under hard predeclared run-level
caps.

It does **not** mean a fractional quantity of 0.01 contracts.

## Why this amendment exists

The project had accumulated a roadmap that could be read as requiring a separate
168-hour read-only prospective run before any real-money validation. That is not
the intended path.

The intended path is:

read-only hardening -> production-shaped order/risk implementation -> stable demo
of the exact path -> explicitly approved micro-production run -> evidence review
-> only then any scale-up discussion.

The existing 168-hour prospective concept may be retained, but if retained the
intended post-demo cohort is the micro-production validation cohort rather than a
new mandatory read-only precursor.

## Exact caps still unresolved

This amendment intentionally does not invent the user's total dollar cap.

Before Gate 3 can be authorized, a later predeclaration must freeze:

- total run capital/loss cap including fees;
- maximum order attempts;
- maximum fills;
- maximum simultaneous exposure;
- exact duration;
- exact market-selection scope;
- order type/time-in-force;
- exit/cancellation/restart behavior.

Until those are frozen and the user explicitly approves the specific run, the
project remains read-only.

## Non-scaling rule

No successful micro-production result automatically authorizes a larger price,
quantity, duration, or capital allocation. Any increase requires a new gate and
new explicit user approval.

This amendment changes the roadmap, not the current execution authorization.
