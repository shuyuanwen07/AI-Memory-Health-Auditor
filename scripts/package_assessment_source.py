"""Build a local assessed-source archive without live secrets or development data."""
from __future__ import annotations

import argparse
import hashlib
import json
import stat
import subprocess
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROOT_FILES = {'README.md', '.env.example', '.gitignore', 'docker-compose.yml',
              'docker-compose.ci.yml', 'pyproject.toml', 'LICENSE'}
SOURCE_DIRS = {'backend', 'frontend', 'scripts', 'docs', '.github', 'reference_target', 'mem0_target'}
BLOCKED_PARTS = {'.git', '.env', 'node_modules', 'dist', '__pycache__', '.pytest_cache',
                 '.ruff_cache', '.venv', 'output', 'private', 'experiments', 'artifacts'}
SYNTHETIC_DATA_DIRS = {'annotation', 'benchmarks', 'paper-artifacts', 'assessment-candidates-v1'}
STUDY_FIXTURES = {'independent-repair-v1', 'qwen-repair-v4', 'repair-pilot-v1'}


def allowed(relative: Path) -> bool:
    parts = relative.parts
    if not parts or any(part in BLOCKED_PARTS for part in parts):
        return False
    if any(part.startswith('.env') and part != '.env.example' for part in parts):
        return False
    if relative.is_absolute() or '..' in parts:
        return False
    if relative.suffix.lower() in {'.pyc', '.sqlite', '.sqlite3', '.db', '.log', '.tsbuildinfo'}:
        return False
    if parts[0] in ROOT_FILES and len(parts) == 1:
        return True
    if parts[0] == 'datasets':
        if len(parts) < 3:
            return False
        if parts[1] == 'annotation' and parts[2] not in {'v1', 'pilot-v1'}:
            return False
        return parts[1] in SYNTHETIC_DATA_DIRS or (parts[1] == 'studies' and parts[2] in STUDY_FIXTURES)
    if parts[0] not in SOURCE_DIRS:
        return False
    if parts[:3] == ('frontend', 'public', 'reports'):
        return False
    # Only code/config/docs extensions; never package arbitrary binary exports.
    return relative.suffix.lower() in {'.py', '.tsx', '.ts', '.css', '.html', '.json', '.md', '.txt',
                                      '.toml', '.ini', '.yml', '.yaml', '.sh', '.svg'} or relative.name in {'Dockerfile', '.dockerignore'}


def package(root: Path, destination: Path) -> dict:
    selected = [path for path in root.rglob('*') if path.is_file() and not path.is_symlink()
                and allowed(path.relative_to(root))]
    selected.sort(key=lambda path: path.relative_to(root).as_posix())
    if not selected:
        raise ValueError('No source files selected.')
    contents = {path.relative_to(root).as_posix(): path.read_bytes() for path in selected}
    files = {name: hashlib.sha256(content).hexdigest() for name, content in contents.items()}
    base_revision = None
    working_tree_status = 'unknown'
    try:
        revision = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=root, capture_output=True, text=True, check=False)
        status = subprocess.run(['git', 'status', '--porcelain'], cwd=root, capture_output=True, text=True, check=False)
        if revision.returncode == 0:
            base_revision = revision.stdout.strip() or None
        if status.returncode == 0:
            working_tree_status = 'modified' if status.stdout.strip() else 'clean'
    except FileNotFoundError:
        # Source distributions and minimal containers may not include Git.
        # Content hashes still identify the snapshot; do not claim a clean tree.
        pass
    manifest = {'format': 'assessed-source-v1', 'base_revision': base_revision,
                'working_tree_status': working_tree_status,
                'file_count': len(files), 'files': files,
                'notice': 'Local source snapshot, not a final report or proof of independent validation. File hashes identify included contents; an older CI run does not certify this snapshot.',
                'excluded': ['credentials and environment', 'databases', 'Git history', 'participant/private data',
                             'development outputs and public pilot reports', 'dependency/build caches', 'unreviewed arbitrary binary files']}
    # File selection is complete before writing; output cannot recursively include itself.
    destination.mkdir(parents=True, exist_ok=True)
    archive = destination / 'AI-Memory-Health-Auditor-source.zip'
    with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED) as bundle:
        for path in selected:
            info = zipfile.ZipInfo(path.relative_to(root).as_posix())
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = (stat.S_IMODE(path.stat().st_mode) | stat.S_IFREG) << 16
            bundle.writestr(info, contents[path.relative_to(root).as_posix()])
        bundle.writestr('ASSESSMENT_SOURCE_MANIFEST.json', json.dumps(manifest, indent=2))
    manifest['archive_sha256'] = hashlib.sha256(archive.read_bytes()).hexdigest()
    (destination / 'source-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'output/assessment-release-v1')
    args = parser.parse_args()
    result = package(ROOT, args.output)
    print(json.dumps({'files': result['file_count'], 'archive_sha256': result['archive_sha256'],
                      'working_tree_status': result['working_tree_status']}))
