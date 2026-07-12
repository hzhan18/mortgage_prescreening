import os

from flask import Flask, abort, jsonify, redirect, render_template, request, url_for
from werkzeug.utils import secure_filename

from ai_service import extract_income_from_document, lookup_property
from calculations import QualificationInput, calculate_qualification
from config import Config
from extensions import db
from models import Broker, Lead

ALLOWED_UPLOAD_TYPES = {"image/png", "image/jpeg", "image/webp", "application/pdf"}


def create_app():
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(Config)
    os.makedirs(app.instance_path, exist_ok=True)

    db.init_app(app)
    with app.app_context():
        db.create_all()

    register_routes(app)
    register_cli(app)
    return app


app = create_app()
application = app

def register_routes(app: Flask):

    @app.get("/")
    def index():
        return redirect(url_for("admin"))

    # ---------- Client-facing assessment ----------

    @app.get("/b/<slug>")
    def assessment(slug):
        broker = Broker.query.filter_by(slug=slug).first()
        if broker is None:
            abort(404)
        return render_template("assessment.html", broker=broker)

    @app.post("/b/<slug>/api/extract-income")
    def api_extract_income(slug):
        broker = Broker.query.filter_by(slug=slug).first_or_404()
        if "file" not in request.files:
            return jsonify({"error": "no file uploaded"}), 400
        file = request.files["file"]
        media_type = file.mimetype
        if media_type not in ALLOWED_UPLOAD_TYPES:
            return jsonify({"error": f"unsupported file type: {media_type}"}), 400
        file_bytes = file.read()
        result = extract_income_from_document(app.config["ANTHROPIC_API_KEY"], file_bytes, media_type)
        return jsonify(result)

    @app.post("/b/<slug>/api/lookup-property")
    def api_lookup_property(slug):
        broker = Broker.query.filter_by(slug=slug).first_or_404()
        data = request.get_json(silent=True) or {}
        address = (data.get("address") or "").strip()
        if not address:
            return jsonify({"error": "address is required"}), 400
        result = lookup_property(app.config["ANTHROPIC_API_KEY"], address)
        return jsonify(result)

    @app.post("/b/<slug>/api/submit")
    def api_submit(slug):
        broker = Broker.query.filter_by(slug=slug).first_or_404()
        data = request.get_json(silent=True) or {}

        try:
            qual_input = QualificationInput(
                annual_income=float(data.get("annual_income") or 0),
                down_payment=float(data.get("down_payment") or 0),
                other_monthly_debts=float(data.get("other_monthly_debts") or 0),
                property_tax_monthly=float(data.get("property_tax_monthly") or 0),
                heating_monthly=float(data.get("heating_monthly") or 100),
                condo_fees_monthly=float(data.get("condo_fees_monthly") or 0),
                has_condo=bool(data.get("has_condo") or False),
                contract_rate_pct=float(data.get("contract_rate_pct") or 5.09),
                amortization_years=int(data.get("amortization_years") or 25),
            )
        except (TypeError, ValueError):
            return jsonify({"error": "invalid numeric input"}), 400

        result = calculate_qualification(qual_input)

        lead = Lead(
            broker_id=broker.id,
            name=data.get("name"),
            email=data.get("email"),
            phone=data.get("phone"),
            language=data.get("language", "en"),
            annual_income=qual_input.annual_income,
            income_source=data.get("income_source"),
            property_address=data.get("property_address"),
            property_price=data.get("property_price"),
            property_tax_monthly=qual_input.property_tax_monthly,
            has_condo=qual_input.has_condo,
            condo_fees_monthly=qual_input.condo_fees_monthly,
            property_source=data.get("property_source"),
            down_payment=qual_input.down_payment,
            other_monthly_debts=qual_input.other_monthly_debts,
            heating_monthly=qual_input.heating_monthly,
            contract_rate=qual_input.contract_rate_pct,
            amortization_years=qual_input.amortization_years,
            qualifies=result.qualifies,
            binding_ratio=result.binding_ratio,
            gds_ratio=result.actual_gds_pct,
            tds_ratio=result.actual_tds_pct,
            max_mortgage=result.max_mortgage,
            max_purchase_price=result.max_purchase_price,
        )

        summary = build_broker_summary(broker, lead, result)
        lead.summary_text = summary
        db.session.add(lead)
        db.session.commit()

        return jsonify({
            "qualifies": result.qualifies,
            "binding_ratio": result.binding_ratio,
            "max_mortgage": round(result.max_mortgage),
            "max_purchase_price": round(result.max_purchase_price),
            "down_payment_pct": round(result.down_payment_pct, 1),
            "actual_gds_pct": round(result.actual_gds_pct, 1),
            "actual_tds_pct": round(result.actual_tds_pct, 1),
            "qualifying_rate_pct": round(result.qualifying_rate_pct, 2),
            "summary_text": summary,
        })

    # ---------- Lightweight broker admin ----------

    @app.get("/admin")
    def admin():
        token = request.args.get("token", "")
        if token != app.config["ADMIN_TOKEN"]:
            return "Not authorized. Append ?token=YOUR_ADMIN_TOKEN to the URL.", 401
        brokers = Broker.query.order_by(Broker.created_at.desc()).all()
        return render_template("admin.html", brokers=brokers, token=token, request_host=request.host_url.rstrip("/"))


def build_broker_summary(broker: Broker, lead: Lead, result) -> str:
    from datetime import datetime

    today = datetime.utcnow().strftime("%B %d, %Y")
    lines = [
        f"PRE-SCREENING SUMMARY — {today}",
        "================================================",
        "CLIENT",
        f"  Name:   {lead.name}",
        f"  Email:  {lead.email}",
        f"  Phone:  {lead.phone}",
        "",
        "PROPERTY",
    ]
    if lead.property_price:
        lines.append(f"  List price: ${round(lead.property_price):,} ({lead.property_source})")
    else:
        lines.append("  No specific property provided")
    lines.append(f"  Monthly property tax: ${round(lead.property_tax_monthly or 0):,}")
    lines.append(
        f"  Condo/strata fees: ${round(lead.condo_fees_monthly or 0):,}/mo (50% counted)"
        if lead.has_condo else "  Condo/strata fees: N/A"
    )
    lines += [
        "",
        "INCOME",
        f"  Annual gross income used: ${round(lead.annual_income or 0):,}",
        f"  Source: {lead.income_source}",
        "",
        "MONTHLY OBLIGATIONS",
        f"  Heating: ${round(lead.heating_monthly or 0):,}",
        f"  Other monthly debts: ${round(lead.other_monthly_debts or 0):,}",
        "",
        "QUALIFICATION",
        f"  GDS ratio: {result.actual_gds_pct:.1f}% (limit 39%)",
        f"  TDS ratio: {result.actual_tds_pct:.1f}% (limit 44%)",
        f"  Binding constraint: {result.binding_ratio}",
        f"  Qualifying (stress test) rate: {result.qualifying_rate_pct:.2f}%",
        f"  Amortization: {lead.amortization_years} years",
        "",
        "RESULT",
    ]
    if result.qualifies:
        lines.append(f"  Estimated max mortgage: ${round(result.max_mortgage):,}")
        lines.append(f"  Down payment: ${round(lead.down_payment or 0):,} ({result.down_payment_pct:.0f}%)")
        lines.append(f"  Estimated max purchase price: ${round(result.max_purchase_price):,}")
        if result.down_payment_pct < 20:
            lines.append("  Note: down payment under 20% — mortgage default insurance premium would apply.")
    else:
        lines.append(
            f"  Client does not currently clear the {result.binding_ratio} ratio limit. "
            "Consider debt paydown, larger down payment, or co-signer options."
        )
    lines += [
        "",
        "------------------------------------------------",
        "Preliminary, non-binding estimate for internal pre-screening only.",
        "Not a mortgage pre-approval or credit decision. Subject to full lender underwriting.",
        "================================================",
    ]
    return "\n".join(lines)


def register_cli(app: Flask):
    @app.cli.command("create-broker")
    def create_broker_command():
        """Interactive CLI: flask create-broker"""
        name = input("Broker/realtor name: ").strip()
        email = input("Broker/realtor email (optional): ").strip() or None
        slug = Broker.make_unique_slug(name)
        broker = Broker(name=name, email=email, slug=slug)
        db.session.add(broker)
        db.session.commit()
        print("\nBroker created.")
        print(f"  Name: {broker.name}")
        print(f"  Shareable link (replace host/port with your deployed domain):")
        print(f"  http://127.0.0.1:5000/b/{broker.slug}")


app = create_app()

if __name__ == "__main__":
    app.run(debug=True)
