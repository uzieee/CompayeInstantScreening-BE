"""Australia DFAT Sanctions — via OpenSanctions structured CSV."""
from sqlalchemy.orm import Session
from app.collectors._opensanctions import load_opensanctions_csv

URL = "https://data.opensanctions.org/datasets/latest/au_dfat_sanctions/targets.simple.csv"


def collect(db: Session) -> dict:
    return load_opensanctions_csv(URL, "AUSTRALIA", "Australia DFAT Sanctions", db)
