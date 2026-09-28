# Risk Policy

## Intended execution path — binding roadmap

The current authorization remains **read-only**. This section defines the intended
future path so later checkpoints or handoffs do not silently substitute a
different execution roadmap.

The intended first real-money execution step for Candidate E is a tightly capped
**micro-production validation**, referred to in this project as the **0.01
contract-quantity micro probe**.

For this project, the micro probe means:

- `0.01` contracts per order, only after the exact target market's permitted
  fractional quantity increment has been independently verified;
- a frozen IOC entry price chosen by the frozen V2 policy, rather than a
  one-cent price selected to force a fill;
- applicable fees are included when measuring total capital at risk;
- separately frozen limits on total run capital/loss, maximum order attempts,
  maximum fills, simultaneous exposure, duration, eligible markets, order type,
  cancellation behavior, and restart behavior;
- no automatic increase in price, quantity, duration, or exposure merely to
  force a fill;
- no automatic scale-up after a successful run.

This is an operational and economic validation run, not a general production
launch and not evidence that profitability is guaranteed.

The binding path is:

1. finish read-only runtime/restart/risk hardening;
2. implement the exact production-shaped order and risk state machine;
3. offline-test the same order/risk transitions and archived-ladder evaluator;
4. freeze the exact micro-production run contract and hard dollar limits;
5. obtain direct user approval for that specific real-money run;
6. run the micro-production validation;
7. reconcile actual orders, fills, fees, latency, partial/missed fills, exits,
   cancellations, restarts, kill-switch behavior, and P&L;
8. consider any increase in exposure only under a new predeclared gate and new
   explicit user approval.

A separate 168-hour read-only shadow cohort is **not a mandatory prerequisite**
to the micro-production validation unless the user explicitly reauthorizes that
roadmap. A demo environment run is optional for isolated API mechanics; it is
not a mandatory week-long precursor because its books do not establish
production liquidity or profitability.

Nothing in this section authorizes an order now. Until the later gates are
passed and the user explicitly approves the exact micro-production run, all
current execution prohibitions remain in force.

## Current authorization

Read-only public and authenticated data collection is permitted for the current Bitcoin research scope.

Permitted activity includes:

- Public Kalshi market-data collection
- Authenticated read-only Kalshi collection using the existing locally configured API credentials when required and supported by the account/key
- Read-only BTC perpetual market endpoints for market-data and research purposes
- Authenticated Kalshi WebSocket market-data collection
- Public Coinbase and Kraken Bitcoin reference feeds
- Offline analysis, model development, historical replay, and counterfactual entry/exit signal research that does not submit orders or operate a live paper broker

Credentials must remain environment-managed in an ignored local `.env` or secure secret store. API keys, private keys, signatures, authorization headers, and other secrets must never be logged, committed, written to research artifacts, or pasted into chat.

## Prohibited in the current phase

- Real-money order creation or execution
- Demo order creation or execution
- Paper execution or a paper broker that simulates live order submission/fills
- Order cancellation or automated order management
- Portfolio transfers
- Opening, managing, or closing leveraged or margined positions
- Any other write action against Kalshi trading or portfolio endpoints
- Logging, committing, exporting, or exposing credentials or signing material
- Borrowing or using money needed for expenses
- Martingale or loss-chasing position sizing
- Manipulative behavior, wash trading, spoofing, self-trading, account evasion, or settlement manipulation

Read-only observation of a leveraged product such as the BTC perpetual is permitted. Trading that product is not authorized.

## Research boundary for live-state models

The project may build and evaluate live-state forecasting, valuation, and entry/exit decision logic in read-only mode. During the current phase, outputs such as `ENTER`, `HOLD`, `EXIT`, `LONG`, `SHORT`, `YES`, or `NO` are research signals only. They must not trigger orders, cancellations, transfers, demo execution, paper execution, or real-money execution.

Any historical replay of an entry/exit policy must include realistic fees, bid-ask spreads, available depth, latency, partial fills, missed fills, and model uncertainty. Perpetual-market research must additionally include funding and leverage/liquidation mechanics when evaluating hypothetical economics, even though leveraged execution remains prohibited.

## Phase gates

These gates describe future eligibility for evaluation. Passing a gate does not itself authorize the next execution phase; a separate explicit authorization is still required.

### Gate 1 — Paper strategy eligibility

Required:

- Reliable synchronized data
- Documented settlement/reference source
- Realistic fee and fill model
- Chronological out-of-sample testing
- Calibration or distribution-quality analysis appropriate to the model
- Reproducible experiment report
- Predeclared entry, hold, exit, and no-trade logic for any live-state strategy

### Gate 2 — Demo execution eligibility

Required:

- Gate 1 passed
- Stable order-state machine
- Duplicate-order protection
- Stale-feed and sequence-gap shutdown
- Maximum exposure controls
- Daily loss limit
- Emergency kill switch
- Audit logging
- Separate explicit authorization for demo execution

### Gate 3 — Micro-production validation eligibility

This is the intended first real-money gate for Candidate E. Passing this gate
does not itself authorize an order.

Required:

- Gate 1 passed and the read-only soak plus controlled restart evidence accepted
- Offline state-machine and archived-ladder scenario tests passed
- No material unresolved software or reconciliation failures
- Exact production API endpoint/authentication permissions verified
- `0.01` contract maximum per order, with the exact quantity increment verified
  for the selected production market before authorization
- Frozen V2-selected IOC entry limit; no price increase to force a fill
- Exact fee-aware total-run capital/loss cap frozen before authorization
- Maximum order attempts, fills, simultaneous exposure, and run duration frozen
- Eligible market-selection rule frozen
- Order type, time-in-force, cancellation, exit, and restart rules frozen,
  including a single-exit-writer hybrid: one reduce-only GTC protection order,
  then cancel/reconcile before any reduce-only FOK full-remainder handoff
- Duplicate-order/idempotency protection proven
- Order/fill/cancel/restart reconciliation proven
- Stale feeds, sequence gaps, unhealthy/unknown clock, unclear settlement/risk
  state, or API/reconciliation errors disable all new writes
- Emergency kill switch proven
- Audit logging proven and credential-safe
- Direct user approval for the exact predeclared micro-production run

If the fractional micro probe cannot safely exercise the intended path under the
frozen caps, stop and redesign the validation. Do not silently increase price,
quantity, duration, or exposure to force execution.

### Gate 4 — Any scale-up discussion

Required:

- Gate 3 micro-production validation completed
- All real orders/fills/fees/cancellations/restarts reconciled
- No material unresolved operational or safety failure
- Actual execution costs and latency understood
- Strategy economics evaluated using the real micro-run evidence plus the
  existing historical/prospective evidence
- New predeclared capital, exposure, and loss limits
- New explicit user approval

No successful micro-run automatically authorizes a larger run.

Passing a gate permits further evaluation; it does not guarantee profitability.
