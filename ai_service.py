"""
All calls to the Anthropic API happen here, server-side, so the API key
never reaches the browser. Two capabilities:

1. extract_income_from_document() — vision extraction of gross income from
   an uploaded NOA / T4 / paystub / employment letter.
2. lookup_property() — web-search-assisted lookup of a property's list
   price, tax, and condo fees from a plain address.

NOTE ON MODEL / TOOL NAMES: this uses "claude-sonnet-5", the current
mid-tier model as of this writing. Anthropic occasionally renames tool
types (the web search tool below is "web_search_20250305") — if either
call starts failing with a model/tool-not-found error, check
https://docs.claude.com for the current identifiers and update the
constants below.
"""

import base64
import json
import re
from dataclasses import dataclass
from typing import Optional

import anthropic

MODEL = "claude-sonnet-5"
WEB_SEARCH_TOOL = {"type": "web_search_20250305", "name": "web_search", "max_uses": 6}


def _get_client(api_key: str) -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=api_key)


def _extract_json(text: str, delimited: bool = False) -> Optional[dict]:
    """Pull a JSON object out of a model response. If `delimited`, look for
    our ===JSON_START===...===JSON_END=== wrapper first (more robust than
    brace-matching when web search results add extra prose)."""
    if delimited:
        m = re.search(r"===JSON_START===([\s\S]*?)===JSON_END===", text)
        if m:
            try:
                return json.loads(m.group(1).strip())
            except json.JSONDecodeError:
                pass
    m = re.search(r"\{[\s\S]*\}", text)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


INCOME_EXTRACTION_PROMPT = """You are analyzing a Canadian income/employment document (a Notice of \
Assessment, T4 slip, pay stub, or employment letter). Extract the following and reply with ONLY a raw \
JSON object — no markdown fences, no commentary:
{"document_type": "NOA"|"T4"|"Paystub"|"Employment Letter"|"Unknown",
"annual_gross_income": number (best estimate of ANNUALIZED gross income; annualize a paystub using its pay period),
"pay_frequency": "weekly"|"biweekly"|"semi-monthly"|"monthly"|"annual"|"unknown",
"employer_name": string or null,
"confidence": "high"|"medium"|"low",
"notes": short note flagging anything uncertain that a human should double-check}
If illegible or not an income document, set document_type "Unknown", annual_gross_income 0, confidence "low", explain in notes.
"""


def extract_income_from_document(api_key: str, file_bytes: bytes, media_type: str) -> dict:
    """Returns a dict matching INCOME_EXTRACTION_PROMPT's schema, or a
    low-confidence 'Unknown' dict if the model call fails outright."""
    client = _get_client(api_key)
    b64 = base64.b64encode(file_bytes).decode("utf-8")

    is_pdf = media_type == "application/pdf"
    doc_block = (
        {"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": b64}}
        if is_pdf
        else {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": b64}}
    )

    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=1000,
            messages=[{"role": "user", "content": [doc_block, {"type": "text", "text": INCOME_EXTRACTION_PROMPT}]}],
        )
        text = "".join(block.text for block in response.content if block.type == "text")
        parsed = _extract_json(text)
        if parsed is None:
            raise ValueError("model did not return parseable JSON")
        return parsed
    except Exception as exc:  # noqa: BLE001 — surface any failure as a low-confidence result
        return {
            "document_type": "Unknown",
            "annual_gross_income": 0,
            "pay_frequency": "unknown",
            "employer_name": None,
            "confidence": "low",
            "notes": f"Automatic extraction failed ({exc}). Please enter income manually.",
        }


def _property_lookup_prompt(address: str) -> str:
    return f"""Find the current or most recent real estate listing for this Canadian property: "{address}".

Search persistently before concluding it can't be found — try several query variants, not just one:
- the address exactly as given
- the unit and street number combined differently (e.g. "15677 24 Avenue #19", "19-15677 24 Avenue", "15677 24 Ave Unit 19")
- the street address without the unit number, then look for the specific unit in the results (this often surfaces the building/strata name, which you can then search again)
- site-specific queries against realtor.ca, rew.ca, redfin.ca, zealty.ca, and local brokerage sites
Only conclude "found": false after trying at least 3 different query variants with no useful result.

Once you have what you can find, respond with a JSON object wrapped in delimiters exactly like this, with nothing else before or after:
===JSON_START===
{{"found": boolean,
"list_price": number or null,
"property_type": "condo" or "townhouse" or "detached" or "other" or null,
"is_condo": boolean,
"condo_fees_monthly": number or null,
"estimated_property_tax_monthly": number or null,
"source_note": "short note on what you found, which source, and your confidence, or which query variants you tried if nothing worked"}}
===JSON_END===

If you find a list_price but no tax figure, estimate estimated_property_tax_monthly as list_price*0.01/12 and say so in source_note. Never invent a precise figure you did not find or reasonably derive."""


def lookup_property(api_key: str, address: str) -> dict:
    """Returns a dict with found/list_price/property_type/is_condo/
    condo_fees_monthly/estimated_property_tax_monthly/source_note. On any
    failure, returns found: False with an explanatory source_note so the
    UI can fall back to manual entry."""
    client = _get_client(api_key)
    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=1200,
            messages=[{"role": "user", "content": _property_lookup_prompt(address)}],
            tools=[WEB_SEARCH_TOOL],
        )
        text = "".join(block.text for block in response.content if block.type == "text")
        parsed = _extract_json(text, delimited=True)
        if parsed is None:
            raise ValueError("model did not return parseable JSON")
        return parsed
    except Exception as exc:  # noqa: BLE001
        return {
            "found": False,
            "list_price": None,
            "property_type": None,
            "is_condo": False,
            "condo_fees_monthly": None,
            "estimated_property_tax_monthly": None,
            "source_note": f"Automatic lookup failed ({exc}). Please enter property details manually.",
        }
