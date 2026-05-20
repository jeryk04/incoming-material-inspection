import pandas as pd

print("===================================")
print("INCOMING INSPECTION AI SYSTEM")
print("===================================")

# ===========================
# Load Excel Inspection Sheet
# ===========================

file_path = "data/templates/A513-10200-011.xls"

try:
    df = pd.read_excel(file_path)

    print("\nExcel file loaded successfully.")

    print("\nColumns detected in inspection sheet:")
    print(df.columns.tolist())

# ==========================
# Detect Measurement Columns
# ==========================

    possible_measurements = [
        "OD",
        "ID",
        "Wall",
        "Length",
        "Width",
        "Height"
    ]

    detected_measurements = []

    for measurement in possible_measurements:

        if measurement in df.columns:
            detected_measurements.append(measurement)


    print("\nDetected inspection measurements:")

    if len(detected_measurements) == 0:
        print("No standard measurement columns found.")

    else:
        for measurement in detected_measurements:
            print(f"- {measurement}")

# ===================================
# Preview Inspection Data
# ===================================

    print("\nInspection Sheet Preview:")
    print(df.head())

except Exception as error:

    print("\nError reading Excel inspection file:")
    print(error)
