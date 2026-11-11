#!/usr/bin/env python3
"""Create a disposable pinned application copy outside immutable source/."""
import io
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tarfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    subprocess.run([sys.executable, str(ROOT / 'scripts/verify_baseline.py')], check=True)
    pins = json.loads((ROOT / 'REVIEW_SCOPE.json').read_text())['pinned_commits']
    destination = ROOT / 'scratch/runtime/app'
    manifest = destination.parent / 'baseline.json'
    reused = destination.exists()
    if reused:
        if not manifest.exists() or json.loads(manifest.read_text()) != pins:
            raise SystemExit('Existing runtime has a different baseline; preserve it and inspect manually')
        if (destination.parent / 'file-hashes.json').exists():
            print('Existing runtime preserved:', destination)
            return
    destination.mkdir(parents=True, exist_ok=True)
    for relative, commit in pins.items():
        archive = subprocess.check_output(['git', '-C', str(ROOT / relative), 'archive', commit])
        target = destination / Path(relative).relative_to('source')
        target.mkdir(parents=True, exist_ok=True)
        with tarfile.open(fileobj=io.BytesIO(archive)) as stream:
            if reused:
                for member in stream.getmembers():
                    if member.isfile():
                        path = target / member.name
                        expected = hashlib.sha256(stream.extractfile(member).read()).hexdigest()
                        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
                            raise SystemExit(f'Runtime differs from pinned archive: {member.name}')
            else:
                stream.extractall(target, filter='data')
    hashes = {str(p.relative_to(destination)): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in destination.rglob('*') if p.is_file()}
    (destination.parent / 'file-hashes.json').write_text(json.dumps(hashes, indent=2) + '\n')
    manifest.write_text(json.dumps(pins, indent=2) + '\n')
    print('Pinned disposable runtime:', destination)


if __name__ == '__main__':
    main()
