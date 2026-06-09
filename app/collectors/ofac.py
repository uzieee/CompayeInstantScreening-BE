"""OFAC SDN + Consolidated List collector."""
import xml.etree.ElementTree as ET
import httpx
import json
from sqlalchemy.orm import Session
from app.models.sanctions import SanctionedEntity
from app.collectors.base import normalize_name, HEADERS

OFAC_SDN_URL = "https://sanctionslist.ofac.treas.gov/Home/SdnList"
OFAC_CONS_URL = "https://sanctionslist.ofac.treas.gov/Home/ConsolidatedList"

OFAC_NS = "https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports/XML"


def _tag(name: str) -> str:
    return f"{{{OFAC_NS}}}{name}"


def _parse_ofac_xml(xml_bytes: bytes, db: Session, source: str = "OFAC") -> int:
    root = ET.fromstring(xml_bytes)
    # Try namespaced first, then bare
    entries = list(root.iter(_tag("sdnEntry"))) or list(root.iter("sdnEntry"))

    count = 0
    def _t(el, tag):
        """Find child by namespaced or bare tag."""
        child = el.find(_tag(tag)) or el.find(tag)
        return (child.text or "").strip() if child is not None else ""

    for entry in entries:
        uid      = _t(entry, "uid")
        last     = _t(entry, "lastName")
        first    = _t(entry, "firstName")
        sdn_type = _t(entry, "sdnType").lower()

        full_name = f"{first} {last}".strip() if first else last

        # Aliases
        aliases = []
        for aka in list(entry.iter(_tag("aka"))) or list(entry.iter("aka")):
            a_first = _t(aka, "firstName"); a_last = _t(aka, "lastName")
            alias = f"{a_first} {a_last}".strip() if a_first else a_last
            if alias:
                aliases.append(alias)

        # Programs
        programs = [
            (p.text or "").strip()
            for p in list(entry.iter(_tag("program"))) or list(entry.iter("program"))
            if p.text
        ]

        # Date of birth
        dob = ""
        for dob_el in list(entry.iter(_tag("dateOfBirth"))) or list(entry.iter("dateOfBirth")):
            dob = (dob_el.text or "").strip(); break

        # Nationality
        nationality = ""
        for cit in list(entry.iter(_tag("citizenship"))) or list(entry.iter("citizenship")):
            for field in ["uid", "country"]:
                el = cit.find(_tag(field)) or cit.find(field)
                if el is not None and el.text:
                    nationality = el.text.strip()[:200]; break
            if nationality:
                break

        raw = json.dumps({
            "uid": uid, "name": full_name, "type": sdn_type,
            "programs": programs, "aliases": aliases,
        })

        # Truncate to column limits
        full_name = full_name[:500]
        nationality = nationality[:200]
        dob = dob[:50]

        existing = db.query(SanctionedEntity).filter_by(source=source, source_id=uid).first()
        if existing:
            existing.name = normalize_name(full_name)
            existing.name_original = full_name
            existing.aliases = [normalize_name(a) for a in aliases]
            existing.entity_type = sdn_type or "entity"
            existing.date_of_birth = dob
            existing.nationality = nationality
            existing.program = "; ".join(programs)
            existing.raw_data = raw
        else:
            db.add(SanctionedEntity(
                source=source,
                source_id=uid,
                entity_type=sdn_type or "entity",
                name=normalize_name(full_name),
                name_original=full_name,
                aliases=[normalize_name(a) for a in aliases],
                date_of_birth=dob,
                nationality=nationality,
                program="; ".join(programs),
                raw_data=raw,
            ))
        count += 1

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        raise e
    return count


def collect(db: Session) -> dict:
    results = {}
    with httpx.Client(timeout=120, headers=HEADERS, follow_redirects=True) as client:
        for label, url in [
            ("sdn", "https://www.treasury.gov/ofac/downloads/sdn.xml"),
            ("consolidated", "https://www.treasury.gov/ofac/downloads/consolidated/consolidated.xml"),
        ]:
            try:
                r = client.get(url); r.raise_for_status()
                n = _parse_ofac_xml(r.content, db, "OFAC")
                results[label] = n
                break  # one success is enough
            except Exception as e:
                results[f"{label}_error"] = str(e)

    return results
