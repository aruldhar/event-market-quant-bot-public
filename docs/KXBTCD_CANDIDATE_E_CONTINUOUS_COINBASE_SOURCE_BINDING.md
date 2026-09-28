# KXBTCD Candidate-E Continuous Coinbase Source Recovery and Binding

## Checkpoint 21N-U-B

The continuous Coinbase source materialization itself succeeded, but the collection
run's manifest finalization failed afterward on Windows with `[WinError 5] Access is denied`
during the manifest temp-file `os.replace`.

The failed run remains permanently and honestly classified as **failed**:

`collect_kxbtcd_candidate_e_continuous_btc_materialization_20260902T053628200857Z_f7b9153a`

The failure did **not** occur in Coinbase collection or source validation. The runtime
stream recorded four successful Coinbase HTTP responses, then a `collector.completed`
event with:

- 216 rows,
- 4 events,
- SHA-256 `ecc83bc5a95c65d05063e06df6d5c9aab04895577c3ef5d8ad1cc99ab62f7d1d`,
- Candidate E not scored,
- continuous Predexon strategy not run,
- outcomes not accessed,
- orders 0.

The derived artifact independently reloads under the frozen source contract as 216
valid rows across four events.

## Recovery decision

Do not repeat the public Coinbase requests merely to obtain a cosmetically completed
manifest.

Instead:

1. preserve the original failed manifest unchanged;
2. reuse only the already-written derived Coinbase artifact;
3. require its exact SHA-256 `ecc83bc5a95c65d05063e06df6d5c9aab04895577c3ef5d8ad1cc99ab62f7d1d`;
4. re-run the deterministic 216-row source validator offline;
5. bind that source artifact to the already-frozen continuous implementation
   `cf93bbdd7704ae46954feba8ce73e15a734f117a1791837d87a130e50a15764f`;
6. record that this recovery itself performs zero Coinbase requests.

This is an infrastructure recovery. It does not change Candidate E, the continuous
strategy, the Predexon replay, thresholds, latency, liquidation, re-entry, or any
economic rule.

## Next

After this binding closes, the next checkpoint may run the **outcome-blind continuous
July 10 Predexon path**.

Settlement outcomes remain closed.
