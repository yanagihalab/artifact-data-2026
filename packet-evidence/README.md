# Osmosis evidence: contents and provenance

## Download and inspect

Download the assets from the [Osmosis evidence release](https://github.com/yanagihalab/artifact-data-2026/releases/tag/osmosis-evidence-20261015).

After downloading `SHA256SUMS` and both ZIP files, verify their transfer integrity:

```sh
shasum -a 256 -c SHA256SUMS
```

On systems with GNU coreutils, `sha256sum -c SHA256SUMS` is equivalent. Extract the packet archive and, if needed, the saved-block-results archive into the same directory. Both use the `osmosis-evidence/` root. Their distinct publication manifests can coexist.

Each publication manifest records the source ZIP member, published member, byte length, and SHA-256. These checksums verify file transfer and preservation; they do not validate the measurement results.

## Scope

Only **Osmosis (`osmosis-1`)** is included. The retained dataset path is:

```text
osmosis-evidence/skipgo_paper_data/
  skipgo_from_scratch_completion_histograms_1000000_c50000/
    osmosis_osmosis-1_latest_1000000_c50000/
```

Relative paths and commands inside the original files describe their original execution environment. They are historical records, not newly tested reproduction instructions.

### Packet archive

| Retained files | Purpose |
| --- | --- |
| `completion/packet_completions.csv`, `source_packets.csv` | Packet-level source and reported outcome records |
| `completion/same_chain_completions.csv` | Separate same-chain records; these are not additional acknowledged IBC packets |
| `completion/source_packet_errors.csv`, `completion_scan_errors.csv` | Original extraction and follow-up error records |
| `completion/summary.json`, `summary.md` | Existing summaries, preserved without recalculation |
| `scan/combined/txs.jsonl`, `entry_point_actions.csv` | Combined transaction records and extracted action rows |
| `scan/combined/block_status.csv`, `summary.json` | Recorded collection status and combined scan summary |
| `scan/plan.json`, `chunk_results.json` | Collection configuration and recorded chunk results |
| `logs/01_collect.log`, `scan/logs/*.log` | Available collection and chunk logs |
| `target_plan.json`, `target_result.json` | Historical orchestration records, retained for provenance; see the qualification below |
| Five supplied Python scripts and `requirements.txt` | Relevant code snapshots, including plotting helpers referenced by the collection workflow |

The unchanged script snapshots are also in [code-snapshots/](code-snapshots/); [CODE_SNAPSHOT_MANIFEST.json](CODE_SNAPSHOT_MANIFEST.json) identifies their source members and hashes.

### Saved-block-results archive

This contains the supplied Osmosis files at `scan/chunks/*/raw_blocks/block_results/*.json.gz`. The collection plan specifies `raw_save_mode: matching` and `save_raw_blocks: false`. These are saved responses for the configured collection, not a complete archive of all blocks or a demonstrated complete set of ACK/timeout observations.

## Selection policy

The source package was `skipgo_packet_evidence_20261004_114657_329910.zip` (SHA-256 `6eadf03fa73e44610e43f5697cc6c9f5d9f176bce37e47589d430909b82fbf88`). Its date identifies the packaging operation, not the observation date of every record.

Included original file contents are unchanged. Selection and packaging did not execute the supplied scripts, inspect packet outcomes for correctness, or produce new research results.

The following are excluded from this release:

- Terra records: outside the selected Osmosis scope.
- Chunk-local CSV/JSONL outputs and summaries: intermediate outputs; the combined outputs are retained.
- `chunk_results.partial.json`: an intermediate copy; `chunk_results.json` is retained.
- Additional combined derived tables, the alternative `txs.csv` representation, and prose scan summaries: the combined transaction JSONL, action records, block status, and JSON summary are retained.
- The original package-wide manifest and collection notes: they describe the larger source package, including excluded material. New selection-specific manifests and the provenance notes below describe the actual release.

Row-level equivalence between omitted intermediate outputs and retained combined outputs was not checked for this release. Error records are retained to document the observed collection and follow-up failures.

## Provenance and unresolved qualifications

- The source package notes state that the code has not been verified as the version used during the measurements, and that completeness of the raw records is unverified. No execution-time Git revision is established. The dependency file is not a complete historical environment lockfile.
- The existing Osmosis completion summary records **521 completion-scan errors** and **zero source errors**. These are values already present in the supplied summary, not a recount. The corresponding error files are included.
- `target_result.json` records **`collect_failed`**. Combined scan outputs and completion outputs are also present. Their relationship to that orchestration status has not been reconstructed; this release must not be read as evidence that the entire workflow completed successfully.
- The source package notes identify missing `run_skipgo_from_scratch_completion_histograms.py`, `skipgo_entrypoint_blockdata_targets.json`, and logs matching `skipgo_fs_osmosis_1000000_c50000*.log*`. The target plan also references `collect_and_plot_skipgo_completion_histograms.py`, which was not supplied. Other collection and chunk logs are included.
- `acknowledged` is the original source-side event-observation label. It is not an independently decoded application-success label or proof that all downstream route legs completed. `not_found` does not by itself identify pending packets versus missing observations or parsing problems.
- File availability does not resolve packet matching, effective follow-up limits, extreme latency values, or discrepancies between the earlier aggregate exports. Those checks were not performed as part of publishing this release.
