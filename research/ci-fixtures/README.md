# Research contract test evidence

This archive contains selected research source and output files needed by the repository's research-script unittest suite. It preserves original evidence bytes, including completed-review data and the 500-case LongMemEval Oracle, for hash and provenance checks. It does not include the full research workspace, credentials or dependencies. The associated study outcomes remain distinct from synthetic test attestations generated in temporary directories.

Reconstruct `contract-evidence-new.tar.gz` by concatenating the parts in alphabetical order, then verify `SHA256SUMS` before extracting into a clean checkout. Do not extract over a live project: it includes frozen paths that may have since been edited by reviewers. Original source data are public under their recorded terms; any future re-blinding must use new independently prepared material.

macOS AppleDouble metadata entries were removed from the archive because Linux test discovery treated their `._*.json` names as additional experiment records. All 761 non-metadata files were checked byte-for-byte against the original archive; their contents and study conclusions were not changed.

`frozen-backend-app-v36.tar.gz` is a separate read-only source snapshot for the historical AC2 supplement replay. Its application files were checked against the frozen protocol; the protocol explicitly exempts the unrelated API routes file. The replay runs in an isolated directory with these historical modules, while all remaining tests run against current code.
