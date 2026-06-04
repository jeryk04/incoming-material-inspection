import os
import re

import pandas as pd


MATERIAL_SPECS_FOLDER = "data/material_specs"
ACCESS_TABLE_NAME = "Material Specification"


COLUMN_ALIASES = {
    "item_number": [
        "material specification number",
        "material specification no",
        "material specification nu",
        "material spec number",
        "item number",
        "item#",
        "part number",
    ],
    "reference_specification": [
        "referenced specification",
        "reference specification",
        "ref specification",
        "astm specification",
        "specification",
    ],
    "material_grade": [
        "material grade",
        "material grade alloy",
        "material gr",
        "grade",
        "alloy",
    ],
    "material_description": [
        "material description",
        "material descripti",
        "description",
        "material",
    ],
    "outside_diameter": [
        "outside diameter",
        "od",
    ],
    "outside_diameter_tolerance": [
        "od tol",
        "outside diameter tolerance",
        "od tolerance",
    ],
    "inside_diameter": [
        "inside diameter",
        "inside diamet",
        "id",
    ],
    "inside_diameter_tolerance": [
        "id tol",
        "inside diameter tolerance",
        "id tolerance",
    ],
    "wall_thickness": [
        "wall thickness",
        "wall thick",
        "wall",
    ],
    "wall_thickness_tolerance": [
        "wall tol",
        "wall thickness tolerance",
        "wall tolerance",
    ],
    "yield_strength": [
        "yield strength",
        "yield",
        "ys",
    ],
    "tensile_strength": [
        "tensile strength",
        "tensile",
        "uts",
    ],
    "elongation": [
        "elongation",
        "elong",
    ],
    "hardness": [
        "hardness",
        "hrb",
        "rockwell",
    ],
}


CHEMICAL_COLUMNS = {
    "C",
    "Mn",
    "P",
    "S",
    "Si",
    "Al",
    "N",
    "Cr",
    "Ni",
    "Mo",
    "Cu",
}


DIMENSION_FIELDS = {
    "OD": ("outside_diameter", "outside_diameter_tolerance"),
    "ID": ("inside_diameter", "inside_diameter_tolerance"),
    "Wall": ("wall_thickness", "wall_thickness_tolerance"),
}


def clean_text(value, default=""):
    if value is None:
        return default

    text = str(value).strip()

    if not text or text.lower() in ("nan", "none", "null"):
        return default

    return text


def normalize_key(value):
    text = clean_text(value).lower()
    text = text.replace("#", " number ")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def normalize_item_number(value):
    text = clean_text(value).upper()
    return re.sub(r"[^A-Z0-9]", "", text)


def safe_float(value):
    text = clean_text(value).replace(",", "")

    if not text:
        return None

    match = re.search(r"[-+]?\d*\.?\d+", text)

    if not match:
        return None

    return float(match.group())


def parse_tolerance(value, nominal=None):
    text = clean_text(value).replace(",", "")

    if not text:
        return None

    numbers = re.findall(r"[-+]?\d*\.?\d+", text)

    if not numbers:
        return None

    tolerance = abs(float(numbers[0]))

    if "%" in text:
        nominal_value = safe_float(nominal)

        if nominal_value is None:
            return None

        return nominal_value * (tolerance / 100.0)

    return tolerance


def limits_from_nominal_tolerance(nominal, tolerance):
    nominal_value = safe_float(nominal)
    tolerance_value = parse_tolerance(tolerance, nominal=nominal)

    if nominal_value is None:
        return None, None

    if tolerance_value is None:
        return nominal_value, nominal_value

    return nominal_value - tolerance_value, nominal_value + tolerance_value


def _existing_files():
    configured_path = os.getenv("MATERIAL_SPEC_DB_PATH")

    if configured_path and os.path.isfile(configured_path):
        return [configured_path]

    if not os.path.isdir(MATERIAL_SPECS_FOLDER):
        return []

    preferred_names = [
        "material_specifications.csv",
        "material_specification.csv",
        "material_specifications.xlsx",
        "material_specification.xlsx",
        "Material Specification.xlsx",
        "material_specifications.xls",
        "material_specification.xls",
        "material_specifications.json",
        "Mathist.mdb",
        "Mathist.accdb",
        "material_specifications.mdb",
        "material_specification.mdb",
        "material_specifications.accdb",
        "material_specification.accdb",
    ]

    paths = []

    for name in preferred_names:
        path = os.path.join(MATERIAL_SPECS_FOLDER, name)

        if os.path.isfile(path):
            paths.append(path)

    for name in os.listdir(MATERIAL_SPECS_FOLDER):
        lower_name = name.lower()

        if "template" in lower_name:
            continue

        if lower_name.endswith((".mdb", ".accdb", ".csv", ".xlsx", ".xls", ".json")):
            path = os.path.join(MATERIAL_SPECS_FOLDER, name)

            if path not in paths:
                paths.append(path)

    return paths


def _first_existing_file():
    paths = _existing_files()

    if not paths:
        return None

    return paths[0]


def _read_access_table(path):
    try:
        import pyodbc
    except ImportError as error:
        raise ImportError(
            "Reading Access .mdb/.accdb files requires pyodbc. "
            "Install project requirements and make sure the Microsoft Access "
            "ODBC driver is installed."
        ) from error

    connection_strings = [
        (
            "DRIVER={Microsoft Access Driver (*.mdb, *.accdb)};"
            f"DBQ={os.path.abspath(path)};"
        ),
        (
            "DRIVER={Microsoft Access Driver (*.mdb)};"
            f"DBQ={os.path.abspath(path)};"
        ),
    ]

    last_error = None

    for connection_string in connection_strings:
        try:
            with pyodbc.connect(connection_string) as connection:
                cursor = connection.cursor()
                table_names = [
                    row.table_name
                    for row in cursor.tables(tableType="TABLE")
                    if not row.table_name.startswith("MSys")
                ]

                if not table_names:
                    raise ValueError(f"No user tables found in Access file: {path}")

                table_name = (
                    ACCESS_TABLE_NAME
                    if ACCESS_TABLE_NAME in table_names
                    else table_names[0]
                )

                return pd.read_sql(f"SELECT * FROM [{table_name}]", connection)

        except Exception as error:
            last_error = error

    raise RuntimeError(
        "Could not open Access material specification database. "
        "Install the Microsoft Access Database Engine/ODBC driver or export "
        "the table to CSV."
    ) from last_error


def _read_spec_table(path):
    extension = os.path.splitext(path)[1].lower()

    if extension in (".mdb", ".accdb"):
        return _read_access_table(path)

    if extension == ".csv":
        return pd.read_csv(path)

    if extension in (".xlsx", ".xls"):
        return pd.read_excel(path)

    if extension == ".json":
        return pd.read_json(path)

    raise ValueError(f"Unsupported material specification file: {path}")


def _map_columns(columns):
    normalized_columns = {normalize_key(column): column for column in columns}
    mapped = {}

    for canonical, aliases in COLUMN_ALIASES.items():
        for alias in aliases:
            source = normalized_columns.get(normalize_key(alias))

            if source:
                mapped[canonical] = source
                break

    for column in columns:
        cleaned = clean_text(column)

        if cleaned in CHEMICAL_COLUMNS:
            mapped[f"chemical_{cleaned}"] = column

    return mapped


def _row_value(row, mapped_columns, key):
    source_column = mapped_columns.get(key)

    if not source_column:
        return ""

    return clean_text(row.get(source_column, ""))


def _build_dimensions(row, mapped_columns):
    dimensions = []

    for name, (nominal_key, tolerance_key) in DIMENSION_FIELDS.items():
        nominal = _row_value(row, mapped_columns, nominal_key)
        tolerance = _row_value(row, mapped_columns, tolerance_key)

        if not nominal:
            continue

        lsl, usl = limits_from_nominal_tolerance(nominal, tolerance)

        dimensions.append(
            {
                "measurement": name,
                "nominal": nominal,
                "tolerance": tolerance,
                "lsl": lsl,
                "usl": usl,
            }
        )

    return dimensions


def _build_chemical_requirements(row, mapped_columns):
    chemical = {}

    for element in CHEMICAL_COLUMNS:
        value = _row_value(row, mapped_columns, f"chemical_{element}")

        if value:
            chemical[element] = value

    return chemical


def lookup_material_spec(item_number, spec_path=None):
    """
    Find the material specification row for an item number.

    Expected export location:
    data/material_specs/material_specifications.csv
    """
    paths = [spec_path] if spec_path else _existing_files()

    if not paths:
        return None

    table = None
    path = None
    read_errors = []

    for candidate_path in paths:
        try:
            table = _read_spec_table(candidate_path)
            path = candidate_path
            break
        except Exception as error:
            read_errors.append((candidate_path, error))

    if table is None:
        if read_errors:
            first_path, first_error = read_errors[0]
            raise RuntimeError(
                f"Could not read material specification file: {first_path}"
            ) from first_error

        return None

    mapped_columns = _map_columns(table.columns)

    item_column = mapped_columns.get("item_number")

    if not item_column:
        raise ValueError(
            "Material specification file is missing an item/material specification "
            "number column."
        )

    wanted_item = normalize_item_number(item_number)

    if not wanted_item:
        return None

    for _, row in table.iterrows():
        row_item = normalize_item_number(row.get(item_column, ""))

        if row_item == wanted_item:
            return {
                "source_file": path,
                "item_number": _row_value(row, mapped_columns, "item_number"),
                "reference_specification": _row_value(
                    row,
                    mapped_columns,
                    "reference_specification",
                ),
                "material_grade": _row_value(row, mapped_columns, "material_grade"),
                "material_description": _row_value(
                    row,
                    mapped_columns,
                    "material_description",
                ),
                "dimensions": _build_dimensions(row, mapped_columns),
                "mechanical_properties": {
                    "yield_strength": _row_value(
                        row,
                        mapped_columns,
                        "yield_strength",
                    ),
                    "tensile_strength": _row_value(
                        row,
                        mapped_columns,
                        "tensile_strength",
                    ),
                    "elongation": _row_value(row, mapped_columns, "elongation"),
                    "hardness": _row_value(row, mapped_columns, "hardness"),
                },
                "chemical_properties": _build_chemical_requirements(
                    row,
                    mapped_columns,
                ),
            }

    return None


def spec_to_prompt_text(material_spec):
    if not material_spec:
        return ""

    lines = [
        "Approved material specification from internal database:",
        f"- Item number: {material_spec.get('item_number', '')}",
        f"- Reference specification: {material_spec.get('reference_specification', '')}",
        f"- Material grade: {material_spec.get('material_grade', '')}",
        f"- Material description: {material_spec.get('material_description', '')}",
    ]

    dimensions = material_spec.get("dimensions", [])

    if dimensions:
        lines.append("- Required dimensional properties:")

        for dimension in dimensions:
            lines.append(
                "  "
                f"{dimension.get('measurement', '')}: "
                f"nominal {dimension.get('nominal', '')}, "
                f"tolerance {dimension.get('tolerance', '')}, "
                f"acceptable range {dimension.get('lsl', '')} to "
                f"{dimension.get('usl', '')}"
            )

    mechanical = material_spec.get("mechanical_properties", {})
    mechanical = {key: value for key, value in mechanical.items() if value}

    if mechanical:
        lines.append(f"- Required mechanical properties: {mechanical}")

    chemical = material_spec.get("chemical_properties", {})

    if chemical:
        lines.append(f"- Required chemical properties: {chemical}")

    return "\n".join(lines)
