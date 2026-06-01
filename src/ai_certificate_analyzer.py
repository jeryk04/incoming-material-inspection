import os
import json
import ast
import base64

import fitz  # PyMuPDF
from dotenv import load_dotenv
from openai import OpenAI


load_dotenv(dotenv_path=".env")


def render_pdf_pages_to_base64(pdf_path, max_pages=2, zoom=2):
    """
    Convert PDF pages into base64 PNG images.
    This allows AI to read scanned inspection sheets and certificates.
    """
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")

    document = fitz.open(pdf_path)
    images = []

    pages_to_process = min(len(document), max_pages)

    for page_index in range(pages_to_process):
        page = document[page_index]
        matrix = fitz.Matrix(zoom, zoom)
        pixmap = page.get_pixmap(matrix=matrix, alpha=False)

        image_bytes = pixmap.tobytes("png")
        image_base64 = base64.b64encode(image_bytes).decode("utf-8")

        images.append(image_base64)

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
    """
    Robustly parse AI output into a Python dictionary.
    """
    if ai_text is None:
        return {
            "error": "AI response was empty",
            "raw_response": ""
        }

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
                second_candidate = remove_markdown_fences(parsed)
                second_candidate = extract_json_object(second_candidate)
                parsed_again = json.loads(second_candidate)

                if isinstance(parsed_again, dict):
                    return parsed_again

        except Exception:
            continue

    return {
        "error": "AI response was not valid JSON",
        "raw_response": original
    }


def analyze_incoming_pdf(pdf_path):
    """
    Analyze a complete incoming material PDF.

    Expected:
    - Page 1: G&J incoming inspection data sheet
    - Page 2: supplier material certificate

    Returns one JSON object with:
    - material_info
    - measurements
    - certificate
    - validation
    """
    api_key = os.getenv("OPENAI_API_KEY")

    if not api_key:
        raise ValueError("OPENAI_API_KEY not found. Check your .env file.")

    client = OpenAI(api_key=api_key)

    page_images = render_pdf_pages_to_base64(pdf_path, max_pages=2)

    prompt = """
You are a manufacturing quality assurance assistant.

You will receive images from a combined incoming inspection PDF.

Usually:
- Page 1 is the G&J incoming inspection data sheet.
- Page 2 is the supplier material test certificate.

Analyze both pages and return ONLY one valid JSON object.
Do not include markdown.
Do not include explanations.
Do not wrap the response in ```json.

Required JSON format:

{
  "material_info": {
    "supplier": "",
    "item_number": "",
    "part_number": "",
    "po_number": "",
    "quantity": "",
    "heat_number": "",
    "inspection_date": "",
    "inspector": "",
    "sample_size": ""
  },
  "measurements": [
    {
      "measurement": "",
      "lsl": "",
      "usl": "",
      "average": "",
      "min": "",
      "max": "",
      "instrument": "",
      "result": ""
    }
  ],
  "certificate": {
    "supplier_name": "",
    "heat_number": "",
    "material_description": "",
    "material_grade": "",
    "purchase_order": "",
    "outside_diameter": "",
    "inside_diameter": "",
    "wall_thickness": "",
    "yield_strength": "",
    "tensile_strength": "",
    "elongation": "",
    "hardness": "",
    "chemical_composition": {
      "C": "",
      "Mn": "",
      "P": "",
      "S": "",
      "Si": "",
      "Al": "",
      "N": "",
      "Cr": "",
      "Ni": "",
      "Mo": "",
      "Cu": ""
    },
    "certificate_status_notes": "",
    "certificate_review_result": ""
  },
  "validation": {
    "heat_number_match": "",
    "po_number_match": "",
    "material_review": "",
    "certificate_review_status": "",
    "final_lot_decision": ""
  }
}

Important rules:
- item_number and part_number can be the same if only one is visible.
- If a value is not found, use an empty string.
- For each measurement, calculate average if sample readings are visible.
- Result must be PASS only if all visible readings are inside specification.
- Result must be FAIL if any visible reading is outside specification.
- For instrument, extract the measuring tool name from the inspection sheet (e.g. Micrometer, Caliper, Scale, CMM). If not visible, use an empty string.
- Heat number match must be PASS only if inspection heat number and certificate heat number match.
- PO number match must be PASS only if inspection PO and certificate PO match.
- final_lot_decision must be exactly "LOT ACCEPTED" or "LOT REJECTED". Use LOT ACCEPTED only if all measurements pass and certificate review is acceptable.
- Do not invent values.
"""

    content = [
        {
            "type": "input_text",
            "text": prompt
        }
    ]

    for image_base64 in page_images:
        content.append(
            {
                "type": "input_image",
                "image_url": f"data:image/png;base64,{image_base64}"
            }
        )

    response = client.responses.create(
        model="gpt-4.1-mini",
        input=[
            {
                "role": "user",
                "content": content
            }
        ]
    )

    return parse_ai_json(response.output_text)


def analyze_certificate_with_ai(pdf_path):
    """
    Backward-compatible function name.

    This now analyzes the full incoming PDF and returns only the certificate section.
    Existing code that imports analyze_certificate_with_ai will still work.
    """
    full_analysis = analyze_incoming_pdf(pdf_path)
    return full_analysis.get("certificate", {})


def save_analysis_json(data, output_path):
    """
    Save JSON analysis file.
    """
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as file:
        json.dump(data, file, indent=4)


def main():
    pdf_path = "data/incomings/05-19-2026.pdf"
    output_path = "data/processed/test_incoming_analysis.json"

    data = analyze_incoming_pdf(pdf_path)
    save_analysis_json(data, output_path)

    print("========================================")
    print("INCOMING PDF AI ANALYSIS")
    print("========================================")
    print(json.dumps(data, indent=4))

    print("\nAnalysis saved to:")
    print(output_path)


if __name__ == "__main__":
    main()