import os
import re
import json

from dotenv import load_dotenv
from openai import OpenAI

from ai_certificate_analyzer import parse_ai_json

load_dotenv(dotenv_path=".env")

CACHE_PATH = "data/material_specs/spec_limits_cache.json"


def _primary_grade(grade_str):
    """
    Extract the primary grade number from ambiguous strings.

    Examples:
      "MT1020/1026"  ->  "1020"   (MT prefix stripped, first grade taken)
      "TP316L"       ->  "TP316L" (no slash, returned as-is)
      "6063"         ->  "6063"
      "1020/1026"    ->  "1020"
    """
    grade_str = grade_str.strip()
    stripped = re.sub(r"^[A-Za-z]+(?=\d)", "", grade_str)
    primary = re.split(r"[/,]", stripped)[0].strip()
    return primary if primary else grade_str


def _cache_key(reference_specification, material_grade):
    key = f"{reference_specification}_{_primary_grade(material_grade)}".upper()
    return key.replace(" ", "_").replace("/", "_")


def _load_cache():
    if os.path.exists(CACHE_PATH):
        with open(CACHE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def _save_cache(cache):
    os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
    with open(CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2)


def lookup_specification_limits(reference_specification, material_grade):
    """
    Look up chemical/mechanical limits AND required inspection sections for a
    material specification using AI with web search.

    Results are cached locally — each unique spec+grade is looked up only once.

    Returns a dict with keys:
      "chemical_properties"   -> {element: limit_string, ...}
      "mechanical_properties" -> {property: limit_string, ...}
      "required_sections"     -> list of "chemical" | "mechanical" | "dimensional"
    """
    if not reference_specification:
        return {}

    key = _cache_key(reference_specification, material_grade)
    cache = _load_cache()

    if key in cache:
        print(f"Spec limits (cached): {reference_specification} {_primary_grade(material_grade)}")
        return cache[key]

    primary = _primary_grade(material_grade)
    print(f"Looking up spec limits online: {reference_specification} {primary}")

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return {}

    client = OpenAI(api_key=api_key)

    prompt = f"""You are a materials engineering expert with access to web search.

Search the internet for the published standard and return:
1. The exact chemical composition limits
2. The exact mechanical property requirements
3. Which inspection sections are required by this standard

Specification: {reference_specification}
Grade/Alloy: {primary}

Use the exact grade number to look up the tables in the published standard.

Return ONLY a valid JSON object with this exact format. No markdown, no explanation:

{{
  "chemical_properties": {{
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
  "mechanical_properties": {{
    "yield_strength": "",
    "tensile_strength": "",
    "elongation": "",
    "hardness": ""
  }},
  "required_sections": [],
  "required_dimensional_properties": []
}}

Rules for chemical_properties and mechanical_properties:
- Use "X Max" for maximum limits (e.g. "0.25 Max")
- Use "X Min" for minimum limits (e.g. "35000 PSI Min")
- Use "X-Y" for range limits (e.g. "0.18-0.23")
- Use empty string "" if not required/applicable for this grade
- Chemical composition values are weight percent (%)
- Include units in mechanical property values (PSI, ksi, N/mm2, MPa, %, HRB, HRC, HV)
- Be precise and accurate to the actual published standard

Rules for required_sections:
- Include "chemical" if the standard requires chemical composition verification
- Include "mechanical" if the standard requires mechanical property testing (tensile, yield, elongation, hardness)
- Include "dimensional" if the standard requires dimensional inspection
- Only include what is explicitly required by the specification

Rules for required_dimensional_properties (only when "dimensional" is in required_sections):
- List which dimensional properties are explicitly required by the standard
- Use exactly these names: "OD", "ID", "Wall", "Length", "Straightness"
- Example for a tube standard like ASTM A513 or IS 3074: ["OD", "ID", "Wall", "Length", "Straightness"]
- Example for a bar or rod: ["OD"] or ["OD", "Length"]
- If dimensional is not required, use an empty list []
"""

    result = {}

    try:
        response = client.responses.create(
            model="gpt-4o",
            tools=[{"type": "web_search_preview"}],
            input=[{"role": "user", "content": prompt}]
        )
        result = parse_ai_json(response.output_text)
    except Exception as error:
        print(f"Web search unavailable ({error}), using AI training knowledge.")

    if not result.get("chemical_properties") and not result.get("mechanical_properties"):
        try:
            response = client.responses.create(
                model="gpt-4.1-mini",
                input=[{"role": "user", "content": prompt}]
            )
            result = parse_ai_json(response.output_text)
        except Exception as error:
            print(f"Spec limits lookup failed: {error}")
            return {}

    # Default: show all sections if AI did not return required_sections
    if "required_sections" not in result:
        result["required_sections"] = ["chemical", "mechanical", "dimensional"]

    if result.get("chemical_properties") or result.get("mechanical_properties"):
        cache[key] = result
        _save_cache(cache)
        print(f"Spec limits saved to cache.")

    return result
