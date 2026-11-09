"""Automated SHA-256 Checksum Verifier for Sentinel Plant Network Research Package.

Verifies:
1. All files in supplementary_materials/ against supplementary_materials/CHECKSUMS_SHA256.txt.
2. Raw public dataset files against results/real_data_validation/DATASETS_MANIFEST.json (if present).

Usage:
    python scripts/verify_checksums.py [--update]
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path


def compute_sha256(filepath: Path) -> str:
    """Compute SHA-256 hexadecimal digest of a file in 1MB chunks."""
    digest = hashlib.sha256()
    with filepath.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_supplementary_materials(supp_dir: Path) -> int:
    """Verify all files listed in CHECKSUMS_SHA256.txt."""
    checksum_file = supp_dir / "CHECKSUMS_SHA256.txt"
    if not checksum_file.exists():
        print(f"[FAIL] Missing checksum file: {checksum_file}")
        return 1

    lines = [
        line.strip() for line in checksum_file.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]

    print(f"Verifying {len(lines)} files in {supp_dir}/ against {checksum_file.name}...")
    errors = 0
    for line in lines:
        parts = line.split(maxsplit=1)
        if len(parts) != 2:
            continue
        expected_hash, rel_path_str = parts[0].strip(), parts[1].strip()
        target_path = supp_dir / rel_path_str
        if not target_path.exists():
            print(f"  [MISSING] {target_path}")
            errors += 1
            continue
        actual_hash = compute_sha256(target_path)
        if actual_hash.lower() != expected_hash.lower():
            print(f"  [MISMATCH] {target_path}")
            print(f"    Expected: {expected_hash}")
            print(f"    Actual:   {actual_hash}")
            errors += 1
        else:
            print(f"  [OK] {rel_path_str}")

    if errors == 0:
        print(f"[PASS] All {len(lines)} supplementary files verified successfully.\n")
    else:
        print(f"[FAIL] {errors} verification error(s) detected in {supp_dir}/.\n")
    return errors


def verify_datasets_manifest(manifest_path: Path) -> int:
    """Verify raw dataset input files recorded in DATASETS_MANIFEST.json if present on disk."""
    if not manifest_path.exists():
        print(f"[INFO] No manifest at {manifest_path}; skipping raw dataset check.")
        return 0

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    datasets = manifest.get("datasets", {})
    print(f"Verifying raw dataset inputs recorded in {manifest_path}...")
    checked = 0
    errors = 0
    missing = 0

    for ds_name, ds_info in datasets.items():
        inputs = ds_info.get("input_files", [])
        for item in inputs:
            p = Path(item["path"])
            expected = item.get("sha256")
            if not p.exists():
                missing += 1
                continue
            actual = compute_sha256(p)
            checked += 1
            if expected and actual.lower() != expected.lower():
                print(f"  [MISMATCH] {p}")
                print(f"    Expected: {expected}")
                print(f"    Actual:   {actual}")
                errors += 1
            else:
                print(f"  [OK] {p.name} ({actual[:12]}...)")

    print(f"[INFO] Verified {checked} available local dataset files ({missing} absent from repo by design).")
    if errors > 0:
        print(f"[FAIL] {errors} raw dataset hash mismatch(es) found.\n")
    else:
        print("[PASS] All present raw dataset files match manifest checksums.\n")
    return errors


def regenerate_checksums_txt(supp_dir: Path):
    """Regenerate CHECKSUMS_SHA256.txt with verified current hashes for all files in supplementary_materials."""
    files = []
    for p in sorted(supp_dir.rglob("*")):
        if p.is_file() and p.name != "CHECKSUMS_SHA256.txt":
            rel = p.relative_to(supp_dir).as_posix()
            h = compute_sha256(p)
            files.append(f"{h}  {rel}")

    checksum_file = supp_dir / "CHECKSUMS_SHA256.txt"
    content = "\n".join(files) + "\n"
    checksum_file.write_text(content, encoding="utf-8")
    print(f"Regenerated {checksum_file} with {len(files)} files.")


def main():
    parser = argparse.ArgumentParser(description="Verify Sentinel Plant Network SHA-256 checksums.")
    parser.add_argument("--supp-dir", type=Path, default=Path("supplementary_materials"), help="Supplementary materials directory")
    parser.add_argument("--manifest", type=Path, default=Path("results/real_data_validation/DATASETS_MANIFEST.json"), help="Path to DATASETS_MANIFEST.json")
    parser.add_argument("--regenerate", action="store_true", help="Regenerate CHECKSUMS_SHA256.txt from current files")
    args = parser.parse_args()

    if args.regenerate:
        regenerate_checksums_txt(args.supp_dir)

    err1 = verify_supplementary_materials(args.supp_dir)
    err2 = verify_datasets_manifest(args.manifest)

    total_errors = err1 + err2
    if total_errors > 0:
        sys.exit(1)
    print("All checksums verified cleanly.")
    sys.exit(0)


if __name__ == "__main__":
    main()
