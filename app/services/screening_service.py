"""RapidFuzz-based screening engine."""
from __future__ import annotations
import json
from datetime import datetime
from typing import Optional
from sqlalchemy.orm import Session
from rapidfuzz import process, fuzz
from app.models.sanctions import SanctionedEntity
from app.models.screening import ScreeningSession, ScreeningResult, MatchResult, ScreeningStatus
from app.models.audit import AuditLog, AuditAction
from app.models.tenant import Tenant
from app.collectors.base import normalize_name
from app.services.ai_service import generate_risk_narrative

# Score thresholds
HIT_THRESHOLD      = 88
POSSIBLE_THRESHOLD = 72


def _classify(score: float) -> MatchResult:
    if score >= HIT_THRESHOLD:
        return MatchResult.hit
    if score >= POSSIBLE_THRESHOLD:
        return MatchResult.possible_match
    return MatchResult.clear


def _composite_score(query: str, name: str) -> float:
    """Weighted composite of 4 RapidFuzz algorithms (TC-SCR-08)."""
    w  = fuzz.WRatio(query, name)
    ts = fuzz.token_sort_ratio(query, name)
    te = fuzz.token_set_ratio(query, name)
    p  = fuzz.partial_ratio(query, name)
    return w * 0.40 + ts * 0.25 + te * 0.25 + p * 0.10


def screen_entity(
    db: Session,
    tenant_id: str,
    user_id: Optional[str],
    query_name: str,
    query_country: Optional[str] = None,
    query_type: Optional[str] = None,
    query_dob: Optional[str] = None,
    sources: Optional[list] = None,
    ip_address: Optional[str] = None,
) -> ScreeningSession:
    """Run fuzzy-match screening for a single entity name."""

    norm_query = normalize_name(query_name)
    sources = sources or ["OFAC", "EU", "UN", "UK"]

    # Create session
    session = ScreeningSession(
        tenant_id=tenant_id,
        user_id=user_id,
        mode="single",
        query_name=query_name,
        query_country=query_country,
        query_type=query_type,
        query_dob=query_dob,
        status=ScreeningStatus.pending,
        sources_checked=sources,
    )
    db.add(session)
    db.flush()

    # Pull all entities from requested sources
    q = db.query(SanctionedEntity).filter(SanctionedEntity.source.in_(sources))
    if query_type:
        q = q.filter(SanctionedEntity.entity_type == query_type)
    entities = q.all()

    # Build name → entity_id lookup
    name_map: dict[str, str] = {}
    for e in entities:
        name_map[e.name] = str(e.id)
        for alias in (e.aliases or []):
            if alias:
                name_map[alias] = str(e.id)

    all_names = list(name_map.keys())

    # Pre-filter with WRatio to top 50 candidates, then apply composite scoring (TC-SCR-08)
    prefilter = process.extract(
        norm_query,
        all_names,
        scorer=fuzz.WRatio,
        limit=50,
    ) if all_names else []

    # Deduplicate by entity id, keep highest composite score
    best: dict[str, tuple] = {}
    for name, _, _ in prefilter:
        score = _composite_score(norm_query, name)
        eid = name_map[name]
        if eid not in best or score > best[eid][1]:
            best[eid] = (name, score)

    # Apply DOB and country score adjustments (TC-SCR-05, TC-SCR-06)
    entity_cache_pre: dict[str, SanctionedEntity] = {str(e.id): e for e in entities}
    adjusted_best: dict[str, tuple] = {}
    for eid, (matched_name, score) in best.items():
        entity = entity_cache_pre.get(eid)
        if entity:
            # DOB adjustment (TC-SCR-05): boost if match, penalise if mismatch
            if query_dob and entity.date_of_birth:
                try:
                    q_year = str(query_dob)[:4]
                    e_year = str(entity.date_of_birth)[:4]
                    if q_year == e_year:
                        score = min(100.0, score + 5)
                    else:
                        score = max(0.0, score - 8)
                except Exception:
                    pass
            # Country adjustment (TC-SCR-06): penalise if country mismatch
            if query_country and (entity.country or entity.nationality):
                qc = query_country.strip().upper()[:2]
                ec = ((entity.country or entity.nationality) or "").strip().upper()[:2]
                if ec and qc != ec:
                    score = max(0.0, score - 10)
        adjusted_best[eid] = (matched_name, score)

    best = adjusted_best

    # Create result rows for anything above possible threshold
    hit_count = possible_count = 0
    entity_cache: dict[str, SanctionedEntity] = entity_cache_pre

    results_created = []
    for eid, (matched_name, score) in sorted(best.items(), key=lambda x: -x[1][1]):
        classification = _classify(score)
        if classification == MatchResult.clear and score < POSSIBLE_THRESHOLD:
            continue

        entity = entity_cache.get(eid)
        detail = {}
        if entity:
            detail = {
                "id": str(entity.id),
                "name": entity.name_original,
                "source": entity.source,
                "type": entity.entity_type,
                "program": entity.program,
                "country": entity.country or entity.nationality,
                "date_of_birth": entity.date_of_birth,
                "aliases": entity.aliases or [],
                "source_id": entity.source_id,
                "reason": entity.reason,
            }

        result = ScreeningResult(
            session_id=session.id,
            matched_entity_id=eid,
            match_result=classification,
            score=round(score, 2),
            matched_name=entity.name_original if entity else matched_name,
            matched_source=entity.source if entity else "",
            matched_type=entity.entity_type if entity else "",
            matched_country=(entity.country or entity.nationality) if entity else "",
            matched_program=entity.program if entity else "",
            match_detail=detail,
        )
        db.add(result)
        results_created.append(result)

        if classification == MatchResult.hit:
            hit_count += 1
        elif classification == MatchResult.possible_match:
            possible_count += 1

    # Update session
    session.total_results = len(results_created)
    session.hit_count = hit_count
    session.possible_count = possible_count
    session.status = ScreeningStatus.completed
    session.completed_at = datetime.utcnow()

    # Determine overall result for audit
    if hit_count > 0:
        audit_result = "hit"
    elif possible_count > 0:
        audit_result = "possible_match"
    else:
        audit_result = "clear"

    # AI risk narrative
    top_matches = [
        {
            "name": r.matched_name,
            "source": r.matched_source,
            "score": r.score,
            "result": r.match_result.value,
            "program": r.matched_program,
            "country": r.matched_country,
        }
        for r in sorted(results_created, key=lambda x: -x.score)
    ]
    session.ai_narrative = generate_risk_narrative(
        query_name=query_name,
        overall_result=audit_result,
        hit_count=hit_count,
        possible_count=possible_count,
        sources_checked=sources,
        top_matches=top_matches,
        query_country=query_country,
        query_type=query_type,
    )

    # Audit log
    db.add(AuditLog(
        tenant_id=tenant_id,
        user_id=user_id,
        action=AuditAction.screening,
        entity_name=query_name,
        result=audit_result,
        ip_address=ip_address,
        details={"session_id": str(session.id), "sources": sources, "score_top": round(prefilter[0][1], 1) if prefilter else 0},
    ))

    # Increment tenant quota usage
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if tenant:
        tenant.searches_used = (tenant.searches_used or 0) + 1

    db.commit()
    db.refresh(session)
    return session
