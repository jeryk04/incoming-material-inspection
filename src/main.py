import os
import pandas as pd
import numpy as np
from report_generator import create_inspection_pdf

# ==========================================================
# Incoming Material Inspection AI System
# ==========================================================

INSPECTION_FILE = "data/raw_excel/A513-10200-011(05-19-2026).xls"

print("========================================")
print("INCOMING MATERIAL INSPECTION AI SYSTEM")
print("========================================")


# ==========================================================
# Load Excel File
# ==========================================================

if not os.path.exists(INSPECTION_FILE):
    print("\nERROR: Inspection file not found.")
    exit()

df = pd.read_excel(INSPECTION_FILE, header=None)

print("\nExcel file loaded successfully.")


# ==========================================================
# Extract General Information
# ==========================================================

part_number = str(df.iloc[4, 1])
heat_number = str(df.iloc[4, 5])
supplier = str(df.iloc[4, 9])

print("\n========================================")
print("GENERAL INFORMATION")
print("========================================")

print(f"Part Number: {part_number}")
print(f"Heat Number: {heat_number}")
print(f"Supplier: {supplier}")


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
            "sample": sample_number,
            "measurement": "OD",
            "value": od_value,
            "lsl": od_min,
            "usl": od_max,
            "result": od_result
        })

    if pd.notna(wall_value):

        wall_result = "PASS"

        if wall_value < wall_min or wall_value > wall_max:
            wall_result = "FAIL"

        measurements.append({
            "sample": sample_number,
            "measurement": "Wall",
            "value": wall_value,
            "lsl": wall_min,
            "usl": wall_max,
            "result": wall_result
        })

    row += 1


# ==========================================================
# Create Results DataFrame
# ==========================================================

results_df = pd.DataFrame(measurements)

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

summary_df = pd.DataFrame(summary_rows)

print("\n========================================")
print("STATISTICAL SUMMARY")
print("========================================")
print(summary_df)

print("\n========================================")
print("MEASUREMENT RESULTS")
print("========================================")

print(results_df)


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

os.makedirs("data/processed", exist_ok=True)

results_output = "data/processed/tolerance_analysis_results.csv"

results_df.to_csv(results_output, index=False)

print("\nResults saved to:")
print(results_output)

material_info = {
    "part_number": part_number,
    "supplier": supplier,
    "heat_number": heat_number,
    "inspection_date": "05/19/2026",
    "inspector": "JC",
    "certificate_file": "data/certificates/05-19-2026 cert A513-10200-011.pdf"
}

os.makedirs("reports", exist_ok=True)

pdf_output = "reports/incoming_inspection_report_A513-10200-011.pdf"

create_inspection_pdf(
    pdf_output,
    material_info,
    results_df,
    summary_df,
    final_result
)

print("\nPDF report created:")
print(pdf_output)