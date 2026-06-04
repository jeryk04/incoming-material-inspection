# Incoming-material-inspection

AI-powered incoming material inspection system for quality control, measurement analysis, certificate review, anomaly detection, and digital inspection reporting.

## Material specification database

Place the Access database in:

`data/material_specs/Mathist.mdb`

The project can also use an exported copy of the Access `Material Specification`
table from:

`data/material_specs/material_specifications.csv`

For direct `.mdb`/`.accdb` reading, Windows needs the Microsoft Access ODBC
driver and Python needs `pyodbc`.

The report generator uses the item number from each incoming PDF filename to find
the matching row in this file. That internal row becomes the source of truth for:

- referenced specification
- material grade and description
- dimensional requirements such as OD, ID, and wall thickness
- mechanical properties
- chemical properties

Expected incoming PDF filename format:

`ItemNumber PO#PONumber.pdf`

Example:

`A213-30400-001 PO#96345.pdf`

When a matching item is found, the AI receives the internal requirements in its
prompt and the Python validation uses the database dimensional limits when
deciding PASS/FAIL.
