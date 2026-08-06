import re
import unicodedata
import hashlib
from datetime import datetime


def normalize_name(name: str) -> str:
    """Uppercase, strip accents, collapse whitespace, remove punctuation."""
    if not name:
        return ""
    # Unicode normalize then encode to ASCII ignoring errors (strips accents)
    name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    name = name.upper()
    name = re.sub(r"[^\w\s]", " ", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name


def safe_text(el, tag: str, default: str = "") -> str:
    child = el.find(tag)
    return (child.text or "").strip() if child is not None else default


HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; ComplayeCIS/1.0; +https://complayeconsulting.com)",
    "Accept": "*/*",
}


def compute_content_hash(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def check_and_update_hash(db, source: str, content: bytes) -> bool:
    """Return True if content has changed (or no hash stored yet). Updates the hash table. (TC-DATA-06)"""
    from sqlalchemy import text
    new_hash = compute_content_hash(content)
    now = datetime.utcnow()
    try:
        row = db.execute(text("SELECT content_hash FROM datasource_hashes WHERE source = :s"), {"s": source}).fetchone()
        if row and row[0] == new_hash:
            db.execute(text("UPDATE datasource_hashes SET last_checked_at = :t WHERE source = :s"), {"t": now, "s": source})
            db.commit()
            return False
        if row:
            db.execute(text("UPDATE datasource_hashes SET content_hash = :h, last_checked_at = :t, last_changed_at = :t WHERE source = :s"), {"h": new_hash, "t": now, "s": source})
        else:
            db.execute(text("INSERT INTO datasource_hashes (source, content_hash, last_checked_at, last_changed_at) VALUES (:s, :h, :t, :t)"), {"s": source, "h": new_hash, "t": now})
        db.commit()
    except Exception:
        pass
    return True
