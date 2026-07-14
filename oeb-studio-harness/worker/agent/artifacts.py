import hashlib
import mimetypes
import shutil
from pathlib import Path


def compute_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def copy_to_store(src: Path, store_root: str, job_id: str) -> Path:
    dest_dir = Path(store_root) / job_id
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / src.name
    shutil.copy2(src, dest)
    return dest


def artifact_info(path: Path) -> dict:
    mime, _ = mimetypes.guess_type(str(path))
    return {
        "filename": path.name,
        "size_bytes": path.stat().st_size,
        "mime_type": mime or "application/octet-stream",
        "checksum_sha256": compute_sha256(path),
    }
