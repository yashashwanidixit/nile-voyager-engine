# app/scrapers/base.py
import re

def parse_price(raw: str) -> float:
    """Extract numeric price from strings like '₹4,599' or 'INR 4599'."""
    digits = "".join(ch for ch in raw if ch.isdigit() or ch == ".")
    try:
        return float(digits) if digits else 0.0
    except ValueError:
        return 0.0

def parse_rating(raw: str) -> float:
    """Extract rating like '4.3' from '4.3/5' or '4.3 Very Good'."""
    match = re.search(r"\d(\.\d)?", raw)
    return float(match.group()) if match else 0.0