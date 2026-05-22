import pandas as pd
import os

print("========================================")
print("INCOMING MATERIAL INSPECTION AI SYSTEM")
print("========================================")

inspection_file = "data/raw_excel/A513-10200-011(05-19-2026).xls"

if not os.path.exists(inspection_file):
    print("\nERROR: Inspection file not found.")
    exit()

df = pd.read_excel(inspection_file)

print("\nExcel file loaded successfully.")
print("\nColumns found:")
print(df.columns.tolist())

# Possible measurements used in inspection
possible_measurements = ["OD", "ID", "Wall", "Length", "Width", "Height"]

# Detect measurements that exist in the Excel
detected_measurements = []

for measurement in possible_measurements:
    if measurement in df.columns:
        min_col = measurement + "_Min"
        max_col = measurement + "_Max"

        if min_col in df.columns and max_col in df.columns:
            detected_measurements.append(measurement)

print("\nDetected measurements with tolerance limits:")
print(detected_measurements)

results = []

for measurement in detected_measurements:
    min_col = measurement + "_Min"
    max_col = measurement + "_Max"

    lsl = df[min_col].dropna().iloc[0]
    usl = df[max_col].dropna().iloc[0]

    for index, row in df.iterrows():
        value = row[measurement]

        if pd.isna(value):
            continue

        if value < lsl or value > usl:
            result = "FAIL"
        else:
            result = "PASS"

        results.append({
            "sample": index + 1,
            "measurement": measurement,
            "value": value,
            "lsl": lsl,
            "usl": usl,
            "result": result
        })

results_df = pd.DataFrame(results)

print("\n========================================")
print("TOLERANCE ANALYSIS RESULTS")
print("========================================")
print(results_df)

if len(results_df) == 0:
    final_result = "NO MEASUREMENT DATA FOUND"
elif all(results_df["result"] == "PASS"):
    final_result = "LOT ACCEPTED"
else:
    final_result = "LOT REJECTED"

print("\n========================================")
print("FINAL LOT DECISION")
print("========================================")
print(final_result)

os.makedirs("data/processed", exist_ok=True)

results_df.to_csv("data/processed/tolerance_analysis_results.csv", index=False)

print("\nResults saved to:")
print("data/processed/tolerance_analysis_results.csv")
