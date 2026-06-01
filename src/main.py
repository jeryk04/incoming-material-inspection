import os
import re
import pandas as pd

from ai_certificate_analyzer import analyze_incoming_pdf, save_analysis_json
from report_generator import create_inspection_pdf


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


def build_results_df(measurements):
    """
    Convert AI measurement summary into dataframe required by report_generator.py.
    """
    rows = []

    for measurement in measurements:
        measurement_name = clean_text(measurement.get("measurement", ""))
        average = safe_float(measurement.get("average", ""))
        lsl = safe_float(measurement.get("lsl", ""))
        usl = safe_float(measurement.get("usl", ""))

        result = clean_text(measurement.get("result", "REVIEW")).upper()

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
                "lsl": lsl if lsl is not None else 0,
                "usl": usl if usl is not None else 0,
                "result": result,
            }
        )

    return pd.DataFrame(rows)


def build_material_info(data, filename_item="", filename_po=""):
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

    return {
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
        "certificate_yield_strength": clean_text(certificate.get("yield_strength", "")),
        "certificate_tensile_strength": clean_text(certificate.get("tensile_strength", "")),
        "certificate_elongation": clean_text(certificate.get("elongation", "")),
        "certificate_hardness": clean_text(certificate.get("hardness", "")),
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
        "chemical_composition": certificate.get("chemical_composition", {}),
    }


def determine_final_result(data, results_df):
    """
    Decide final lot result.
    """
    validation = data.get("validation", {})

    # PO mismatch always rejects regardless of measurements
    po_match = clean_text(validation.get("po_number_match", "")).upper()
    if po_match == "FAIL":
        return "LOT REJECTED"

    ai_decision = clean_text(validation.get("final_lot_decision", "")).upper()

    # Normalize AI decision variants ("FAIL", "ACCEPTED", "REJECTED", etc.)
    if "ACCEPT" in ai_decision:
        return "LOT ACCEPTED"
    if "REJECT" in ai_decision or "FAIL" in ai_decision:
        return "LOT REJECTED"

    if results_df.empty:
        return "LOT REJECTED"

    if all(results_df["result"] == "PASS"):
        return "LOT ACCEPTED"

    return "LOT REJECTED"


def process_single_pdf(pdf_path):
    """
    Analyze one PDF, generate one report, and return a summary row dict.
    """
    file_name = os.path.basename(pdf_path)
    filename_item, filename_po = get_item_po_from_filename(file_name)

    print("\n========================================")
    print("PROCESSING INCOMING PDF")
    print("========================================")
    print(pdf_path)
    print(f"Item from filename: {filename_item}")
    print(f"PO from filename: {filename_po}")

    data = analyze_incoming_pdf(pdf_path)

    json_output_path = os.path.join(
        PROCESSED_FOLDER,
        f"{safe_filename(filename_item)}_PO_{safe_filename(filename_po)}_analysis.json"
    )

    save_analysis_json(data, json_output_path)

    measurements = data.get("measurements", [])
    results_df = build_results_df(measurements)

    summary_df = pd.DataFrame()

    material_info = build_material_info(
        data,
        filename_item=filename_item,
        filename_po=filename_po
    )

    final_result = determine_final_result(data, results_df)

    item_number = (
        clean_text(material_info.get("item_number", ""))
        or filename_item
    )

    po_number = (
        clean_text(material_info.get("po_number", ""))
        or filename_po
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