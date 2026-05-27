import os
import json
from dotenv import load_dotenv
from pypdf import PdfReader
from openai import OpenAI


load_dotenv()


def extract_pdf_text(pdf_path):
    """
    Extract text from supplier certificate PDF.
    """
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"Certificate PDF not found: {pdf_path}")

    reader = PdfReader(pdf_path)
    text = ""

    for page in reader.pages:
        page_text = page.extract_text()

        if page_text:
            text += page_text + "\n"

    return text


def analyze_certificate_with_ai(pdf_path):
    """
    Use AI to extract structured certificate information.
    """
    api_key = os.getenv("OPENAI_API_KEY")

    if not api_key:
        raise ValueError("OPENAI_API_KEY not found. Check your .env file.")

    client = OpenAI(api_key=api_key)

    certificate_text = extract_pdf_text(pdf_path)

    prompt = f"""
You are a manufacturing quality assurance assistant.

Extract the following information from this supplier material test certificate.
Return ONLY valid JSON. Do not include explanations.

Required JSON format:
{{
  "supplier_name": "",
  "heat_number": "",
  "material_description": "",
  "material_grade": "",
  "purchase_order": "",
  "outside_diameter": "",
  "wall_thickness": "",
  "yield_strength": "",
  "tensile_strength": "",
  "elongation": "",
  "hardness": "",
  "chemical_composition": {{
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
  }},
  "certificate_status_notes": ""
}}

Supplier certificate text:
{certificate_text}
"""

    response = client.responses.create(
        model="gpt-4.1-mini",
        input=prompt
    )

    ai_text = response.output_text.strip()

    try:
        certificate_data = json.loads(ai_text)
    except json.JSONDecodeError:
        certificate_data = {
            "error": "AI response was not valid JSON",
            "raw_response": ai_text
        }

    return certificate_data


if __name__ == "__main__":
    certificate_file = "data/certificates/05-19-2026 cert A513-10200-011.pdf"

    data = analyze_certificate_with_ai(certificate_file)

    print(json.dumps(data, indent=4))