# Skip Go / Osmosis measurement artifacts

Artifacts accompanying **Measurement of Skip Go Entry Point Execution and IBC Acknowledgement Latency on Osmosis**.

## Osmosis packet evidence

The [Osmosis evidence release](https://github.com/yanagihalab/artifact-data-2026/releases/tag/osmosis-evidence-20261015) provides a selected subset of the supplied evidence package:

- **`osmosis-packet-evidence.zip`**: packet and transaction records, action records, relevant code snapshots, collection settings, existing summaries, and diagnostic logs.
- **`osmosis-saved-block-results.zip`**: the saved Osmosis `block_results` responses supplied with the dataset. This is a separate optional download because of its size; the packet archive alone does not contain these responses.
- **`SHA256SUMS`**: checksums for both downloads.

See [the contents, selection policy, and provenance notes](packet-evidence/README.md). The [provided code snapshots](packet-evidence/code-snapshots/) are also available for browsing.

This release is an evidence publication, not a new experiment or independent validation. No measurement statistics were recalculated for it. The supplied code has not been verified as the exact version used for the original run, and completeness of the saved raw records has not been established.

## Earlier figures and aggregate tables

The existing files at the repository root, `dataset_histograms/`, and `route_histograms/` are the earlier figures and aggregate exports. They are retained unchanged. The evidence release does not certify packet matching, reconcile previously identified aggregate differences, or replace those historical outputs with new results.
