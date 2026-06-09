"""EU Financial Sanctions (EEAS) collector."""
import xml.etree.ElementTree as ET
import httpx
import json
from sqlalchemy.orm import Session
from app.models.sanctions import SanctionedEntity
from app.collectors.base import normalize_name, HEADERS

EU_URL = "https://webgate.ec.europa.eu/fsd/fsf/public/files/xmlFullSanctionsList_1_1/content"
EU_ALT = "https://data.europa.eu/api/hub/repo/datasets/consolidated-list-of-persons-groups-and-entities-subject-to-eu-financial-sanctions.xml"


def collect(db: Session) -> dict:
    content = None
    for url in [EU_URL, EU_ALT]:
        try:
            with httpx.Client(timeout=60, headers=HEADERS, follow_redirects=True) as c:
                r = c.get(url); r.raise_for_status()
            content = r.content
            break
        except Exception:
            continue

    if not content:
        return {"error": "Could not fetch EU sanctions list"}

    try:
        root = ET.fromstring(content)
    except ET.ParseError as e:
        return {"error": f"XML parse error: {e}"}

    count = 0
    # EU XML uses both sanctionEntity and subjectType
    for entry in list(root.iter("sanctionEntity")) or list(root.iter("entity")):
        uid = entry.get("euReferenceNumber") or entry.get("id") or ""
        etype = (entry.get("subjectType") or "entity").lower()

        # Name
        name_parts = []
        for nm in entry.iter("nameAlias"):
            whole = nm.get("wholeName") or ""
            first = nm.get("firstName") or ""; last = nm.get("lastName") or ""
            n = whole or f"{first} {last}".strip()
            if n:
                name_parts.append(n)

        full_name = name_parts[0] if name_parts else ""
        aliases   = name_parts[1:] if len(name_parts) > 1 else []

        if not full_name:
            continue

        # Country
        country = ""
        for addr in entry.iter("address"):
            country = addr.get("countryIso2Code") or addr.get("countryDescription") or ""; break

        program = "EU Financial Sanctions"
        raw = json.dumps({"uid": uid, "name": full_name, "type": etype})

        existing = db.query(SanctionedEntity).filter_by(source="EU", source_id=uid).first()
        if existing:
            existing.name = normalize_name(full_name)
            existing.name_original = full_name
            existing.aliases = [normalize_name(a) for a in aliases]
        else:
            db.add(SanctionedEntity(
                source="EU", source_id=uid, entity_type=etype,
                name=normalize_name(full_name), name_original=full_name,
                aliases=[normalize_name(a) for a in aliases],
                country=country, program=program, raw_data=raw,
            ))
        count += 1

    db.commit()
    return {"total": count}
