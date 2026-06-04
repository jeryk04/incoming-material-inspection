import os
import json
import ast
import base64

import fitz  # PyMuPDF
from dotenv import load_dotenv
from openai import OpenAI

from material_spec_database import spec_to_prompt_text


load_dotenv(dotenv_path=".env")

# A page is considered "digital" (has selectable text) when it contains at
# least this many characters of extracted text.
_MIN_TEXT_CHARS = 150


def extract_pdf_text(pdf_path, max_pages=2):
    """Return list of plain-text strings, one per page."""
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")

    document = fitz.open(pdf_path)
    texts = []

    for i in range(min(len(document), max_pages)):
        texts.append(document[i].get_text("text").strip())

    document.close()
    return texts


def render_pdf_pages_to_base64(pdf_path, max_pages=2, zoom=2):
    """Convert PDF pages to base64 PNG images (used for scanned PDFs)."""
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")

    document = fitz.open(pdf_path)
    images = []

    for i in range(min(len(document), max_pages)):
        page = document[i]
        matrix = fitz.Matrix(zoom, zoom)
        pixmap = page.get_pixmap(matrix=matrix, alpha=False)
        images.append(base64.b64encode(pixmap.tobytes("png")).decode("utf-8"))

    document.close()
    return images


def remove_markdown_fences(text):
    text = str(text).strip()
    if text.startswith("```json"):
        text = text.replace("```json", "", 1).strip()
    if text.startswith("```"):
        text = text.replace("```", "", 1).strip()
    if text.endswith("```"):
        text = text[:-3].strip()
    return text


def extract_json_object(text):
    text = str(text).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start:end + 1]
    return text


def parse_ai_json(ai_text):
    """Robustly parse AI output into a Python dictionary."""
    if ai_text is None:
        return {"error": "AI response was empty", "raw_response": ""}

    original = str(ai_text).strip()
    candidates = [original]

    try:
        decoded = json.loads(original)
        if isinstance(decoded, dict):
            return decoded
        if isinstance(decoded, str):
            candidates.append(decoded.strip())
    except Exception:
        pass

    try:
        literal_decoded = ast.literal_eval(original)
        if isinstance(literal_decoded, dict):
            return literal_decoded
        if isinstance(literal_decoded, str):
            candidates.append(literal_decoded.strip())
    except Exception:
        pass

    manually_cleaned = (
        original
        .replace("\\n", "\n")
        .replace('\\"', '"')
        .replace("\\t", "\t")
    )
    candidates.append(manually_cleaned.strip())

    for candidate in candidates:
        candidate = remove_markdown_fences(candidate)
        candidate = extract_json_object(candidate)
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                return parsed
            if isinstance(parsed, str):
                second = extract_json_object(remove_markdown_fences(parsed))
                parsed_again = json.loads(second)
                if isinstance(parsed_again, dict):
                    return parsed_again
        except Exception:
            continue

    return {"error": "AI response was not valid JSON", "raw_response": original}


# ── Shared prompt template ────────────────────────────────────────────────────

_PROMPT_TEMPLATE = """
You are a manufacturing quality assurance assistant.

You will receive content from a combined incoming inspection PDF:
- Page 1: G&J incoming inspection data sheet
- Page 2: supplier material test certificate

{content_description}

Analyze both and return ONLY one valid JSON object.
Do not include markdown. Do not include explanations. Do not wrap in ```json.

If an approved internal material specification is provided below, use it as the
source of truth for requirements. Do not replace values from the PDF; use the
database requirements only to judge conformance.

{material_spec_text}

Required JSON format:

{{
  "material_info": {{
    "supplier": "",
    "item_number": "",
    "part_number": "",
    "po_number": "",
    "quantity": "",
    "heat_number": "",
    "inspection_date": "",
    "inspector": "",
    "sample_size": ""
  }},
  "measurements": [
    {{
      "measurement": "",
      "lsl": "",
      "usl": "",
      "average": "",
      "min": "",
      "max": "",
      "instrument": "",
      "result": ""
    }}
  ],
  "certificate": {{
    "supplier_name": "",
    "heat_number": "",
    "material_description": "",
    "material_grade": "",
    "purchase_order": "",
    "outside_diameter": "",
    "inside_diameter": "",
    "wall_thickness": "",
    "length": "",
    "straightness": "",
    "yield_strength": "",
    "tensile_strength": "",
    "elongation": "",
    "hardness": "",
    "chemical_composition": {{
      "C": "", "Mn": "", "P": "", "S": "", "Si": "",
      "Al": "", "N": "", "Cr": "", "Ni": "", "Mo": "", "Cu": ""
    }},
    "chemical_specified": {{
      "C": "", "Mn": "", "P": "", "S": "", "Si": "",
      "Al": "", "N": "", "Cr": "", "Ni": "", "Mo": "", "Cu": ""
    }},
    "mechanical_specified": {{
      "yield_strength": "",
      "tensile_strength": "",
      "elongation": "",
      "hardness": ""
    }},
    "mechanical_properties": [
      {{
        "property": "",
        "specified": "",
        "observed": "",
        "unit": "",
        "result": ""
      }}
    ],
    "dimensional_specified": {{
      "outside_diameter": "",
      "inside_diameter": "",
      "wall_thickness": "",
      "length": "",
      "straightness": ""
    }},
    "certificate_status_notes": "",
    "certificate_review_result": ""
  }},
  "validation": {{
    "heat_number_match": "",
    "po_number_match": "",
    "material_review": "",
    "certificate_review_status": "",
    "final_lot_decision": ""
  }}
}}

Important rules:
- item_number and part_number can be the same if only one is visible.
- If a value is completely absent from the certificate, use an empty string. If a cell shows "N.A", "N/A", "N.S", "N.S.", "N.T.", "Not Tested", or similar, extract that text exactly as printed (e.g. "N.A" or "N.S") — do NOT use empty string for these.
- For each measurement, calculate average if sample readings are visible.
- Result must be PASS only if all visible readings are inside specification.
- Result must be FAIL if any visible reading is outside specification.
- For instrument, extract the measuring tool name from the inspection sheet (e.g. Micrometer, Caliper, Scale, CMM). If not visible, use an empty string.
- Heat number match must be PASS only if inspection heat number and certificate heat number match. If the certificate has no heat number, use REVIEW.
- PO number match must be PASS if the PO is clearly visible on the inspection data sheet. If the certificate has no PO, use PASS. Only use FAIL if the certificate explicitly shows a different PO.
- final_lot_decision must be exactly "LOT ACCEPTED" or "LOT REJECTED".
- Do not invent values.
- The certificate material-property output is certificate-driven. Focus on chemical
  composition and mechanical test results. Dimensional certificate values are
  optional and must come only from an explicit dimensional test/specification
  table on the supplier certificate.
- Normalize supplier labels into the fixed JSON keys. Examples: YS/Yield/Proof
  Stress -> yield_strength; UTS/Tensile/Ultimate Tensile -> tensile_strength;
  Elong/Elongation/%EL -> elongation; HRB/HRC/Rockwell -> hardness.
- Read mechanical values by their row/column labels and units, not by table
  position alone. Do not copy length, OD, ID, wall, tolerance, or sample-count
  numbers into mechanical fields.
- Values printed as "N.A", "N/A", "N.S", "N.S.", "N.T.", "Not Tested", or
  similar are not real measured material-property values. Extract the printed
  text if it appears in a cell, but do not use it as evidence that the property
  was actually tested.
- chemical_composition is the OBSERVED row (actual measured values from the certificate). Do not extract specified limits here.
- chemical_specified is the SPECIFIED/REQUIRED row from the certificate's chemical properties table (the required limits printed on the cert, not the measured values).
- mechanical_specified is the SPECIFIED/REQUIRED row from the certificate's mechanical properties table (e.g. "490 Min", "550 Min", "25% Min"). Leave each missing mechanical specified field empty independently.
- mechanical_properties is the full visible mechanical test table from the certificate. Include one object for every mechanical column that appears on the supplier certificate, even if the observed cell says "N/A", "N.A", "N.S", or "Not Tested". Use the certificate's label as the property name, for example "Yield 0.2", "Yield 1.0", "Tensile", "Hardness", "Elongation", "Reduction". Put units such as "N/mm2", "PSI", "HRB", "%", or "%" in unit when visible. Do not include non-mechanical process tests such as Eddy Current, Flaring, Flattening, Intergranular Corrosion, Visual, or Material Identification in mechanical_properties.
- yield_strength (observed) is the labeled yield/proof value. tensile_strength (observed) is the labeled tensile/ultimate tensile value. If a table has two unlabeled strength values in the observed row, yield_strength is usually the lower value and tensile_strength is usually the higher value.
- hardness: only extract if the certificate's mechanical properties table has an explicit Hardness/Rockwell/HRB/HRC/HV/HB label. If the cert has no hardness label, leave hardness and mechanical_specified.hardness empty. Do NOT fabricate "N.A" for columns that do not exist.
- For dimensional observed values (outside_diameter, inside_diameter, wall_thickness, length, straightness): read the DIMENSIONAL MEASUREMENT TABLE column by column. Match each OBSERVED value strictly to its column header (Outer Diameter, Inner Diameter, Thickness/Wall, Length, Straightness) — do not shift values between columns. If a column's OBSERVED cell is blank or shows "N.A"/"N.S", extract that literally. The tube nominal size line at the top (e.g. "33.22 mm OD x 30.22 mm ID x 1.50 mm") is a description line, NOT a measured value — never use it. IMPORTANT: the SPECIFIED row in each dimensional column shows tolerance limits (e.g. "+0.05 / -0.00") — do NOT put these tolerance values in the OBSERVED fields. If two sample measurements appear in the OBSERVED section for one column (e.g. 30.24 in row 1 and 30.26 in row 2), format them as "30.24 / 30.26" using a "/" separator — never use "to" between them.
- dimensional_specified: extract the SPECIFIED tolerance values from each column header row (e.g. "+0.05 / -0.00", "-0.10 / +0.10"). Each column has its own unique tolerance — do not copy the same value to multiple columns. If blank, use empty string.
- Realistic steel strength: yield 100-1500 MPa / 15000-220000 PSI; tensile 200-2000 MPa / 30000-290000 PSI. Values outside these ranges are misreads — use empty string.
"""


def _build_prompt(material_spec, content_description):
    return _PROMPT_TEMPLATE.format(
        content_description=content_description,
        material_spec_text=spec_to_prompt_text(material_spec),
    )


# ── Text-based analysis (digital PDFs) ───────────────────────────────────────

def _analyze_with_text(page_texts, material_spec, client):
    """Parse a digital PDF using extracted text — no image rendering needed."""
    pages_block = "\n\n".join(
        f"=== PAGE {i + 1} ===\n{text}"
        for i, text in enumerate(page_texts)
    )

    content_description = (
        "The text content of each page has been extracted directly from the PDF "
        "(digital/computer-generated document). Read all values precisely as printed."
    )

    prompt = _build_prompt(material_spec, content_description)
    full_input = f"{prompt}\n\nExtracted PDF text:\n\n{pages_block}"

    response = client.responses.create(
        model="gpt-4.1-mini",
        input=[{"role": "user", "content": full_input}]
    )

    return parse_ai_json(response.output_text)


# ── Vision-based analysis (scanned PDFs) ─────────────────────────────────────

def _analyze_with_vision(pdf_path, material_spec, client):
    """Parse a scanned PDF by rendering pages as images and using vision AI."""
    page_images = render_pdf_pages_to_base64(pdf_path, max_pages=2)

    content_description = (
        "The pages are provided as images (scanned or image-based PDF). "
        "Read all text and tables carefully from the images."
    )

    prompt = _build_prompt(material_spec, content_description)

    content = [{"type": "input_text", "text": prompt}]
    for image_base64 in page_images:
        content.append({
            "type": "input_image",
            "image_url": f"data:image/png;base64,{image_base64}"
        })

    response = client.responses.create(
        model="gpt-4.1-mini",
        input=[{"role": "user", "content": content}]
    )

    return parse_ai_json(response.output_text)


# ── Public entry point ────────────────────────────────────────────────────────

def analyze_incoming_pdf(pdf_path, material_spec=None):
    """
    Analyze a combined incoming inspection PDF.

    Hybrid strategy:
    - If the PDF has extractable text (digital/computer-generated), pass the
      raw text to the AI — more accurate, no image rendering artifacts.
    - If the PDF is a scanned image (no text layer), fall back to vision AI.

    Returns one JSON object with: material_info, measurements, certificate, validation.
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY not found. Check your .env file.")

    client = OpenAI(api_key=api_key)

    page_texts = extract_pdf_text(pdf_path, max_pages=2)
    total_chars = sum(len(t) for t in page_texts)

    if total_chars >= _MIN_TEXT_CHARS:
        print(f"  [PDF] Digital PDF detected ({total_chars} chars) — using text extraction")
        return _analyze_with_text(page_texts, material_spec, client)
    else:
        print(f"  [PDF] Scanned PDF detected ({total_chars} chars) — using vision AI")
        return _analyze_with_vision(pdf_path, material_spec, client)


def analyze_certificate_with_ai(pdf_path):
    """Backward-compatible wrapper — returns only the certificate section."""
    return analyze_incoming_pdf(pdf_path).get("certificate", {})


def save_analysis_json(data, output_path):
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as file:
        json.dump(data, file, indent=4)


def main():
    pdf_path = "data/incomings/05-19-2026.pdf"
    output_path = "data/processed/test_incoming_analysis.json"
    data = analyze_incoming_pdf(pdf_path)
    save_analysis_json(data, output_path)
    print(json.dumps(data, indent=4))


if __name__ == "__main__":
    main()
