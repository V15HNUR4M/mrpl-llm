#!/usr/bin/env python3
"""
MRPL Sovereign Workbench - Production Backup Utility
Backs up persistent application state (SQLite, Chroma vector store, uploads, attachments)
with cryptographic SHA-256 manifest verification. Supports both direct filesystem directory
and Docker named volumes (mrpl_data).
"""

import os
import sys
import tarfile
import hashlib
import json
import argparse
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional

def compute_sha256(filepath: Path) -> str:
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()

def create_backup_archive(data_dir: Path, output_archive: Path, volume_name: Optional[str] = None) -> Dict[str, Any]:
    """
    Creates a tar.gz backup archive of data_dir with manifest.json.
    Backs up: mrpl.db, chroma/, uploads/, attachments/.
    """
    data_dir = Path(data_dir).resolve()
    output_archive = Path(output_archive).resolve()
    output_archive.parent.mkdir(parents=True, exist_ok=True)

    if not data_dir.exists():
        raise FileNotFoundError(f"Source data directory does not exist: {data_dir}")

    manifest: Dict[str, Any] = {
        "version": "1.0",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "volume_name": volume_name or "local_data",
        "files": {},
        "summary": {}
    }

    tracked_targets = ["mrpl.db", "chroma", "uploads", "attachments"]
    total_files = 0
    total_bytes = 0

    # Build manifest
    for target in tracked_targets:
        target_path = data_dir / target
        if not target_path.exists():
            continue

        if target_path.is_file():
            rel_path = target
            sha = compute_sha256(target_path)
            size = target_path.stat().st_size
            manifest["files"][rel_path] = {"sha256": sha, "size": size}
            total_files += 1
            total_bytes += size
        elif target_path.is_dir():
            for root, _, files in os.walk(target_path):
                for fname in files:
                    full_p = Path(root) / fname
                    rel_p = full_p.relative_to(data_dir).as_posix()
                    sha = compute_sha256(full_p)
                    size = full_p.stat().st_size
                    manifest["files"][rel_p] = {"sha256": sha, "size": size}
                    total_files += 1
                    total_bytes += size

    manifest["summary"] = {
        "total_files": total_files,
        "total_bytes": total_bytes
    }

    # Write manifest temporarily into data_dir or temp file
    manifest_path = data_dir / ".backup_manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    try:
        with tarfile.open(output_archive, "w:gz") as tar:
            # Add manifest first
            tar.add(manifest_path, arcname="manifest.json")
            for target in tracked_targets:
                target_p = data_dir / target
                if target_p.exists():
                    tar.add(target_p, arcname=target)
    finally:
        if manifest_path.exists():
            manifest_path.unlink()

    return manifest

def backup_docker_volume(volume_name: str, output_archive: Path) -> Dict[str, Any]:
    """
    Backs up a Docker named volume by mounting it into a temporary container.
    """
    output_archive = Path(output_archive).resolve()
    output_archive.parent.mkdir(parents=True, exist_ok=True)
    abs_out_dir = output_archive.parent.as_posix()
    archive_name = output_archive.name

    # Check if python script can run inside container to preserve exact manifest logic
    cmd = [
        "docker", "run", "--rm",
        "-v", f"{volume_name}:/data:ro",
        "-v", f"{abs_out_dir}:/backup",
        "python:3.11-slim",
        "python", "-c", f"""
import os, sys, tarfile, hashlib, json
from datetime import datetime, timezone
from pathlib import Path

data_dir = Path('/data')
tracked = ['mrpl.db', 'chroma', 'uploads', 'attachments']
manifest = {{
    'version': '1.0',
    'created_at': datetime.now(timezone.utc).isoformat(),
    'volume_name': '{volume_name}',
    'files': {{}}
}}
for target in tracked:
    p = data_dir / target
    if not p.exists(): continue
    if p.is_file():
        h = hashlib.sha256(p.read_bytes()).hexdigest()
        manifest['files'][target] = {{'sha256': h, 'size': p.stat().st_size}}
    else:
        for r, _, fs in os.walk(p):
            for f in fs:
                fp = Path(r)/f
                rel = fp.relative_to(data_dir).as_posix()
                h = hashlib.sha256(fp.read_bytes()).hexdigest()
                manifest['files'][rel] = {{'sha256': h, 'size': fp.stat().st_size}}

mf = data_dir / '.manifest.tmp'
Path('/backup/manifest.json').write_text(json.dumps(manifest, indent=2))
with tarfile.open('/backup/{archive_name}', 'w:gz') as tar:
    tar.add('/backup/manifest.json', arcname='manifest.json')
    for target in tracked:
        tp = data_dir / target
        if tp.exists(): tar.add(tp, arcname=target)
os.remove('/backup/manifest.json')
print('BACKUP_COMPLETE')
"""
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    # Read manifest from created tarball
    with tarfile.open(output_archive, "r:gz") as tar:
        m_file = tar.extractfile("manifest.json")
        if m_file:
            return json.loads(m_file.read().decode("utf-8"))
    return {}

def main():
    parser = argparse.ArgumentParser(description="MRPL Workbench Data Backup Utility")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--data-dir", type=str, help="Path to local persistent data directory")
    group.add_argument("--volume", type=str, help="Name of Docker volume (e.g. mrpl_data)")
    parser.add_argument("--output-dir", type=str, default="./backups", help="Directory to store backup archive")
    parser.add_argument("--archive-name", type=str, default=None, help="Custom filename for archive")
    args = parser.parse_args()

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    archive_name = args.archive_name or f"mrpl_backup_{ts}.tar.gz"
    out_path = Path(args.output_dir) / archive_name

    if args.volume:
        print(f"Backing up Docker volume '{args.volume}' to '{out_path}'...")
        manifest = backup_docker_volume(args.volume, out_path)
    else:
        print(f"Backing up local directory '{args.data_dir}' to '{out_path}'...")
        manifest = create_backup_archive(Path(args.data_dir), out_path)

    print(f"Backup successfully created: {out_path}")
    print(f"Backed up {len(manifest.get('files', {}))} files.")

if __name__ == "__main__":
    main()
