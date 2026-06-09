"""OFAC SDN + Consolidated List collector."""
import xml.etree.ElementTree as ET
import httpx
import json
from sqlalchemy.orm import Session
from app.models.sanctions import SanctionedEntity
from app.collectors.base import normalize_name, HEADERS

OFAC_SDN_URL = "https://sanctionslist.ofac.treas.gov/Home/SdnList"
OFAC_CONS_URL = "https://sanctionslist.ofac.treas.gov/Home/ConsolidatedList"

# Namespace used in OFAC XML
NS = {"ns": "https://sanctionslist.ofac.treas.gov/"}


def _parse_ofac_xml(xml_bytes: bytes, db: Session, source: str = "OFAC") -> int:
    root = ET.fromstring(xml_bytes)
    entries = root.findall(".//ns:sdnEntry", NS) or root.findall(".//sdnEntry")
    if not entries:
        entries = list(root.iter("sdnEntry"))

    count = 0
    for entry in entries:
        def t(tag):
            el = entry.find(tag) or entry.find(f"ns:{tag}", NS)
            return (el.text or "").strip() if el is not None else ""

        uid      = t("uid")
        last     = t("lastName")
        first    = t("firstName")
        sdn_type = t("sdnType").lower()  # individual / entity / vessel / aircraft

        full_name = f"{first} {last}".strip() if first else last

        # Aliases
        aliases = []
        for aka in list(entry.iter("aka")):
            def at(tag): el = aka.find(tag); return (el.text or "").strip() if el is not None else ""
            a_first = at("firstName"); a_last = at("lastName")
            alias = f"{a_first} {a_last}".strip() if a_first else a_last
            if alias:
                aliases.append(alias)

        # Programs
        programs = [p.text.strip() for p in entry.iter("program") if p.text]

        # Dates of birth
        dob = ""
        for dob_el in entry.iter("dateOfBirth"):
            dob = (dob_el.text or "").strip(); break

        # Nationality / country
        nationality = ""
        for cit in entry.iter("citizenship"):
            uid_el = cit.find("uid") or cit.find("country")
            if uid_el is not None and uid_el.text:
                nationality = uid_el.text.strip(); break

        raw = json.dumps({
            "uid": uid, "name": full_name, "type": sdn_type,
            "programs": programs, "aliases": aliases,
        })

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

    db.commit()
    return count


def collect(db: Session) -> dict:
    results = {}
    with httpx.Client(timeout=60, headers=HEADERS, follow_redirects=True) as client:
        # Try SDN XML
        try:
            r = client.get("https://sanctionslist.ofac.treas.gov/Home/SdnList",
                           params={"type": "xml"})
            r.raise_for_status()
            n = _parse_ofac_xml(r.content, db, "OFAC")
            results["sdn"] = n
        except Exception as e:
            results["sdn_error"] = str(e)

    return results
