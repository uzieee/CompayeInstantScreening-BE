"""US Consolidated Screening List — BIS Entity List, State Dept, and more.

OpenSanctions aggregates the US Trade CSL which includes:
  - BIS Entity List (export controls)
  - State Dept Nonproliferation Sanctions
  - State Dept AECA Debarred List
  - DTC Debarred parties
  - OFAC SDN (also covered by our ofac.py — deduplication handled by source_id)
"""
from sqlalchemy.orm import Session
from app.collectors._opensanctions import load_opensanctions_csv

URL = "https://data.opensanctions.org/datasets/latest/us_trade_csl/targets.simple.csv"


def collect(db: Session) -> dict:
    return load_opensanctions_csv(URL, "BIS", "US Consolidated Screening List", db)
