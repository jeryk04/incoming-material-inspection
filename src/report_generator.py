from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet


def create_inspection_pdf(output_path, material_info, results_df, final_result):
    doc = SimpleDocTemplate(output_path, pagesize=letter)
    styles = getSampleStyleSheet()
    story = []

    title = Paragraph("INCOMING MATERIAL INSPECTION REPORT", styles["Title"])
    story.append(title)
    story.append(Spacer(1, 20))

    info_data = [
        ["Part Number", material_info.get("part_number", "")],
        ["Supplier", material_info.get("supplier", "")],
        ["PO Number", material_info.get("po_number", "")],
        ["Heat Number", material_info.get("heat_number", "")],
        ["Inspection Date", material_info.get("inspection_date", "")],
        ["Inspector", material_info.get("inspector", "")],
        ["Certificate File", material_info.get("certificate_file", "")]
    ]

    info_table = Table(info_data, colWidths=[150, 350])
    info_table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
        ("BACKGROUND", (0, 0), (0, -1), colors.lightgrey),
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("PADDING", (0, 0), (-1, -1), 6),
    ]))

    story.append(info_table)
    story.append(Spacer(1, 20))

    story.append(Paragraph("Inspection Results", styles["Heading2"]))

    table_data = [["Sample", "Measurement", "Value", "LSL", "USL", "Result"]]

    for _, row in results_df.iterrows():
        table_data.append([
            row["sample"],
            row["measurement"],
            row["value"],
            row["lsl"],
            row["usl"],
            row["result"]
        ])

    result_table = Table(table_data)
    result_table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
        ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("PADDING", (0, 0), (-1, -1), 5),
    ]))

    story.append(result_table)
    story.append(Spacer(1, 25))

    story.append(Paragraph(f"Final Lot Decision: {final_result}", styles["Heading2"]))
    story.append(Spacer(1, 40))

    signature_data = [
        ["Inspector Signature", "____________________________"],
        ["QA Approval", "____________________________"],
        ["Date", "____________________________"]
    ]

    signature_table = Table(signature_data, colWidths=[150, 350])
    signature_table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("PADDING", (0, 0), (-1, -1), 10),
    ]))

    story.append(signature_table)

    doc.build(story)
