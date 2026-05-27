"""
Professional Incoming Inspection Report PDF generator (ReportLab).

Produces a landscape, controlled-quality inspection form suitable for
manufacturing incoming material inspection workflows.
"""

import os

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    Image,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

# Default company logo (override with material_info["logo_path"])
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DEFAULT_LOGO_PATH = os.path.join(_PROJECT_ROOT, "assets", "company_logo.png")

# ---------------------------------------------------------------------------
# Page and typography
# ---------------------------------------------------------------------------
PAGE_SIZE = landscape(letter)
PAGE_WIDTH, PAGE_HEIGHT = PAGE_SIZE

MARGIN_H = 0.42 * inch
MARGIN_V = 0.36 * inch
CONTENT_WIDTH = PAGE_WIDTH - 2 * MARGIN_H

FONT_BODY = 7.5
FONT_LABEL = 7
FONT_HEADER = 8
FONT_TITLE = 13
FONT_META = 7.5
FONT_NOTE = 6.5

GRID_WIDTH = 0.35
GRID_COLOR = colors.HexColor("#2F2F2F")
HEADER_BG = colors.HexColor("#D4D4D4")
LABEL_BG = colors.HexColor("#ECECEC")
META_BG = colors.HexColor("#F4F4F4")
ROW_ALT_BG = colors.HexColor("#FAFAFA")
LOGO_BG = colors.black
FAIL_BG = colors.HexColor("#B91C1C")
PASS_BG = colors.HexColor("#E8F5E9")
PASS_TEXT = colors.HexColor("#1B5E20")
ACCEPT_BG = colors.HexColor("#E8F5E9")
PLACEHOLDER = "—"

# Default instrument when not supplied in material_info
_DEFAULT_INSTRUMENTS = {
    "OD": "Micrometer",
    "ID": "Micrometer",
    "Wall": "Micrometer",
    "Length": "Scale",
    "Width": "Scale",
    "Height": "Scale",
}

NOTE_FOOTER = (
    "Note: Sampling size can be formed according to MIL-STD-105E."
)


def _text(value, default=""):
    """Return a display string; empty for None/NaN-like values."""
    if value is None:
        return default
    s = str(value).strip()
    if not s or s.lower() in ("nan", "none"):
        return default
    return s


def _fmt_measure(value):
    """Format numeric measurement for the observation grid."""
    if value == "" or value is None:
        return ""
    try:
        num = float(value)
        text = f"{num:.5f}".rstrip("0").rstrip(".")
        return text
    except (TypeError, ValueError):
        return str(value)


def _instrument_for(measurement, material_info):
    """Resolve instrument from material_info or sensible defaults."""
    instruments = material_info.get("instruments")
    if isinstance(instruments, dict) and measurement in instruments:
        return _text(instruments[measurement])

    keyed = material_info.get(f"instrument_{measurement}")
    if keyed:
        return _text(keyed)

    return _DEFAULT_INSTRUMENTS.get(measurement, "")


def _build_observation_rows(results_df, material_info, min_rows=None):
    """
    Group results_df by characteristic and build observation table body rows.

    Each row: [sl_no, characteristic, spec, instrument, samples 1-10, result]
    """
    if results_df is None or results_df.empty:
        grouped_order = []
        grouped = {}
    else:
        grouped = {}
        grouped_order = []
        for _, row in results_df.iterrows():
            measurement = str(row["measurement"])
            if measurement not in grouped:
                grouped[measurement] = {
                    "lsl": row["lsl"],
                    "usl": row["usl"],
                    "samples": {},
                    "result_list": [],
                }
                grouped_order.append(measurement)

            sample_id = int(row["sample"])
            grouped[measurement]["samples"][sample_id] = row["value"]
            grouped[measurement]["result_list"].append(row["result"])

    observation_rows = []
    sl_no = 1

    for measurement in grouped_order:
        data = grouped[measurement]
        spec_text = f"{_fmt_measure(data['lsl'])} to {_fmt_measure(data['usl'])}"
        overall_result = (
            "PASS" if all(r == "PASS" for r in data["result_list"]) else "FAIL"
        )

        sample_values = [
            _fmt_measure(data["samples"].get(i, "")) for i in range(1, 11)
        ]

        observation_rows.append(
            [
                sl_no,
                measurement,
                spec_text,
                _instrument_for(measurement, material_info),
                *sample_values,
                overall_result,
            ]
        )
        sl_no += 1

    # Pad lightly so the form is balanced without large empty blocks
    if min_rows is None:
        min_rows = max(len(observation_rows) + 2, 6)
    while len(observation_rows) < min_rows:
        observation_rows.append(["", "", "", ""] + [""] * 10 + [""])

    return observation_rows


def _base_table_style(font_size=FONT_BODY, grid=True):
    """Common grid and padding for form tables."""
    style = [
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("FONTSIZE", (0, 0), (-1, -1), font_size),
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]
    if grid:
        style.insert(0, ("GRID", (0, 0), (-1, -1), GRID_WIDTH, GRID_COLOR))
    return style


def _mi(material_info, key, default=""):
    """Shorthand for material_info lookup."""
    return _text(material_info.get(key, default), default)


def _po_number(material_info):
    """Purchase order number (supports common material_info keys)."""
    for key in ("po_number", "po#", "po_no", "purchase_order"):
        value = _mi(material_info, key)
        if value:
            return value
    return ""


def _cell(value, placeholder=PLACEHOLDER):
    """Format a field for display; use placeholder when empty."""
    text = _text(value)
    return text if text else placeholder


def _report_number(material_info):
    """Build a readable report number from metadata when not supplied."""
    custom = _mi(material_info, "report_no")
    if custom and custom not in ("ACT-IIR-", "ACT-IIR"):
        return custom

    part = _mi(material_info, "part_number")
    date = _mi(material_info, "inspection_date").replace("/", "")
    if part and date:
        return f"IIR-{part}-{date}"
    if part:
        return f"IIR-{part}"
    return custom or "IIR"


def _label_para(text):
    """Bold label cell content."""
    style = ParagraphStyle(
        "FieldLabel",
        fontName="Helvetica-Bold",
        fontSize=FONT_LABEL,
        alignment=TA_LEFT,
        leading=FONT_LABEL + 1,
        textColor=colors.HexColor("#1A1A1A"),
    )
    return Paragraph(text, style)


def _value_para(value, bold=False):
    """Value cell content."""
    display = _cell(value)
    style = ParagraphStyle(
        "FieldValue",
        fontName="Helvetica-Bold" if bold else "Helvetica",
        fontSize=FONT_META,
        alignment=TA_LEFT,
        leading=FONT_META + 1,
    )
    return Paragraph(display, style)


def _resolve_logo_path(material_info):
    """Return an existing logo file path, or None."""
    custom = material_info.get("logo_path")
    if custom:
        path = os.path.abspath(custom)
        if os.path.isfile(path):
            return path

    if os.path.isfile(DEFAULT_LOGO_PATH):
        return DEFAULT_LOGO_PATH

    return None


def _build_logo_image(logo_path):
    """Scale logo to fit the top-left header block (cols 0–3, rows 0–2)."""
    max_width = CONTENT_WIDTH * 3 / 12 - 6
    max_height = 0.72 * inch

    img = Image(logo_path)
    aspect = img.imageWidth / float(img.imageHeight)

    img.drawWidth = max_width
    img.drawHeight = max_width / aspect
    if img.drawHeight > max_height:
        img.drawHeight = max_height
        img.drawWidth = max_height * aspect

    return img


def _header_logo_cell(material_info):
    """Logo flowable for the header, or empty placeholder if missing."""
    logo_path = _resolve_logo_path(material_info)
    if logo_path:
        return _build_logo_image(logo_path)
    return ""


def _build_header_table(material_info):
    """
    Top header: logo, centered title, document meta, and traceability row.
    """
    col_w = CONTENT_WIDTH / 12.0
    col_widths = [col_w] * 12

    title_style = ParagraphStyle(
        "ReportTitle",
        fontName="Helvetica-Bold",
        fontSize=FONT_TITLE,
        alignment=TA_CENTER,
        leading=FONT_TITLE + 3,
        textColor=colors.HexColor("#111111"),
    )
    title_para = Paragraph("Incoming Inspection Report", title_style)

    qty = _mi(material_info, "quantity") or _mi(material_info, "lot_qty")

    header_rows = [
        [
            _header_logo_cell(material_info),
            "",
            "",
            "",
            title_para,
            "",
            "",
            "",
            _label_para("Date"),
            _value_para(_mi(material_info, "inspection_date")),
            "",
            "",
        ],
        [
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            _label_para("Report No."),
            _value_para(_report_number(material_info), bold=True),
            "",
            "",
        ],
        [
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            _label_para("Sample Size"),
            _value_para(_mi(material_info, "sample_size", "10")),
            "",
            "",
        ],
        [
            _label_para("Supplier"),
            _value_para(_mi(material_info, "supplier")),
            "",
            "",
            _label_para("Part Number"),
            _value_para(_mi(material_info, "part_number"), bold=True),
            _label_para("PO #"),
            _value_para(_po_number(material_info), bold=True),
            _label_para("Quantity"),
            _value_para(qty),
            _label_para("Heat No."),
            _value_para(_mi(material_info, "heat_number")),
        ],
    ]

    table = Table(header_rows, colWidths=col_widths)

    style = _base_table_style(FONT_LABEL) + [
        ("SPAN", (0, 0), (3, 2)),
        ("BACKGROUND", (0, 0), (3, 2), LOGO_BG),
        ("ALIGN", (0, 0), (3, 2), "CENTER"),
        ("VALIGN", (0, 0), (3, 2), "MIDDLE"),
        ("TOPPADDING", (0, 0), (3, 2), 5),
        ("BOTTOMPADDING", (0, 0), (3, 2), 5),
        ("SPAN", (4, 0), (7, 2)),
        ("SPAN", (9, 0), (11, 0)),
        ("SPAN", (9, 1), (11, 1)),
        ("SPAN", (9, 2), (11, 2)),
        ("SPAN", (1, 3), (3, 3)),
        ("BACKGROUND", (8, 0), (11, 2), META_BG),
        ("BACKGROUND", (8, 3), (11, 3), LABEL_BG),
        ("BACKGROUND", (0, 3), (0, 3), LABEL_BG),
        ("BACKGROUND", (2, 3), (2, 3), LABEL_BG),
        ("BACKGROUND", (4, 3), (4, 3), LABEL_BG),
        ("BACKGROUND", (6, 3), (6, 3), LABEL_BG),
        ("BACKGROUND", (8, 3), (8, 3), LABEL_BG),
        ("BACKGROUND", (10, 3), (10, 3), LABEL_BG),
        ("ALIGN", (4, 0), (7, 2), "CENTER"),
        ("ALIGN", (8, 0), (8, 2), "RIGHT"),
        ("VALIGN", (4, 0), (7, 2), "MIDDLE"),
        ("TOPPADDING", (4, 0), (7, 2), 6),
        ("BOTTOMPADDING", (4, 0), (7, 2), 6),
    ]

    table.setStyle(TableStyle(style))
    return table


def _build_observation_table(observation_rows):
    """Observation grid with merged header cells for sample columns."""
    header_row_1 = [
        "Sl No",
        "Characteristics",
        "Specification",
        "Instrument Used",
        "Sample observations",
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        "Remarks / Result",
    ]
    header_row_2 = [
        "",
        "",
        "",
        "",
        "1",
        "2",
        "3",
        "4",
        "5",
        "6",
        "7",
        "8",
        "9",
        "10",
        "",
    ]

    table_data = [header_row_1, header_row_2]
    for row in observation_rows:
        table_data.append(
            [
                row[0],
                row[1],
                row[2],
                row[3],
                row[4],
                row[5],
                row[6],
                row[7],
                row[8],
                row[9],
                row[10],
                row[11],
                row[12],
                row[13],
                row[14],
            ]
        )

    # Column widths scaled to CONTENT_WIDTH (15 columns)
    widths = [
        0.38 * inch,  # Sl No
        0.95 * inch,  # Characteristics
        1.05 * inch,  # Specification
        0.88 * inch,  # Instrument
    ]
    sample_w = (CONTENT_WIDTH - sum(widths) - 0.92 * inch) / 10.0
    widths.extend([sample_w] * 10)
    widths.append(0.92 * inch)  # Remarks / Result

    # Normalize to exact content width
    total = sum(widths)
    scale = CONTENT_WIDTH / total
    widths = [w * scale for w in widths]

    table = Table(table_data, colWidths=widths, repeatRows=2)

    style = _base_table_style(FONT_BODY) + [
        ("SPAN", (4, 0), (13, 0)),
        ("SPAN", (0, 0), (0, 1)),
        ("SPAN", (1, 0), (1, 1)),
        ("SPAN", (2, 0), (2, 1)),
        ("SPAN", (3, 0), (3, 1)),
        ("SPAN", (14, 0), (14, 1)),
        ("BACKGROUND", (0, 0), (-1, 1), HEADER_BG),
        ("FONTNAME", (0, 0), (-1, 1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 1), FONT_HEADER),
        ("ALIGN", (0, 0), (0, -1), "CENTER"),
        ("ALIGN", (1, 0), (1, -1), "CENTER"),
        ("ALIGN", (3, 0), (3, -1), "CENTER"),
        ("ALIGN", (4, 0), (14, -1), "CENTER"),
        ("ALIGN", (2, 2), (2, -1), "CENTER"),
        ("ROWBACKGROUNDS", (0, 2), (-1, -1), [colors.white, ROW_ALT_BG]),
    ]

    for row_index in range(2, len(table_data)):
        result_value = table_data[row_index][14]
        has_data = bool(table_data[row_index][1])

        if not has_data:
            style.append(("BACKGROUND", (0, row_index), (-1, row_index), ROW_ALT_BG))
            continue

        if result_value == "FAIL":
            style.append(("BACKGROUND", (0, row_index), (-1, row_index), FAIL_BG))
            style.append(("TEXTCOLOR", (0, row_index), (-1, row_index), colors.white))
            style.append(
                ("FONTNAME", (14, row_index), (14, row_index), "Helvetica-Bold")
            )
        elif result_value == "PASS":
            style.append(("BACKGROUND", (14, row_index), (14, row_index), PASS_BG))
            style.append(
                ("FONTNAME", (14, row_index), (14, row_index), "Helvetica-Bold")
            )
            style.append(
                ("TEXTCOLOR", (14, row_index), (14, row_index), PASS_TEXT)
            )

    table.setStyle(TableStyle(style))
    return table


def _build_summary_table(summary_df):
    """Compact Cp/Cpk summary table below observations."""
    if summary_df is None or summary_df.empty:
        return None

    data = [
        ["Characteristic", "Mean", "Cp", "Cpk"],
    ]
    for _, row in summary_df.iterrows():
        data.append([
            _text(row.get("measurement", "")),
            _text(row.get("mean", "")),
            _text(row.get("cp", "")),
            _text(row.get("cpk", "")),
        ])

    col_widths = [
        1.35 * inch,
        1.1 * inch,
        0.85 * inch,
        0.85 * inch,
    ]
    table = Table(data, colWidths=col_widths, hAlign="LEFT")
    table.setStyle(
        TableStyle(
            _base_table_style(FONT_NOTE)
            + [
                ("BACKGROUND", (0, 0), (-1, 0), HEADER_BG),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("ALIGN", (1, 0), (-1, -1), "CENTER"),
                ("ALIGN", (0, 0), (0, -1), "CENTER"),
            ]
        )
    )
    return table


def _build_remarks_table(material_info):
    data = [[_label_para("Remarks"), _value_para(_mi(material_info, "remarks"))]]
    table = Table(data, colWidths=[0.85 * inch, CONTENT_WIDTH - 0.85 * inch])
    table.setStyle(
        TableStyle(
            _base_table_style(FONT_BODY)
            + [
                ("BACKGROUND", (0, 0), (0, 0), LABEL_BG),
                ("MINROWHEIGHT", (0, 0), (-1, -1), 22),
            ]
        )
    )
    return table


def _build_conclusion_table(final_result):
    accepted = final_result == "LOT ACCEPTED"
    rejected = final_result == "LOT REJECTED"

    data = [
        [
            _label_para("Conclusion"),
            f"{'[X]' if accepted else '[ ]'}  Lot Accepted",
            f"{'[X]' if rejected else '[ ]'}  Lot Rejected",
            "[ ]  Concession Accepted",
        ]
    ]
    col_w = CONTENT_WIDTH / 4.0
    table = Table(data, colWidths=[col_w, col_w, col_w, col_w])
    style = _base_table_style(FONT_BODY) + [
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("BACKGROUND", (0, 0), (0, 0), LABEL_BG),
    ]
    if accepted:
        style.append(("BACKGROUND", (1, 0), (1, 0), ACCEPT_BG))
        style.append(("TEXTCOLOR", (1, 0), (1, 0), PASS_TEXT))
    if rejected:
        style.append(("BACKGROUND", (2, 0), (2, 0), FAIL_BG))
        style.append(("TEXTCOLOR", (2, 0), (2, 0), colors.white))
    table.setStyle(TableStyle(style))
    return table


def _build_signature_table(material_info):
    inspector = _mi(material_info, "inspector")
    approved_by = _mi(material_info, "approved_by")
    approval_date = _mi(
        material_info,
        "approval_date",
        _mi(material_info, "inspection_date"),
    )

    label_w = 0.9 * inch
    value_w = 1.2 * inch
    sig_w = (CONTENT_WIDTH - 2 * label_w - 2 * value_w) / 2.0

    data = [
        [
            _label_para("Inspected by"),
            _value_para(inspector, bold=True),
            _label_para("Signature"),
            "",
            _label_para("Approved by"),
            _value_para(approved_by),
            _label_para("Date"),
            _value_para(approval_date),
        ],
    ]

    table = Table(
        data,
        colWidths=[label_w, value_w, label_w, sig_w, label_w, value_w, label_w, value_w],
    )
    table.setStyle(
        TableStyle(
            _base_table_style(FONT_BODY)
            + [
                ("BACKGROUND", (0, 0), (0, 0), LABEL_BG),
                ("BACKGROUND", (2, 0), (2, 0), LABEL_BG),
                ("BACKGROUND", (4, 0), (4, 0), LABEL_BG),
                ("BACKGROUND", (6, 0), (6, 0), LABEL_BG),
                ("MINROWHEIGHT", (0, 0), (-1, -1), 26),
            ]
        )
    )
    return table


def create_inspection_pdf(
    output_path, material_info, results_df, summary_df, final_result
):
    """
    Build a landscape Incoming Inspection Report PDF.

    Parameters
    ----------
    output_path : str
        Destination PDF path.
    material_info : dict
        Header, traceability, remarks, and signature fields.
    results_df : pandas.DataFrame
        Columns: sample, measurement, value, lsl, usl, result.
    summary_df : pandas.DataFrame
        Optional per-characteristic statistics (mean, Cp, Cpk).
    final_result : str
        ``LOT ACCEPTED`` or ``LOT REJECTED``.
    """
    doc = SimpleDocTemplate(
        output_path,
        pagesize=PAGE_SIZE,
        leftMargin=MARGIN_H,
        rightMargin=MARGIN_H,
        topMargin=MARGIN_V,
        bottomMargin=MARGIN_V,
        title="Incoming Inspection Report",
    )

    note_style = ParagraphStyle(
        "FooterNote",
        fontName="Helvetica-Oblique",
        fontSize=FONT_NOTE,
        leading=FONT_NOTE + 2,
        alignment=TA_LEFT,
        textColor=colors.HexColor("#555555"),
    )

    story = []

    story.append(_build_header_table(material_info))
    story.append(Spacer(1, 6))

    observation_rows = _build_observation_rows(results_df, material_info)
    story.append(_build_observation_table(observation_rows))
    story.append(Spacer(1, 5))

    summary_table = _build_summary_table(summary_df)
    if summary_table is not None:
        story.append(summary_table)
        story.append(Spacer(1, 4))

    story.append(_build_remarks_table(material_info))
    story.append(Spacer(1, 4))
    story.append(_build_conclusion_table(final_result))
    story.append(Spacer(1, 4))
    story.append(_build_signature_table(material_info))
    story.append(Spacer(1, 5))
    story.append(Paragraph(NOTE_FOOTER, note_style))

    doc.build(story)
