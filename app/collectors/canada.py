"""Canada DFATD SEMA Sanctions — via OpenSanctions structured CSV."""
from sqlalchemy.orm import Session
from app.collectors._opensanctions import load_opensanctions_csv

URL = "https://data.opensanctions.org/datasets/latest/ca_dfatd_sema_sanctions/targets.simple.csv"


def collect(db: Session) -> dict:
    return load_opensanctions_csv(URL, "CANADA", "Canada SEMA Sanctions", db)
