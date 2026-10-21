"""Privacy-preserving source provenance helpers."""

from functools import lru_cache
import hashlib
from pathlib import Path
from urllib.parse import urlparse


@lru_cache(maxsize=128)
def _file_sha256(path_text):
    digest = hashlib.sha256()
    with Path(path_text).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def source_reference(source, include_content_hash=True):
    """Return provenance without exposing an absolute path or file name."""

    source_text = str(source)
    path = Path(source_text).expanduser()
    if path.is_file():
        result = {"kind": "file"}
        if include_content_hash:
            result["sha256"] = _file_sha256(str(path.resolve()))
        return result
    parsed = urlparse(source_text)
    kind = parsed.scheme or "opaque"
    return {
        "kind": kind,
        "reference_sha256": hashlib.sha256(source_text.encode("utf-8")).hexdigest(),
    }
