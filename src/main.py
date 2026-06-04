import os
import re
import pandas as pd

from ai_certificate_analyzer import analyze_incoming_pdf, save_analysis_json
from material_spec_database import lookup_material_spec
from report_generator import create_inspection_pdf
from spec_limits_lookup import lookup_specification_limits


# ==========================================================
# Batch Incoming PDF Report Generator
# ==========================================================

INCOMING_FOLDER = "data/incomings"
PROCESSED_FOLDER = "data/processed"
REPORTS_FOLDER = "reports"


def clean_text(value, default=""):
    """Convert values safely to clean strings."""
    if value is None:
        return default

    text = str(value).strip()

    if not text or text.lower() in ("nan", "none", "null"):
        return default

    return text


def safe_float(value):
    """
    Convert values like:
    '0.439'
    '0.439 INCH'
    '91,232.65 PSI'
    into a float.
    """
    if value is None:
        return None

    text = str(value).strip().replace(",", "")

    if not text:
        return None

    match = re.search(r"[-+]?\d*\.?\d+", text)

    if not match:
        return None

    return float(match.group())


def _is_spec_limit(value_str):
    """Return True when a string looks like a specification limit, not an observation."""
    if not value_str:
        return False
    low = value_str.lower()
    return "min" in low or "max" in low


ABSENT_CERT_VALUES = {
    "",
    "-",
    "n.a",
    "n/a",
    "na",
    "n.s",
    "n.s.",
    "ns",
    "n.t",
    "n.t.",
    "nt",
    "not tested",
    "not applicable",
}

CHEMICAL_KEY_MAP = {
    "c": "C",
    "carbon": "C",
    "mn": "Mn",
    "manganese": "Mn",
    "p": "P",
    "phosphorus": "P",
    "s": "S",
    "sulfur": "S",
    "sulphur": "S",
    "si": "Si",
    "silicon": "Si",
    "al": "Al",
    "aluminum": "Al",
    "aluminium": "Al",
    "n": "N",
    "nitrogen": "N",
    "cr": "Cr",
    "chromium": "Cr",
    "ni": "Ni",
    "nickel": "Ni",
    "mo": "Mo",
    "molybdenum": "Mo",
    "cu": "Cu",
    "copper": "Cu",
    "ca": "Ca",
    "calcium": "Ca",
}

MECHANICAL_KEY_MAP = {
    "yieldstrength": "yield_strength",
    "yield": "yield_strength",
    "ys": "yield_strength",
    "yields": "yield_strength",
    "tensilestrength": "tensile_strength",
    "tensile": "tensile_strength",
    "uts": "tensile_strength",
    "ultimatetensilestrength": "tensile_strength",
    "elongation": "elongation",
    "elong": "elongation",
    "elongationpercent": "elongation",
    "hardness": "hardness",
    "hrb": "hardness",
    "hrc": "hardness",
    "rockwell": "hardness",
}

FIXED_MECHANICAL_DISPLAY = {
    "yield_strength": "Yield Strength",
    "tensile_strength": "Tensile Strength",
    "elongation": "Elongation",
    "hardness": "Hardness",
}

MECHANICAL_PROCESS_TEST_TOKENS = {
    "eddycurrenttest",
    "eddycurrent",
    "visualdimensionaltest",
    "visualtest",
    "dimensionaltest",
    "flaringtest",
    "flaring",
    "flatteningtest",
    "flattening",
    "intergranularcorrosiontest",
    "intergranularcorrosion",
    "materialidentificationtest",
    "materialidentification",
}

DIMENSIONAL_KEY_MAP = {
    "outsidediameter": "outside_diameter",
    "outerdiameter": "outside_diameter",
    "od": "outside_diameter",
    "insidediameter": "inside_diameter",
    "innerdiameter": "inside_diameter",
    "id": "inside_diameter",
    "wallthickness": "wall_thickness",
    "wall": "wall_thickness",
    "thickness": "wall_thickness",
    "length": "length",
    "straightness": "straightness",
}


def _normalized_token(value):
    return re.sub(r"[^a-z0-9]+", "", clean_text(value).lower())


def _is_absent_cert_value(value):
    text = clean_text(value).lower()
    if text in ABSENT_CERT_VALUES:
        return True

    parts = [part.strip() for part in re.split(r"\s*/\s*", text) if part.strip()]
    return bool(parts) and all(part in ABSENT_CERT_VALUES for part in parts)


def _real_cert_value(value):
    text = clean_text(value)
    return "" if _is_absent_cert_value(text) else text


def _sanitize_strength(value_str):
    """
    Return empty string if a strength value is clearly unrealistic for steel
    OR looks like a specification limit rather than an observed measurement.
    Steel tensile/yield: 100-2500 N/mm2 (MPa) or 15000-360000 PSI.
    """
    if not value_str:
        return value_str
    if _is_spec_limit(value_str):
        return ""
    num = safe_float(value_str)
    if num is None:
        return value_str
    lower_val = value_str.lower()
    is_psi = "psi" in lower_val or "ksi" in lower_val
    if is_psi:
        return value_str if 10_000 <= num <= 400_000 else ""
    return value_str if 80 <= num <= 2_500 else ""


def _sanitize_mechanical_observed(value_str, property_name):
    value = _real_cert_value(value_str)
    if not value:
        return ""

    if property_name in ("yield_strength", "tensile_strength"):
        return _sanitize_strength(value)

    return _sanitize_observed(value)


def _canonical_dict(source, key_map, allowed_keys):
    canonical = {key: "" for key in allowed_keys}

    if not isinstance(source, dict):
        return canonical

    for raw_key, raw_value in source.items():
        key = key_map.get(_normalized_token(raw_key))
        if key in canonical:
            canonical[key] = clean_text(raw_value)

    return canonical


def _canonical_chemical_dict(source):
    return _canonical_dict(
        source,
        CHEMICAL_KEY_MAP,
        ["C", "Mn", "P", "S", "Si", "Al", "N", "Cr", "Ni", "Mo", "Cu", "Ca"],
    )


def _canonical_mechanical_dict(source):
    return _canonical_dict(
        source,
        MECHANICAL_KEY_MAP,
        ["yield_strength", "tensile_strength", "elongation", "hardness"],
    )


def _display_mechanical_property_name(value):
    text = clean_text(value)
    if not text:
        return ""

    normalized = _normalized_token(text)
    fixed_key = MECHANICAL_KEY_MAP.get(normalized)
    if fixed_key:
        return FIXED_MECHANICAL_DISPLAY[fixed_key]

    text = re.sub(r"\s+", " ", text)
    text = text.replace("_", " ").strip()
    return text


def _mechanical_property_allowed(name):
    token = _normalized_token(name)
    return bool(token) and token not in MECHANICAL_PROCESS_TEST_TOKENS


def _extract_mechanical_value(row, *keys):
    if not isinstance(row, dict):
        return ""

    for key in keys:
        for candidate in (key, key.upper(), key.lower(), key.title()):
            if candidate in row:
                return clean_text(row.get(candidate))

    return ""


def _normalize_dynamic_mechanical_properties(source):
    rows = []

    if isinstance(source, dict):
        source = [
            {"property": key, "observed": value}
            for key, value in source.items()
        ]

    if not isinstance(source, list):
        return rows

    seen = set()
    for row in source:
        if not isinstance(row, dict):
            continue

        name = _display_mechanical_property_name(
            _extract_mechanical_value(row, "property", "name", "measurement", "test")
        )
        if not _mechanical_property_allowed(name):
            continue

        observed = _extract_mechanical_value(row, "observed", "actual", "value", "result")
        specified = _extract_mechanical_value(row, "specified", "spec", "required", "requirement")
        unit = _extract_mechanical_value(row, "unit", "units")
        result = _extract_mechanical_value(row, "conformance", "pass_fail", "status")

        if not observed and not specified and not unit:
            continue

        key = (_normalized_token(name), observed, specified, unit)
        if key in seen:
            continue
        seen.add(key)

        rows.append(
            {
                "property": name,
                "specified": specified,
                "observed": observed,
                "unit": unit,
                "result": result,
            }
        )

    return rows


def _fallback_dynamic_mechanical_properties(certificate, cert_mech_spec):
    rows = []
    fixed_fields = [
        ("Yield Strength", "yield_strength"),
        ("Tensile Strength", "tensile_strength"),
        ("Elongation", "elongation"),
        ("Hardness", "hardness"),
    ]

    for display, key in fixed_fields:
        observed = clean_text(certificate.get(key, ""))
        specified = clean_text(cert_mech_spec.get(key, ""))

        if not _real_cert_value(observed):
            continue

        rows.append(
            {
                "property": display,
                "specified": _real_cert_value(specified),
                "observed": _real_cert_value(observed),
                "unit": "",
                "result": "",
            }
        )

    return rows


def _canonical_dimensional_dict(source):
    return _canonical_dict(
        source,
        DIMENSIONAL_KEY_MAP,
        [
            "outside_diameter",
            "inside_diameter",
            "wall_thickness",
            "length",
            "straightness",
        ],
    )


def _sanitize_specified_dict(source, canonicalizer):
    values = canonicalizer(source)
    return {key: _real_cert_value(value) for key, value in values.items()}


def _looks_like_dimensional_test_value(value, field_name):
    value = _real_cert_value(value)
    if not value:
        return False

    if field_name == "straightness":
        return True

    lower = value.lower()
    if "/" in value:
        return True

    if re.search(r"\b(pass|satisfactory|ok|acceptable|within)\b", lower):
        return True

    return False


def _sanitize_dimensional_observed(value_str, field_name, specified_value):
    value = _sanitize_observed(_real_cert_value(value_str))

    if not value:
        return ""

    if _looks_like_dimensional_test_value(value, field_name):
        return value

    return ""


def _sanitize_observed(value_str):
    """
    Return empty string when an observed value looks like a spec limit or
    dimensional tolerance (AI confusion between specified and observed rows).
    Normalizes multi-reading "X to Y" format to "X / Y".
    Strips trailing tolerance notation when AI mixed observed + spec in one field.
    """
    if not value_str:
        return value_str
    if _is_spec_limit(value_str):
        return ""
    # Pure tolerance notation "+0.05/-0.00" starting with a sign → spec, not observation
    if re.match(r"^[+\-][\d.]+\s*/\s*[+\-][\d.]", value_str.strip()):
        return ""
    # Mixed: measurement followed by tolerance, e.g. "30.24 0.00 / +0.05" or "33.22 +0.00 / +0.10"
    # Extract only the leading measurement.
    mixed = re.match(
        r"^([\d.]+)\s+[+\-]?[\d.]+\s*/\s*[+\-]?[\d.]", value_str.strip()
    )
    if mixed:
        return mixed.group(1)
    # "A to B" range: determine if spec range or two sample readings.
    # Threshold = max(0.10 mm, 0.5% of value) — filters OD/ID spec ranges but keeps
    # tight wall/length sample pairs.
    to_match = re.match(
        r"^([\d.]+)\s+to\s+([\d.]+)", value_str.strip(), re.IGNORECASE
    )
    if to_match:
        a, b = float(to_match.group(1)), float(to_match.group(2))
        threshold = max(0.10, a * 0.005)
        if abs(b - a) >= threshold:
            return ""          # wide spread → spec range, discard
        unit_suffix = value_str.strip()[to_match.end():].strip()
        return f"{to_match.group(1)} / {to_match.group(2)}{(' ' + unit_suffix) if unit_suffix else ''}"
    return value_str


def normalize_measurement_name(value):
    """Normalize measurement names for matching AI output to spec database rows."""
    text = clean_text(value).lower()
    text = re.sub(r"[^a-z0-9]+", "", text)

    aliases = {
        "od": "OD",
        "outsidediameter": "OD",
        "outside": "OD",
        "id": "ID",
        "insidediameter": "ID",
        "inside": "ID",
        "wall": "Wall",
        "wallthickness": "Wall",
        "thickness": "Wall",
    }

    return aliases.get(text, clean_text(value))


def get_spec_dimension(material_spec, measurement_name):
    """Return the matching dimensional requirement from the material spec."""
    if not material_spec:
        return None

    wanted = normalize_measurement_name(measurement_name)

    for dimension in material_spec.get("dimensions", []):
        dimension_name = normalize_measurement_name(dimension.get("measurement", ""))

        if dimension_name == wanted:
            return dimension

    return None


def safe_filename(value):
    """Make safe Windows/GitHub file names."""
    value = clean_text(value, "UNKNOWN")

    value = value.replace("/", "-")
    value = value.replace("\\", "-")
    value = value.replace(":", "-")
    value = value.replace("*", "-")
    value = value.replace("?", "-")
    value = value.replace('"', "")
    value = value.replace("<", "")
    value = value.replace(">", "")
    value = value.replace("|", "")
    value = value.replace("#", "")
    value = re.sub(r"\s+", "_", value)

    return value


def get_item_po_from_filename(file_name):
    """
    Extract Item# and PO# from PDF file name.

    Expected examples:
    A513-10200-011 PO#96345.pdf
    A269-31600-043 PO#96388.pdf
    """
    base_name = os.path.splitext(file_name)[0]

    pattern = r"(?P<item>[A-Za-z0-9\-]+)\s*PO#?\s*(?P<po>[A-Za-z0-9\-]+)"
    match = re.search(pattern, base_name, re.IGNORECASE)

    if not match:
        return "", ""

    item_number = match.group("item").strip()
    po_number = match.group("po").strip()

    return item_number, po_number


def extract_po_from_page1(pdf_path):
    """
    Read PO number directly from page 1 text (digital PDFs).
    Returns empty string if not found or if the PDF is scanned/image-based.
    """
    try:
        from ai_certificate_analyzer import extract_pdf_text
        texts = extract_pdf_text(pdf_path, max_pages=1)
        page1 = texts[0] if texts else ""
        match = re.search(r"PO\s*#?\s*(\d[\d\-]+)", page1, re.IGNORECASE)
        if match:
            return match.group(1).strip()
    except Exception:
        pass
    return ""


def get_all_incoming_pdfs():
    """
    Get all valid incoming PDFs from data/incomings.
    """
    if not os.path.exists(INCOMING_FOLDER):
        os.makedirs(INCOMING_FOLDER, exist_ok=True)

    pdf_files = []

    for file_name in os.listdir(INCOMING_FOLDER):
        if not file_name.lower().endswith(".pdf"):
            continue

        item_number, po_number = get_item_po_from_filename(file_name)

        if item_number and po_number:
            full_path = os.path.join(INCOMING_FOLDER, file_name)
            pdf_files.append(full_path)
        else:
            print(f"Skipping invalid file name: {file_name}")
            print("Expected format: ItemNumber PO#PONumber.pdf")

    pdf_files.sort()

    return pdf_files


def build_results_df(measurements, material_spec=None):
    """
    Convert AI measurement summary into dataframe required by report_generator.py.
    """
    rows = []

    for measurement in measurements:
        measurement_name = clean_text(measurement.get("measurement", ""))
        average = safe_float(measurement.get("average", ""))
        minimum = safe_float(measurement.get("min", ""))
        maximum = safe_float(measurement.get("max", ""))
        lsl = safe_float(measurement.get("lsl", ""))
        usl = safe_float(measurement.get("usl", ""))
        instrument = clean_text(measurement.get("instrument", ""))

        spec_dimension = get_spec_dimension(material_spec, measurement_name)

        if spec_dimension:
            spec_lsl = spec_dimension.get("lsl")
            spec_usl = spec_dimension.get("usl")

            if spec_lsl is not None:
                lsl = spec_lsl

            if spec_usl is not None:
                usl = spec_usl

        result = clean_text(measurement.get("result", "REVIEW")).upper()

        # Only compute PASS/FAIL when we have real, non-zero spec limits.
        # lsl=0 / usl=0 means no spec was found — keep AI result or REVIEW.
        has_real_limits = (
            lsl is not None and usl is not None
            and not (lsl == 0 and usl == 0)
        )

        if has_real_limits:
            values_to_check = [
                value
                for value in (minimum, maximum, average)
                if value is not None
            ]

            if values_to_check:
                result = (
                    "PASS"
                    if all(lsl <= value <= usl for value in values_to_check)
                    else "FAIL"
                )

        if result not in ("PASS", "FAIL"):
            result = "REVIEW"

        if not measurement_name:
            continue

        if average is None:
            continue

        rows.append(
            {
                "sample": 1,
                "measurement": measurement_name,
                "value": average,
                "min": minimum if minimum is not None else average,
                "max": maximum if maximum is not None else average,
                "lsl": lsl if lsl is not None else 0,
                "usl": usl if usl is not None else 0,
                "instrument": instrument,
                "result": result,
            }
        )

    return pd.DataFrame(rows)


def build_material_info(data, filename_item="", filename_po="", material_spec=None):
    """
    Convert AI analysis JSON into material_info used by report_generator.py.
    """
    material = data.get("material_info", {})
    certificate = data.get("certificate", {})
    validation = data.get("validation", {})

    item_number = (
        clean_text(material.get("item_number", ""))
        or clean_text(material.get("part_number", ""))
        or filename_item
    )

    part_number = (
        clean_text(material.get("part_number", ""))
        or item_number
    )

    # Priority: AI material_info → certificate → filename fallback
    po_number = (
        clean_text(material.get("po_number", ""))
        or clean_text(certificate.get("purchase_order", ""))
        or filename_po
    )

    heat_number = clean_text(material.get("heat_number", ""))
    certificate_heat_number = clean_text(certificate.get("heat_number", ""))

    heat_match = clean_text(validation.get("heat_number_match", ""))

    if not heat_match:
        heat_match = (
            "PASS"
            if heat_number
            and certificate_heat_number
            and heat_number.upper() == certificate_heat_number.upper()
            else "REVIEW"
        )

    cert_chem_obs = _sanitize_specified_dict(
        certificate.get("chemical_composition", {}),
        _canonical_chemical_dict,
    )
    cert_chem_spec = _sanitize_specified_dict(
        certificate.get("chemical_specified", {}),
        _canonical_chemical_dict,
    )
    cert_mech_spec = _sanitize_specified_dict(
        certificate.get("mechanical_specified", {}),
        _canonical_mechanical_dict,
    )
    cert_mech_properties = _normalize_dynamic_mechanical_properties(
        certificate.get("mechanical_properties", [])
    )
    if not cert_mech_properties:
        cert_mech_properties = _fallback_dynamic_mechanical_properties(
            certificate,
            cert_mech_spec,
        )
    cert_dim_spec = _sanitize_specified_dict(
        certificate.get("dimensional_specified", {}),
        _canonical_dimensional_dict,
    )
    cert_dim_obs = {
        key: _sanitize_dimensional_observed(
            certificate.get(key, ""),
            key,
            cert_dim_spec.get(key, ""),
        )
        for key in (
            "outside_diameter",
            "inside_diameter",
            "wall_thickness",
            "length",
            "straightness",
        )
    }

    material_info = {
        "supplier": clean_text(material.get("supplier", "")),
        "item_number": item_number,
        "part_number": part_number,
        "po_number": po_number,
        "quantity": clean_text(material.get("quantity", "")),
        "heat_number": heat_number,
        "inspection_date": clean_text(material.get("inspection_date", "")),
        "inspector": clean_text(material.get("inspector", "")),
        "sample_size": clean_text(material.get("sample_size", "10")),
        "report_no": "",
        "logo_path": "assets/company_logo.png",

        "certificate_supplier": clean_text(certificate.get("supplier_name", "")),
        "certificate_heat_number": certificate_heat_number,
        "certificate_material": clean_text(certificate.get("material_description", "")),
        "certificate_material_grade": clean_text(certificate.get("material_grade", "")),
        "certificate_purchase_order": clean_text(certificate.get("purchase_order", "")),
        "certificate_yield_strength": _sanitize_mechanical_observed(
            certificate.get("yield_strength", ""),
            "yield_strength",
        ),
        "certificate_tensile_strength": _sanitize_mechanical_observed(
            certificate.get("tensile_strength", ""),
            "tensile_strength",
        ),
        "certificate_elongation": _sanitize_mechanical_observed(
            certificate.get("elongation", ""),
            "elongation",
        ),
        "certificate_hardness": _sanitize_mechanical_observed(
            certificate.get("hardness", ""),
            "hardness",
        ),
        "certificate_heat_match": heat_match,
        "certificate_review_status": clean_text(
            validation.get("certificate_review_status", "AI Reviewed")
        ),
        "certificate_review_result": clean_text(
            certificate.get("certificate_review_result", "")
            or validation.get("material_review", "")
            or "AI Reviewed"
        ),
        "certificate_notes": clean_text(certificate.get("certificate_status_notes", "")),
        "certificate_outside_diameter": cert_dim_obs["outside_diameter"],
        "certificate_inside_diameter": cert_dim_obs["inside_diameter"],
        "certificate_wall_thickness": cert_dim_obs["wall_thickness"],
        "certificate_length": cert_dim_obs["length"],
        "certificate_straightness": cert_dim_obs["straightness"],
        "chemical_composition": cert_chem_obs,
        "certificate_dimensional_specified": cert_dim_spec,
        "certificate_mechanical_properties": cert_mech_properties,
    }

    # Raw cert specified values — stored separately so the report can use them
    # for column visibility and row values without DB values interfering.
    material_info["cert_chemical_specified"]   = cert_chem_spec
    material_info["cert_mechanical_specified"]  = cert_mech_spec
    material_info["cert_mechanical_properties"] = cert_mech_properties

    if material_spec:
        # Start with DB values then overlay cert specified values where present.
        db_chem  = material_spec.get("chemical_properties", {})
        db_mech  = material_spec.get("mechanical_properties", {})

        merged_chem = {**db_chem}
        if cert_chem_spec and any(v for v in cert_chem_spec.values() if clean_text(v)):
            for k, v in cert_chem_spec.items():
                if clean_text(v):
                    merged_chem[k] = v

        merged_mech = {**db_mech}
        if cert_mech_spec and any(v for v in cert_mech_spec.values() if clean_text(v)):
            for k, v in cert_mech_spec.items():
                if clean_text(v):
                    merged_mech[k] = v

        material_info.update(
            {
                "spec_found": "YES",
                "reference_specification": clean_text(
                    material_spec.get("reference_specification", "")
                ),
                "required_material_grade": clean_text(
                    material_spec.get("material_grade", "")
                ),
                "required_material_description": clean_text(
                    material_spec.get("material_description", "")
                ),
                "required_chemical_properties": merged_chem,
                "required_mechanical_properties": merged_mech,
                "required_sections": material_spec.get(
                    "required_sections",
                    ["chemical", "mechanical", "dimensional"],
                ),
                "required_dimensional_properties": material_spec.get(
                    "required_dimensional_properties",
                    ["OD", "ID", "Wall"],
                ),
                "required_dimensional_limits": material_spec.get(
                    "dimensions", []
                ),
            }
        )

    else:
        material_info["spec_found"] = "NO"
        # No DB spec — use cert specified values directly if available.
        if cert_chem_spec and any(v for v in cert_chem_spec.values() if clean_text(v)):
            material_info["required_chemical_properties"] = cert_chem_spec
        if cert_mech_spec and any(v for v in cert_mech_spec.values() if clean_text(v)):
            material_info["required_mechanical_properties"] = cert_mech_spec

    return material_info


def determine_final_result(data, results_df):
    """
    Decide final lot result.
    Only FAIL measurements from the inspection sheet trigger rejection.
    Empty cert fields (N.A, not tested) are not treated as failures.
    """
    if not results_df.empty and any(results_df["result"] == "FAIL"):
        return "LOT REJECTED"

    return "LOT ACCEPTED"


def sync_validation_with_report_result(data, results_df, final_result):
    """Store the Python-calculated report decision back into the saved analysis."""
    validation = data.setdefault("validation", {})
    validation["final_lot_decision"] = final_result

    if results_df.empty:
        validation["measurements_result"] = "REVIEW"
        validation["rejection_reason"] = ""
        return

    failed_rows = results_df[results_df["result"] == "FAIL"]

    if failed_rows.empty:
        validation["measurements_result"] = "PASS"
        validation["rejection_reason"] = ""
        return

    validation["measurements_result"] = "FAIL"
    reasons = []
    for _, row in failed_rows.iterrows():
        reasons.append(
            f"{row['measurement']} min/max {row['min']} to {row['max']} "
            f"outside {row['lsl']} to {row['usl']}"
        )

    validation["rejection_reason"] = "; ".join(reasons)


def process_single_pdf(pdf_path):
    """
    Analyze one PDF, generate one report, and return a summary row dict.
    """
    file_name = os.path.basename(pdf_path)
    filename_item, filename_po = get_item_po_from_filename(file_name)

    # Resolve PO: page 1 text first, filename as fallback
    page1_po = extract_po_from_page1(pdf_path)
    resolved_po = page1_po or filename_po

    print("\n========================================")
    print("PROCESSING INCOMING PDF")
    print("========================================")
    print(pdf_path)
    print(f"Item from filename:  {filename_item}")
    print(f"PO from filename:    {filename_po}")
    print(f"PO from page 1:      {page1_po or '(not found)'}")
    print(f"PO resolved:         {resolved_po}")

    try:
        material_spec = lookup_material_spec(filename_item)
    except Exception as error:
        material_spec = None
        print("Material specification database could not be read.")
        print(error)

    if material_spec:
        print("Material specification found:")
        print(material_spec.get("reference_specification", ""))
    else:
        print("Material specification not found in data/material_specs.")

    json_output_path = os.path.join(
        PROCESSED_FOLDER,
        f"{safe_filename(filename_item)}_PO_{safe_filename(resolved_po)}_analysis.json"
    )

    # Use cached JSON if it exists to avoid unnecessary API calls.
    if os.path.exists(json_output_path):
        import json as _json
        with open(json_output_path, encoding="utf-8") as _f:
            data = _json.load(_f)
        print(f"  [CACHE] Loaded existing analysis: {json_output_path}")
    else:
        data = analyze_incoming_pdf(pdf_path, material_spec=material_spec)

    if material_spec:
        has_chem = any(material_spec.get("chemical_properties", {}).values())
        has_mech = any(material_spec.get("mechanical_properties", {}).values())

        if not has_chem or not has_mech:
            ref_spec = clean_text(material_spec.get("reference_specification", ""))
            # Prefer the specific grade written on the certificate (e.g. "1020"),
            # but only if it contains digits — generic strings like "Carbon Steel"
            # are material descriptions, not grade numbers, and produce wrong lookups.
            cert_grade = clean_text(data.get("certificate", {}).get("material_grade", ""))
            db_grade = clean_text(material_spec.get("material_grade", ""))
            grade = cert_grade if re.search(r"\d", cert_grade) else db_grade

            online_limits = lookup_specification_limits(ref_spec, grade)

            if not has_chem and online_limits.get("chemical_properties"):
                material_spec["chemical_properties"] = online_limits["chemical_properties"]

            if not has_mech and online_limits.get("mechanical_properties"):
                material_spec["mechanical_properties"] = online_limits["mechanical_properties"]

            if online_limits.get("required_sections"):
                material_spec["required_sections"] = online_limits["required_sections"]

            if online_limits.get("required_dimensional_properties"):
                material_spec["required_dimensional_properties"] = online_limits["required_dimensional_properties"]

    data["material_specification"] = material_spec or {}

    measurements = data.get("measurements", [])
    results_df = build_results_df(measurements, material_spec=material_spec)

    summary_df = pd.DataFrame()

    material_info = build_material_info(
        data,
        filename_item=filename_item,
        filename_po=resolved_po,
        material_spec=material_spec,
    )

    final_result = determine_final_result(data, results_df)
    sync_validation_with_report_result(data, results_df, final_result)
    save_analysis_json(data, json_output_path)

    item_number = (
        clean_text(material_info.get("item_number", ""))
        or filename_item
    )

    po_number = (
        clean_text(material_info.get("po_number", ""))
        or resolved_po
    )

    output_filename = f"{safe_filename(item_number)}_PO_{safe_filename(po_number)}.pdf"
    report_output_path = os.path.join(REPORTS_FOLDER, output_filename)

    create_inspection_pdf(
        report_output_path,
        material_info,
        results_df,
        summary_df,
        final_result
    )

    print("AI analysis saved:")
    print(json_output_path)

    print("Report created:")
    print(report_output_path)

    validation = data.get("validation", {})

    summary_row = {
        "item_number": item_number,
        "po_number": po_number,
        "supplier": clean_text(material_info.get("supplier", "")),
        "inspection_date": clean_text(material_info.get("inspection_date", "")),
        "inspector": clean_text(material_info.get("inspector", "")),
        "heat_number": clean_text(material_info.get("heat_number", "")),
        "quantity": clean_text(material_info.get("quantity", "")),
        "heat_match": clean_text(validation.get("heat_number_match", "")),
        "po_match": clean_text(validation.get("po_number_match", "")),
        "measurements_result": (
            "PASS" if not results_df.empty and all(results_df["result"] == "PASS") else "FAIL"
        ),
        "certificate_result": clean_text(
            data.get("certificate", {}).get("certificate_review_result", "")
        ),
        "final_result": final_result,
    }

    for _, row in results_df.drop_duplicates("measurement").iterrows():
        key = f"{row['measurement']}_avg"
        summary_row[key] = row["value"]

    return summary_row


def save_batch_summary(summary_rows, output_path):
    """Write all lot summary rows to a CSV."""
    if not summary_rows:
        return

    df = pd.DataFrame(summary_rows)
    df.to_csv(output_path, index=False)

    print("\nBatch summary saved:")
    print(output_path)


def main():
    print("========================================")
    print("BATCH INCOMING MATERIAL REPORT GENERATOR")
    print("========================================")

    os.makedirs(PROCESSED_FOLDER, exist_ok=True)
    os.makedirs(REPORTS_FOLDER, exist_ok=True)

    incoming_pdfs = get_all_incoming_pdfs()

    if not incoming_pdfs:
        print("\nERROR: No valid incoming PDFs found.")
        print("Put PDFs in data/incomings with this format:")
        print("ItemNumber PO#PONumber.pdf")
        print("\nExample:")
        print("A513-10200-011 PO#96345.pdf")
        return

    print("\nPDF files found:")
    for pdf_path in incoming_pdfs:
        print("-", os.path.basename(pdf_path))

    total_success = 0
    total_failed = 0
    summary_rows = []

    for pdf_path in incoming_pdfs:
        try:
            summary_row = process_single_pdf(pdf_path)
            summary_rows.append(summary_row)
            total_success += 1

        except Exception as error:
            total_failed += 1
            print("\nERROR processing PDF:")
            print(pdf_path)
            print(error)

    if summary_rows:
        save_batch_summary(
            summary_rows,
            os.path.join(PROCESSED_FOLDER, "batch_summary.csv")
        )

    print("\n========================================")
    print("BATCH COMPLETE")
    print("========================================")
    print(f"Reports created: {total_success}")
    print(f"Failed files: {total_failed}")
    print("========================================")


if __name__ == "__main__":
    main()   
