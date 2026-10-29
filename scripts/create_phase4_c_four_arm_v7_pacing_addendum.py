"""Create a private, immutable snapshot of post-run UTC pacing evidence."""
from __future__ import annotations

import argparse
import json
import os
import stat
from pathlib import Path
from typing import Any

from phase4_c_four_arm_v7_pacing_addendum import (
    PacingAddendumError,
    build_addendum,
    sha256_file,
)
from run_phase4_c_four_arm_v7 import _read_json, validate_frozen_inputs


def _is_within(path: Path, directory: Path) -> bool:
    try:
        path.resolve().relative_to(directory.resolve())
        return True
    except ValueError:
        return False


def _write_private_exclusive(path: Path, value: dict[str, Any]) -> None:
    if path.exists() or path.is_symlink():
        raise FileExistsError(f"Refuse to overwrite existing addendum: {path}")
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.parent.is_symlink():
        raise PacingAddendumError("Addendum output directory must not be a symlink.")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(path, flags, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            os.fchmod(stream.fileno(), stat.S_IRUSR | stat.S_IWUSR)
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        path.unlink(missing_ok=True)
        raise


def create(root: Path, directory: Path, output: Path) -> dict[str, Any]:
    inputs = validate_frozen_inputs(root, directory)
    directory = inputs["directory"]
    output = output if output.is_absolute() else inputs["root"] / output
    if _is_within(output, directory):
        raise PacingAddendumError("Keep the post-run addendum outside the frozen run directory.")
    run_path = directory / "C-live.json"
    protocol_path = directory / "protocol.json"
    subset_path = directory / "longmemeval-subset.json"
    before = {"run": sha256_file(run_path), "protocol": sha256_file(protocol_path),
              "subset": sha256_file(subset_path)}
    run = _read_json(run_path)
    if run.get("status") == "running":
        raise PacingAddendumError("The v7 journal still says running; wait until collection has stopped.")
    addendum = build_addendum(run, inputs["protocol"], before,
                              tool_sha256=sha256_file(Path(__file__)))
    _write_private_exclusive(output, addendum)
    after = {"run": sha256_file(run_path), "protocol": sha256_file(protocol_path),
             "subset": sha256_file(subset_path)}
    if before != after:
        output.unlink(missing_ok=True)
        raise PacingAddendumError("A frozen source changed during addendum creation; the partial addendum was removed.")
    return {"output": str(output), "sha256": sha256_file(output),
            "status": addendum["status"], "cause_assessment": addendum["cause_assessment"],
            "dispatch_count": addendum["observations"]["dispatch_count"],
            "violations": len(addendum["observations"]["violations"]),
            "winner_recommendation_allowed": False}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--directory", type=Path, required=True,
                        help="Frozen v7 run directory containing C-live.json, protocol.json and subset.")
    parser.add_argument("--output", type=Path, required=True,
                        help="New private addendum path outside the frozen run directory.")
    args = parser.parse_args()
    print(json.dumps(create(args.root, args.directory, args.output), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
