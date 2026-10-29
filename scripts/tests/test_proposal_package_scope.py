"""Release-package selection must include reproducibility fixtures and exclude private data."""
from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "package_assessment_source", ROOT / "scripts/package_assessment_source.py"
)
assert SPEC and SPEC.loader
PACKAGE_MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PACKAGE_MODULE)


class AssessmentPackageScopeTests(unittest.TestCase):
    def test_includes_required_review_script_and_synthetic_fixtures(self) -> None:
        self.assertTrue(PACKAGE_MODULE.allowed(Path("scripts/phase4_review_form.js")))
        self.assertTrue(PACKAGE_MODULE.allowed(Path(".nvmrc")))
        for path in (
            "datasets/demo/presentation-memory-v1/conversation.json",
            "datasets/smoke/qwen-four-dimension-source-v1.json",
            "datasets/templates/research-source-permission-template.json",
            "datasets/phase3-engineering-v1/freeze.json",
            "datasets/phase4-candidate-v1/source-histories.json",
            "datasets/benchmarks/longmemeval-compatible-v1/local_sample.json",
            "handoff/owner-a/README.md",
            "handoff/owner-b/README.md",
            "handoff/owner-c/step5_metrics.json",
            "handoff/owner-b/engineering_checks/temp_step4_details.py",
            "datasets/demo/presentation-memory-v1/conversation.json",
        ):
            with self.subTest(path=path):
                self.assertTrue(PACKAGE_MODULE.allowed(Path(path)))

    def test_excludes_runtime_data_private_material_and_generated_files(self) -> None:
        for path in (
            ".env",
            "backend/.env.local",
            ".git/config",
            "output/proposal-delivery/report.md",
            "artifacts/local/reviewer.json",
            "experiments/run/results.json",
            "handoff/owner-a-custodian/heldout/source.json",
            "handoff/owner-d/private/reviewer.zip",
            "frontend/public/reports/private-export.html",
            "backend/.engineering-smoke/presentation-demo-v1/report.json",
            "datasets/annotation/owner-a-custodian/labels.json",
            "datasets/benchmarks/official-private/source.json",
            "datasets/studies/ten-cycle-01/study.json",
            "scripts/unreviewed-helper.js",
            "backend/local.sqlite3",
            "handoff/owner-a/reviewer.zip",
            "handoff/owner-c/chart.png",
            "datasets/phase4-candidate-v1/archive.zip",
            "datasets/demo/presentation-memory-v1/report.pdf",
        ):
            with self.subTest(path=path):
                self.assertFalse(PACKAGE_MODULE.allowed(Path(path)))

    def test_generated_package_has_matching_hash_manifest_and_no_symlinks(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "source"
            output = Path(temporary) / "release"
            (root / "scripts").mkdir(parents=True)
            (root / "datasets/phase4-candidate-v1").mkdir(parents=True)
            (root / "handoff/owner-a").mkdir(parents=True)
            (root / "private").mkdir()
            (root / "README.md").write_text("safe source\n")
            (root / ".nvmrc").write_text("22.22.2\n")
            (root / "handoff/owner-a/README.md").write_text("shared synthetic handoff\n")
            (root / "scripts/phase4_review_form.js").write_text("window.review = true;\n")
            (root / "datasets/phase4-candidate-v1/source-histories.json").write_text("[]\n")
            (root / "datasets/phase4-candidate-v1/diagram.png").write_bytes(b"binary")
            (root / "handoff/owner-a/reviewer.zip").write_bytes(b"binary")
            (root / "private/reviewer.csv").write_text("private\n")
            try:
                (root / "scripts/leak.py").symlink_to(root / "README.md")
            except OSError:
                pass

            manifest = PACKAGE_MODULE.package(root, output)
            archive = output / "AI-Memory-Health-Auditor-source.zip"
            with zipfile.ZipFile(archive) as bundle:
                names = set(bundle.namelist())
                embedded = json.loads(bundle.read("ASSESSMENT_SOURCE_MANIFEST.json"))
                self.assertIn("scripts/phase4_review_form.js", names)
                self.assertIn(".nvmrc", names)
                self.assertIn("datasets/phase4-candidate-v1/source-histories.json", names)
                self.assertIn("handoff/owner-a/README.md", names)
                self.assertNotIn("private/reviewer.csv", names)
                self.assertNotIn("datasets/phase4-candidate-v1/diagram.png", names)
                self.assertNotIn("handoff/owner-a/reviewer.zip", names)
                self.assertNotIn("scripts/leak.py", names)
                self.assertEqual(embedded["files"], manifest["files"])
                for name, expected_hash in manifest["files"].items():
                    import hashlib

                    self.assertEqual(hashlib.sha256(bundle.read(name)).hexdigest(), expected_hash)


if __name__ == "__main__":
    unittest.main()
