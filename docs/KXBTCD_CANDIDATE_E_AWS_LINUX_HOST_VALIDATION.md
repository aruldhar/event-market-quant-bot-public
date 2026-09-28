# Candidate-E AWS Linux Host Validation

Checkpoint: **21N-Z-E-B5-R5-A**
Date: **2026-09-04**
Classification: **HOST_REBOOT_AND_CLOCK_BOOT_IDENTITY_PASS**

## Purpose

Establish direct production-environment evidence for the Linux cloud host,
Python/runtime compatibility, Linux kernel boot identity, chrony clock health,
and controlled operating-system reboot recovery.

This checkpoint is operational engineering validation only. It does not test
strategy profitability and does not authorize order execution.

## Accepted AWS baseline

- Region: `us-east-1`
- Physical Availability Zone ID: `use1-az4`
- Account-local AZ name: `us-east-1c`
- Instance type: `m7i-flex.large`
- Operating system: Amazon Linux 2023 x86_64
- Root volume: 100 GiB gp3
- Administration: AWS Systems Manager Session Manager
- Security-group inbound rules: none
- EC2 login key pair: none
- Instance metadata: IMDSv2 required
- GitHub repository access: repo-scoped read-only deploy key
- Execution mode: disabled / read-only

The AWS baseline is an operational choice, not a claim that AWS is the globally
lowest-latency cloud or that Kalshi infrastructure is colocated in this region.

## Repository identity

AWS clone:

`bed0796cf0f85d375635f0acb2088b221fccce9b`

`HEAD == origin/main`, with clean Git status.

The corresponding Windows source-of-truth checkout was independently verified
clean and synchronized to the same commit before this documentation update.

## Linux runtime compatibility

Python: `3.11.16`.

Required project imports loaded successfully and `pip check` reported no broken
requirements.

The first complete Linux pytest discovery produced:

- 1,603 passed
- 11 failed
- 4 skipped
- 1,618 regular tests total

Every failure and skip was traced to canonical historical artifacts living under
Git-ignored `data/analysis`, `data/derived`, or `data/manifests` paths. A fresh
production clone intentionally does not contain those archives.

The exact 15 historical-artifact-dependent tests were then deselected and the
source-contained production-host suite produced:

`1603 passed, 15 deselected in 11.69s`

Exit code: `0`.

No Linux-specific source-code failure was observed.

Historical outcome/research archives are not copied onto the production host
merely to satisfy historical integration tests.

## Pre-reboot evidence

UTC observation: approximately `2026-09-04T10:51:44Z`.

Boot ID:

`ca870b4a-9490-4328-8f1a-c55fe2046117`

Clock:
- synchronized: yes;
- NTP service: active;
- selected chrony reference: AWS Time Sync `169.254.169.123`;
- system offset: `0.002688 ms` fast;
- leap status: Normal.

Services:
- `chronyd`: active;
- `amazon-ssm-agent`: active;
- `docker`: active.

## Controlled reboot

The host was rebooted through the Linux operating system using:

`sudo reboot`

This was an OS reboot, not an EC2 stop/start cycle.

## Post-reboot evidence

Post-reboot boot ID:

`0d6faadc-2fae-40bd-aa78-5d86807f8702`

The changed UUID proves the Linux boot identity changed across the real reboot.

Approximately one minute after boot:
- UTC/NTP synchronization: PASS;
- shell-level chrony system offset: `0.032553 ms` fast;
- leap status: Normal;
- `chronyd`: active;
- `amazon-ssm-agent`: active;
- `docker`: active;
- repository commit unchanged;
- Git worktree clean.

## Application-level production adapters

The project code was then invoked directly against the real Linux host.

`resolve_boot_identity(validation_mode=False)` returned:
- status: `PASS`;
- boot ID:
  `0d6faadc-2fae-40bd-aa78-5d86807f8702`;
- source: `linux_kernel_boot_id`;
- validation-only: false;
- reason: `PASS`.

`read_production_chrony_tracking()` returned:
- status: `PASS`;
- signed offset: `+0.002674 ms`;
- absolute offset: `0.002674 ms`;
- leap status: `Normal`;
- reason: `PASS`.

Frozen maximum absolute clock offset for new-signal eligibility:

`250 ms`.

The observed production-adapter offset was therefore far inside the frozen
clock-health boundary.

## Facts established

- The intended AWS host boots as Linux and exposes a valid kernel boot ID.
- A real OS reboot changes that boot ID.
- Chrony is active and synchronized on the host.
- Required host services recover automatically after reboot.
- The project's production boot adapter reads the real Linux kernel identity.
- The project's production chrony adapter reads real chrony state and passes the
  frozen 250 ms gate.
- The source-contained Python codebase passes its portable Linux regression set.

## Not established

This checkpoint does not establish:
- long-duration runtime stability;
- multi-hour source continuity;
- source latency/jitter adequacy;
- storage growth rate or final minimum-free-disk threshold;
- production dashboard behavior;
- order idempotency;
- fill/cancel/position/cash reconciliation;
- exposure/loss caps;
- emergency kill switch;
- partial/missed-fill handling;
- stable demo qualification;
- production profitability.

## Safety state

Current authorization remains **read-only**.

During this host-validation sequence:
- prospective cohort armed: no;
- Candidate-E signals generated: 0;
- orders: 0;
- production writes: 0.

## Next checkpoint

Freeze a bounded long-duration read-only AWS soak design. The soak should measure
runtime/source stability, source latency/jitter, clock health, reconnect behavior,
resource usage, and storage growth while keeping execution disabled.
