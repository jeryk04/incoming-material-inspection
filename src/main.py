import pandas as pd

print("Incoming Material Inspection AI System")

file_path = "data/templates/A513-10200-011.xls"

try:
    df = pd.read_excel(file_path)

    print("\nExcel File Loaded Successfully")
    print("\nColumns Found:")
    print(df.columns.tolist())

    print("\nPreview of Inspection Sheet:")
    print(df.head())

except Exception as error:
    print("\nError reading Excel file:")
    print(error)
