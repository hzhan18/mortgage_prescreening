import re
import secrets
import unicodedata
from datetime import datetime

from extensions import db


def _slugify(text: str) -> str:
    """Small built-in slugifier (avoids an extra dependency): lowercase,
    strip accents, replace anything non-alphanumeric with a hyphen."""
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return text


class Broker(db.Model):
    __tablename__ = "brokers"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120))
    slug = db.Column(db.String(60), unique=True, nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    leads = db.relationship("Lead", backref="broker", lazy=True, order_by="Lead.created_at.desc()")

    @staticmethod
    def make_unique_slug(name: str) -> str:
        """Slugify the broker's name and append a short random suffix so two
        brokers with the same name (or a re-generated link) never collide."""
        base = _slugify(name)[:40] or "broker"
        suffix = secrets.token_hex(3)  # 6 hex chars
        return f"{base}-{suffix}"


class Lead(db.Model):
    __tablename__ = "leads"

    id = db.Column(db.Integer, primary_key=True)
    broker_id = db.Column(db.Integer, db.ForeignKey("brokers.id"), nullable=False)

    # Client contact
    name = db.Column(db.String(120))
    email = db.Column(db.String(120))
    phone = db.Column(db.String(40))
    language = db.Column(db.String(5), default="en")

    # Income
    annual_income = db.Column(db.Float)
    income_source = db.Column(db.String(160))

    # Property
    property_address = db.Column(db.String(255))
    property_price = db.Column(db.Float)
    property_tax_monthly = db.Column(db.Float)
    has_condo = db.Column(db.Boolean, default=False)
    condo_fees_monthly = db.Column(db.Float)
    property_source = db.Column(db.String(40))  # 'lookup' | 'estimated' | 'manual' | 'not found'

    # Debts & assumptions
    down_payment = db.Column(db.Float)
    other_monthly_debts = db.Column(db.Float)
    heating_monthly = db.Column(db.Float)
    contract_rate = db.Column(db.Float)
    amortization_years = db.Column(db.Integer)

    # Results
    qualifies = db.Column(db.Boolean)
    binding_ratio = db.Column(db.String(3))  # 'GDS' | 'TDS'
    gds_ratio = db.Column(db.Float)
    tds_ratio = db.Column(db.Float)
    max_mortgage = db.Column(db.Float)
    max_purchase_price = db.Column(db.Float)

    summary_text = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
