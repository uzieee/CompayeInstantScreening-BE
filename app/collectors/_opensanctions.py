"""Shared helper: load OpenSanctions simple CSV format into SanctionedEntity."""
import csv
import io
import json
import httpx
from sqlalchemy.orm import Session
from app.models.sanctions import SanctionedEntity
from app.collectors.base import normalize_name, HEADERS


def load_opensanctions_csv(url: str, source: str, program_default: str, db: Session) -> dict:
    try:
        with httpx.Client(timeout=120, headers=HEADERS, follow_redirects=True) as c:
            r = c.get(url)
            r.raise_for_status()
    except Exception as e:
        return {"error": str(e)}

    reader = csv.DictReader(io.StringIO(r.text))
    count = 0

    for row in reader:
        uid  = row.get("id", "").strip()
        full = row.get("name", "").strip()
        if not uid or not full:
            continue

        schema    = (row.get("schema") or "").lower()
        etype     = "individual" if "person" in schema else "entity"
        countries = (row.get("countries") or "").strip()
        dob       = (row.get("birth_date") or "").strip()

        # Aliases — semicolon-separated in this format
        raw_aliases = row.get("aliases") or ""
        aliases = [a.strip() for a in raw_aliases.split(";") if a.strip() and a.strip() != full]

        # Program from sanctions column (JSON-ish blob) or default
        sanctions_blob = row.get("sanctions") or ""
        program = program_default
        if "program" in sanctions_blob:
            import re
            m = re.search(r"'program':\s*'([^']+)'", sanctions_blob)
            if m:
                program = m.group(1)

        raw = json.dumps({"id": uid, "name": full, "schema": schema,
                          "countries": countries, "dataset": row.get("dataset", "")})

        full     = full[:500]
        countries = countries[:200]
        dob      = dob[:50]
        program  = program[:500]

        existing = db.query(SanctionedEntity).filter_by(source=source, source_id=uid).first()
        if existing:
            existing.name = normalize_name(full)
            existing.name_original = full
            existing.aliases = [normalize_name(a) for a in aliases]
            existing.country = countries
        else:
            db.add(SanctionedEntity(
                source=source,
                source_id=uid,
                entity_type=etype,
                name=normalize_name(full),
                name_original=full,
                aliases=[normalize_name(a) for a in aliases],
                country=countries,
                date_of_birth=dob,
                program=program,
                raw_data=raw,
            ))
        count += 1

        # Commit in batches to avoid huge transactions
        if count % 500 == 0:
            try:
                db.commit()
            except Exception:
                db.rollback()

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        return {"error": f"Commit failed: {e}"}

    return {"total": count}
