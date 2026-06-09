"""UK OFSI Financial Sanctions collector (CSV format)."""
import csv
import io
import httpx
import json
from sqlalchemy.orm import Session
from app.models.sanctions import SanctionedEntity
from app.collectors.base import normalize_name, HEADERS

UK_URL = "https://ofsistorage.blob.core.windows.net/publishlive/2022format/ConList.csv"
UK_ALT = "https://www.gov.uk/government/publications/financial-sanctions-consolidated-list-of-targets"


def collect(db: Session) -> dict:
    try:
        with httpx.Client(timeout=60, headers=HEADERS, follow_redirects=True) as c:
            r = c.get(UK_URL); r.raise_for_status()
        content = r.text
    except Exception as e:
        return {"error": str(e)}

    reader = csv.DictReader(io.StringIO(content))
    count = 0
    seen_uids: set = set()

    for row in reader:
        uid = row.get("GroupID") or row.get("UniqueID") or ""
        if not uid:
            continue

        full_name = row.get("Name 6") or row.get("Name1") or ""
        if not full_name:
            parts = [row.get(f"Name {i}", "") for i in range(1, 6)]
            full_name = " ".join(p for p in parts if p).strip()

        etype = (row.get("Group Type") or "entity").lower()
        country = row.get("Country") or row.get("Nationality") or ""
        dob = row.get("DOB") or ""
        program = row.get("Regime") or "UK Financial Sanctions"

        # Collect aliases per group id
        alias = row.get("AliasName") or row.get("Alias") or ""
        aliases = [alias] if alias else []

        raw = json.dumps({"uid": uid, "name": full_name, "regime": program})

        if uid in seen_uids:
            # Add alias to existing
            existing = db.query(SanctionedEntity).filter_by(source="UK", source_id=uid).first()
            if existing and alias and normalize_name(alias) not in (existing.aliases or []):
                existing.aliases = (existing.aliases or []) + [normalize_name(alias)]
            continue

        seen_uids.add(uid)
        existing = db.query(SanctionedEntity).filter_by(source="UK", source_id=uid).first()
        if existing:
            existing.name = normalize_name(full_name)
            existing.name_original = full_name
        else:
            if not full_name:
                continue
            db.add(SanctionedEntity(
                source="UK", source_id=uid, entity_type=etype,
                name=normalize_name(full_name), name_original=full_name,
                aliases=[normalize_name(a) for a in aliases if a],
                country=country, date_of_birth=dob, program=program, raw_data=raw,
            ))
        count += 1

    db.commit()
    return {"total": count}
