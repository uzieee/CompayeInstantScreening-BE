"""UN Security Council Consolidated List collector."""
import xml.etree.ElementTree as ET
import httpx
import json
from sqlalchemy.orm import Session
from app.models.sanctions import SanctionedEntity
from app.collectors.base import normalize_name, HEADERS

UN_URL = "https://scsanctions.un.org/resources/xml/en/consolidated.xml"


def collect(db: Session) -> dict:
    try:
        with httpx.Client(timeout=60, headers=HEADERS, follow_redirects=True) as client:
            r = client.get(UN_URL)
            r.raise_for_status()
        root = ET.fromstring(r.content)
    except Exception as e:
        return {"error": str(e)}

    count = 0
    for individual in root.iter("INDIVIDUAL"):
        def t(tag):
            el = individual.find(tag)
            return (el.text or "").strip() if el is not None else ""

        uid       = t("DATAID") or t("REFERENCE_NUMBER")
        first     = t("FIRST_NAME"); second = t("SECOND_NAME")
        third     = t("THIRD_NAME"); fourth = t("FOURTH_NAME")
        full_name = " ".join(filter(None, [first, second, third, fourth]))

        aliases = []
        for aka in individual.iter("ALIAS"):
            a = " ".join(filter(None, [
                (aka.find("QUALITY") and aka.find("QUALITY").text or ""),
                (aka.find("ALIAS_NAME") and aka.find("ALIAS_NAME").text or ""),
            ])).strip()
            if a:
                aliases.append(a)

        dob = t("DATE1") or t("DATE_OF_BIRTH")
        nationality_el = individual.find("NATIONALITY")
        nationality = ""
        if nationality_el is not None:
            v = nationality_el.find("VALUE")
            nationality = (v.text or "").strip() if v is not None else ""

        _upsert(db, "UN", uid, "individual", full_name, aliases, nationality=nationality, dob=dob,
                program="UN SC Consolidated List",
                raw=json.dumps({"uid": uid, "name": full_name}))
        count += 1

    for entity in root.iter("ENTITY"):
        def t(tag):
            el = entity.find(tag)
            return (el.text or "").strip() if el is not None else ""

        uid       = t("DATAID") or t("REFERENCE_NUMBER")
        full_name = t("FIRST_NAME") or t("ENTITY_NAME")

        aliases = []
        for aka in entity.iter("ALIAS"):
            an = aka.find("ALIAS_NAME")
            if an is not None and an.text:
                aliases.append(an.text.strip())

        _upsert(db, "UN", uid, "entity", full_name, aliases,
                program="UN SC Consolidated List",
                raw=json.dumps({"uid": uid, "name": full_name}))
        count += 1

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        return {"error": f"Commit failed: {e}"}
    return {"total": count}


def _upsert(db, source, uid, etype, full_name, aliases,
            nationality="", dob="", program="", raw=""):
    if not full_name:
        return
    # Truncate fields to safe lengths
    nationality = (nationality or "")[:200]
    dob = (dob or "")[:50]
    program = (program or "")[:500]
    full_name = (full_name or "")[:500]

    existing = db.query(SanctionedEntity).filter_by(source=source, source_id=uid).first()
    if existing:
        existing.name = normalize_name(full_name)
        existing.name_original = full_name
        existing.aliases = [normalize_name(a) for a in aliases]
    else:
        db.add(SanctionedEntity(
            source=source, source_id=uid, entity_type=etype,
            name=normalize_name(full_name), name_original=full_name,
            aliases=[normalize_name(a) for a in aliases],
            nationality=nationality, date_of_birth=dob,
            program=program, raw_data=raw,
        ))
