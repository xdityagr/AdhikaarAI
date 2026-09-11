"""
Publish the scheme corpus as a GitHub Release asset.

The corpus is 283 MB and it is not source. It is a build artefact: read-only at
runtime, identical for every deployment, and rebuilt only by an ingest that
takes hours. Three ways to get it onto a server, and only one is good:

  in git            283 MB per rebuild, forever, and over GitHub's 100 MB
                    per-file limit anyway
  fetched at boot   free tiers spin down, so every cold start pays the
                    download again — and a webhook times out while it does
  release asset     downloaded once at BUILD time, baked into the image,
                    versioned, and the repository stays clean

Gzipped it is 42 MB, which is comfortably inside the 2 GB an asset allows and
small enough that a Docker build is not dominated by it.

Usage:
    python scripts/publish_corpus.py --tag corpus-2026-09-08
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.paths import CATALOGUE_DB as CORPUS_DB   # noqa: E402

ASSET = "schemes.db.gz"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag", required=True,
                        help="release tag, e.g. corpus-2026-09-08")
    parser.add_argument("--repo", default="",
                        help="owner/name; defaults to the gh default repo")
    args = parser.parse_args()

    if not CORPUS_DB.exists():
        print(f"No corpus at {CORPUS_DB}. Run the ingest first.")
        return 1

    out = CORPUS_DB.parent / ASSET
    raw = CORPUS_DB.stat().st_size

    # A consistent snapshot, taken through SQLite rather than the filesystem.
    # `VACUUM INTO` reads inside a transaction, so this is safe to run while an
    # ingest is still writing — copying the file directly would capture a torn
    # page and ship a corpus that fails to open only once it is deployed.
    snapshot = CORPUS_DB.parent / "schemes.snapshot.db"
    snapshot.unlink(missing_ok=True)
    print(f"Snapshotting {CORPUS_DB} ({raw / 1e6:.0f} MB)…")
    connection = sqlite3.connect(CORPUS_DB)
    try:
        connection.execute("VACUUM INTO ?", (str(snapshot),))
    finally:
        connection.close()

    print(f"Compressing…")
    with snapshot.open("rb") as src, gzip.open(out, "wb", compresslevel=6) as dst:
        shutil.copyfileobj(src, dst, 1024 * 1024)
    snapshot.unlink(missing_ok=True)
    packed = out.stat().st_size
    print(f"  -> {out} ({packed / 1e6:.0f} MB, {packed / raw:.0%} of the original)")

    # Printed so the Dockerfile can pin it. A corpus that silently changed
    # under a deployment would be very hard to notice from the outside.
    print(f"  sha256: {sha256(out)}")

    repo = ["--repo", args.repo] if args.repo else []
    exists = subprocess.run(["gh", "release", "view", args.tag, *repo],
                            capture_output=True).returncode == 0
    if not exists:
        print(f"Creating release {args.tag}…")
        subprocess.run(
            ["gh", "release", "create", args.tag, *repo,
             "--title", f"Scheme corpus {args.tag}",
             "--notes", "myScheme corpus: schemes, translations, facets and "
                        "the eligibility index. Consumed at Docker build time; "
                        "not source."],
            check=True,
        )

    print("Uploading…")
    subprocess.run(["gh", "release", "upload", args.tag, str(out),
                    "--clobber", *repo], check=True)
    print(f"\nDone. In the Dockerfile:\n"
          f"  ARG CORPUS_TAG={args.tag}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
