"""Switzerland SECO Financial Sanctions — via OpenSanctions structured CSV."""
from sqlalchemy.orm import Session
from app.collectors._opensanctions import load_opensanctions_csv

URL = "https://data.opensanctions.org/datasets/latest/ch_seco_sanctions/targets.simple.csv"


def collect(db: Session) -> dict:
    return load_opensanctions_csv(URL, "SECO", "Switzerland SECO Sanctions", db)
