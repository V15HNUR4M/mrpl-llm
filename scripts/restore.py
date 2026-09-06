#!/usr/bin/env python3
"""
MRPL Sovereign Workbench - Production Restore Utility
Restores persistent application state from a verified backup archive into a target
directory or Docker named volume (mrpl_data), strictly validating SHA-256 checksums.
"""

import os
import sys
import tarfile
import hashlib
import json
import argparse
import subprocess
import shutil
from pathlib import Path
from typing import Dict, Any, Optional

def compute_sha256(filepath: Path) -> str:
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()

def restore_backup_archive(archive_path: Path, target_dir: Path, wipe_target_first: bool = False) -> Dict[str, Any]:
    """
    Restores an archive into target_dir and verifies manifest SHA-256 checksums.
    """
    archive_path = Path(archive_path).resolve()
    target_dir = Path(target_dir).resolve()

    if not archive_path.exists():
        raise FileNotFoundError(f"Backup archive not found: {archive_path}")

    target_dir.mkdir(parents=True, exist_ok=True)

    # 1. Read manifest from archive
    manifest: Optional[Dict[str, Any]] = None
    with tarfile.open(archive_path, "r:gz") as tar:
        try:
            m_file = tar.extractfile("manifest.json")
            if m_file:
                manifest = json.loads(m_file.read().decode("utf-8"))
        except KeyError:
            pass

    if not manifest:
        raise ValueError(f"Corrupted or invalid backup: 'manifest.json' missing from {archive_path}")

    # 2. Optionally wipe target tracked directories
    if wipe_target_first:
        for tracked in ["mrpl.db", "chroma", "uploads", "attachments"]:
            p = target_dir / tracked
            if p.is_file():
                p.unlink()
            elif p.is_dir():
                shutil.rmtree(p)

    # 3. Extract members (excluding manifest.json)
    with tarfile.open(archive_path, "r:gz") as tar:
        members = [m for m in tar.getmembers() if m.name != "manifest.json"]
        tar.extractall(path=target_dir, members=members)

    # 4. Strictly verify SHA-256 for each restored file against manifest
    verified_files = 0
    mismatches = []
    for rel_path, meta in manifest.get("files", {}).items():
        extracted_file = target_dir / rel_path
        if not extracted_file.exists():
            mismatches.append(f"Missing file: {rel_path}")
            continue
        actual_sha = compute_sha256(extracted_file)
        expected_sha = meta["sha256"]
        if actual_sha != expected_sha:
            mismatches.append(f"Checksum mismatch on {rel_path}: expected {expected_sha}, got {actual_sha}")
        else:
            verified_files += 1

    if mismatches:
        raise ValueError(f"Restore verification failed with {len(mismatches)} error(s):\n" + "\n".join(mismatches))

    return {
        "status": "success",
        "verified_files": verified_files,
        "manifest": manifest
    }

def restore_docker_volume(archive_path: Path, volume_name: str, wipe_target_first: bool = True) -> Dict[str, Any]:
    """
    Restores a backup archive into a Docker named volume.
    """
    archive_path = Path(archive_path).resolve()
    if not archive_path.exists():
        raise FileNotFoundError(f"Backup archive not found: {archive_path}")

    abs_archive_dir = archive_path.parent.as_posix()
    archive_name = archive_path.name

    cmd = [
        "docker", "run", "--rm",
        "-v", f"{volume_name}:/data",
        "-v", f"{abs_archive_dir}:/backup:ro",
        "python:3.11-slim",
        "python", "-c", f"""
import tarfile, hashlib, json, shutil
from pathlib import Path

target_dir = Path('/data')
archive_p = Path('/backup/{archive_name}')

with tarfile.open(archive_p, 'r:gz') as tar:
    mf = json.loads(tar.extractfile('manifest.json').read().decode('utf-8'))
    if {wipe_target_first}:
        for t in ['mrpl.db', 'chroma', 'uploads', 'attachments']:
            p = target_dir / t
            if p.is_file(): p.unlink()
            elif p.is_dir(): shutil.rmtree(p)
    members = [m for m in tar.getmembers() if m.name != 'manifest.json']
    tar.extractall(path=target_dir, members=members)

# Verify
mismatches = []
for rel, meta in mf.get('files', {{}}).items():
    fp = target_dir / rel
    if not fp.exists():
        mismatches.append('missing: ' + rel)
        continue
    h = hashlib.sha256(fp.read_bytes()).hexdigest()
    if h != meta['sha256']:
        mismatches.append('mismatch: ' + rel)

if mismatches:
    raise SystemExit('Restore verification failed: ' + str(mismatches))
print('RESTORE_VERIFIED')
"""
    ]
    subprocess.run(cmd, capture_output=True, text=True, check=True)
    return {"status": "success", "volume": volume_name}

def main():
    parser = argparse.ArgumentParser(description="MRPL Workbench Data Restore Utility")
    parser.add_argument("--archive", type=str, required=True, help="Path to backup archive (.tar.gz)")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--data-dir", type=str, help="Path to local persistent data directory")
    group.add_argument("--volume", type=str, help="Name of Docker volume (e.g. mrpl_data)")
    parser.add_argument("--wipe-first", action="store_true", help="Wipe target persistent data before restoring")
    args = parser.parse_args()

    archive_path = Path(args.archive)
    if args.volume:
        print(f"Restoring archive '{archive_path}' into Docker volume '{args.volume}'...")
        res = restore_docker_volume(archive_path, args.volume, wipe_target_first=args.wipe_first)
    else:
        print(f"Restoring archive '{archive_path}' into directory '{args.data_dir}'...")
        res = restore_backup_archive(archive_path, Path(args.data_dir), wipe_target_first=args.wipe_first)

    print(f"Restore completed and verified: {res}")

if __name__ == "__main__":
    main()
