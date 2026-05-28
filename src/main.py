import os
import json
import pandas as pd

from report_generator import create_inspection_pdf
from ai_certificate_analyzer import analyze_certificate_with_ai


# ==========================================================
# Incoming Material Inspection AI System
# ==========================================================

INSPECTION_FILE = "data/raw_excel/A513-10200-011(05-19-2026).xls"
CERTIFICATE_FILE = "data/certificates/05-19-2026 cert A513-10200-011.pdf"

PROCESSED_FOLDER = "data/processed"
REPORTS_FOLDER = "reports"

PDF_OUTPUT = "reports/incoming_inspection_report_A513-10200-011.pdf"
RESULTS_OUTPUT = "data/processed/tolerance_analysis_results.csv"
SUMMARY_OUTPUT = "data/processed/statistical_summary.csv"
CERTIFICATE_ANALYSIS_OUTPUT = "data/processed/certificate_analysis.json"


def safe_string(value):
    """Convert values safely to clean strings."""
    if value is None:
        return ""

    if pd.isna(value):
        return ""

    return str(value).strip()


def compare_values(value_1, value_2):
    """Compare two values as uppercase strings."""
    return safe_string(value_1).upper() == safe_string(value_2).upper()


def calculate_summary(results_df):
    """Calculate Mean, Min, Max, Std Dev, Cp, and Cpk."""
    summary_rows = []

    for measurement_name in results_df["measurement"].unique():
        measurement_data = results_df[results_df["measurement"] == measurement_name]

        values = measurement_data["value"]
        lsl = measurement_data["lsl"].iloc[0]
        usl = measurement_data["usl"].iloc[0]

        mean_value = values.mean()
        min_value = values.min()
        max_value = values.max()
        std_value = values.std()

        if std_value == 0 or pd.isna(std_value):
            cp = None
            cpk = None
        else:
            cp = (usl - lsl) / (6 * std_value)
            cpk = min(
                (usl - mean_value) / (3 * std_value),
                (mean_value - lsl) / (3 * std_value)
            )

        summary_rows.append({
            "measurement": measurement_name,
            "mean": round(mean_value, 6),
            "min": round(min_value, 6),
            "max": round(max_value, 6),
            "std_dev": round(std_value, 6),
            "cp": round(cp, 4) if cp is not None else "",
            "cpk": round(cpk, 4) if cpk is not None else ""
        })

    return pd.DataFrame(summary_rows)


def main():
    print("========================================")
    print("INCOMING MATERIAL INSPECTION AI SYSTEM")
    print("========================================")

    # ==========================================================
    # Load Excel File
    # ==========================================================

    if not os.path.exists(INSPECTION_FILE):
        print("\nERROR: Inspection file not found.")
        print(INSPECTION_FILE)
        return

    df = pd.read_excel(INSPECTION_FILE, header=None)

    print("\nExcel file loaded successfully.")

    # ==========================================================
    # Extract General Information from Excel
    # ==========================================================

    part_number = safe_string(df.iloc[4, 1])
    heat_number = safe_string(df.iloc[4, 5])
    supplier = safe_string(df.iloc[4, 9])

    print("\n========================================")
    print("GENERAL INFORMATION")
    print("========================================")
    print(f"Part Number: {part_number}")
    print(f"Heat Number: {heat_number}")
    print(f"Supplier: {supplier}")

    # ==========================================================
    # AI Supplier Certificate Analysis
    # ==========================================================

    print("\n========================================")
    print("AI SUPPLIER CERTIFICATE ANALYSIS")
    print("========================================")

    try:
        certificate_data = analyze_certificate_with_ai(CERTIFICATE_FILE)

        print("Certificate analyzed successfully.")

        certificate_supplier = safe_string(certificate_data.get("supplier_name", ""))
        certificate_heat_number = safe_string(certificate_data.get("heat_number", ""))
        certificate_material = safe_string(certificate_data.get("material_description", ""))
        certificate_material_grade = safe_string(certificate_data.get("material_grade", ""))
        certificate_po = safe_string(certificate_data.get("purchase_order", ""))
        certificate_od = safe_string(certificate_data.get("outside_diameter", ""))
        certificate_id = safe_string(certificate_data.get("inside_diameter", ""))
        certificate_wall = safe_string(certificate_data.get("wall_thickness", ""))
        certificate_yield = safe_string(certificate_data.get("yield_strength", ""))
        certificate_tensile = safe_string(certificate_data.get("tensile_strength", ""))
        certificate_elongation = safe_string(certificate_data.get("elongation", ""))
        certificate_hardness = safe_string(certificate_data.get("hardness", ""))
        certificate_notes = safe_string(certificate_data.get("certificate_status_notes", ""))

        chemical_composition = certificate_data.get("chemical_composition", {})

        if not isinstance(chemical_composition, dict):
            chemical_composition = {}

        heat_match = "PASS" if compare_values(certificate_heat_number, heat_number) else "REVIEW"

        print(f"Certificate Heat Number: {certificate_heat_number}")
        print(f"Excel Heat Number: {heat_number}")
        print(f"Heat Number Match: {heat_match}")

    except Exception as error:
        print("Certificate AI analysis failed.")
        print(error)

        certificate_data = {}
        certificate_supplier = ""
        certificate_heat_number = ""
        certificate_material = ""
        certificate_material_grade = ""
        certificate_po = ""
        certificate_od = ""
        certificate_id = ""
        certificate_wall = ""
        certificate_yield = ""
        certificate_tensile = ""
        certificate_elongation = ""
        certificate_hardness = ""
        certificate_notes = "AI analysis failed. Manual review required."
        chemical_composition = {}
        heat_match = "REVIEW"

    # ==========================================================
    # Extract Specifications
    # ==========================================================

    od_max = float(df.iloc[9, 1])
    od_min = float(df.iloc[11, 1])

    wall_max = float(df.iloc[9, 2])
    wall_min = float(df.iloc[11, 2])

    print("\n========================================")
    print("SPECIFICATIONS")
    print("========================================")
    print(f"OD Spec Range: {od_min} - {od_max}")
    print(f"Wall Spec Range: {wall_min} - {wall_max}")

    # ==========================================================
    # Extract Measurements
    # ==========================================================

    measurements = []

    row = 12

    while row <= 21:
        sample_number = df.iloc[row, 0]

        od_value = df.iloc[row, 1]
        wall_value = df.iloc[row, 2]

        if pd.notna(od_value):
            od_result = "PASS"

            if od_value < od_min or od_value > od_max:
                od_result = "FAIL"

            measurements.append({
                "sample": int(sample_number),
                "measurement": "OD",
                "value": float(od_value),
                "lsl": od_min,
                "usl": od_max,
                "result": od_result
            })

        if pd.notna(wall_value):
            wall_result = "PASS"

            if wall_value < wall_min or wall_value > wall_max:
                wall_result = "FAIL"

            measurements.append({
                "sample": int(sample_number),
                "measurement": "Wall",
                "value": float(wall_value),
                "lsl": wall_min,
                "usl": wall_max,
                "result": wall_result
            })

        row += 1

    results_df = pd.DataFrame(measurements)

    print("\n========================================")
    print("MEASUREMENT RESULTS")
    print("========================================")
    print(results_df)

    # ==========================================================
    # Statistical Summary
    # ==========================================================

    summary_df = calculate_summary(results_df)

    print("\n========================================")
    print("STATISTICAL SUMMARY")
    print("========================================")
    print(summary_df)

    # ==========================================================
    # Final Lot Decision
    # ==========================================================

    if all(results_df["result"] == "PASS"):
        final_result = "LOT ACCEPTED"
    else:
        final_result = "LOT REJECTED"

    print("\n========================================")
    print("FINAL LOT DECISION")
    print("========================================")
    print(final_result)

    # ==========================================================
    # Save Results
    # ==========================================================

    os.makedirs(PROCESSED_FOLDER, exist_ok=True)
    os.makedirs(REPORTS_FOLDER, exist_ok=True)

    results_df.to_csv(RESULTS_OUTPUT, index=False)
    summary_df.to_csv(SUMMARY_OUTPUT, index=False)

    with open(CERTIFICATE_ANALYSIS_OUTPUT, "w", encoding="utf-8") as file:
        json.dump(certificate_data, file, indent=4)

    print("\nResults saved to:")
    print(RESULTS_OUTPUT)

    print("\nStatistical summary saved to:")
    print(SUMMARY_OUTPUT)

    print("\nCertificate analysis saved to:")
    print(CERTIFICATE_ANALYSIS_OUTPUT)

    # ==========================================================
    # Build Material Info for PDF
    # ==========================================================

    material_info = {
        "part_number": part_number,
        "supplier": supplier,
        "po_number": certificate_po,
        "heat_number": heat_number,
        "inspection_date": "05/19/2026",
        "inspector": "JC",
        "certificate_file": CERTIFICATE_FILE,
        "report_no": "ACT-IIR-001",
        "customer_name": "",
        "sample_size": "10",
        "item_name": part_number,
        "part_rev": "",
        "lot_qty": "",
        "quantity": "",
        "material_grade": "Carbon Steel Round Tubing",
        "lot_size": "",
        "ref_no": "",
        "remarks": "",

        # AI certificate analysis fields
        "certificate_supplier": certificate_supplier,
        "certificate_heat_number": certificate_heat_number,
        "certificate_material": certificate_material,
        "certificate_material_grade": certificate_material_grade,
        "certificate_purchase_order": certificate_po,
        "certificate_outside_diameter": certificate_od,
        "certificate_inside_diameter": certificate_id,
        "certificate_wall_thickness": certificate_wall,
        "certificate_yield_strength": certificate_yield,
        "certificate_tensile_strength": certificate_tensile,
        "certificate_elongation": certificate_elongation,
        "certificate_hardness": certificate_hardness,
        "certificate_heat_match": heat_match,
        "certificate_review_status": "AI Reviewed" if certificate_data else "Manual Review Required",
        "certificate_notes": certificate_notes,
        "chemical_composition": chemical_composition
    }

    # ==========================================================
    # Generate PDF Report
    # ==========================================================

    create_inspection_pdf(
        PDF_OUTPUT,
        material_info,
        results_df,
        summary_df,
        final_result
    )

    print("\nPDF report created:")
    print(PDF_OUTPUT)


if __name__ == "__main__":
    main()