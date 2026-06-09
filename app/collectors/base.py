import re
import unicodedata


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
