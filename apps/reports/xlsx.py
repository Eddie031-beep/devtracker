"""Excel (.xlsx) mínimo sin dependencias: un libro con varias hojas, encabezado en negrita.

Un .xlsx es un ZIP con XML (Office Open XML). Los textos van como `inlineStr`, así que una
celda que empieza con «=» nunca se interpreta como fórmula.
"""

import io
import zipfile
from numbers import Number
from xml.sax.saxutils import escape

CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>
{sheets}
</Types>"""

ROOT_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>"""

STYLES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<fonts count="2"><font><sz val="11"/><name val="Calibri"/></font><font><b/><sz val="11"/><name val="Calibri"/></font></fonts>
<fills count="2"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill></fills>
<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>
<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
<cellXfs count="2"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/><xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/></cellXfs>
<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>
</styleSheet>"""

NS = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
REL_NS = 'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"'
INVALID_SHEET_CHARS = str.maketrans({c: " " for c in "[]:*?/\\"})


def _column(index):
    """0 → A, 25 → Z, 26 → AA."""
    name = ""
    index += 1
    while index:
        index, rest = divmod(index - 1, 26)
        name = chr(65 + rest) + name
    return name


def _clean(text):
    # Los caracteres de control (salvo tab y saltos) no son XML válido
    return "".join(c for c in text if c in "\t\n\r" or ord(c) >= 32)


def _cell(ref, value, bold=False):
    style = ' s="1"' if bold else ""
    if value is None or value == "":
        return f'<c r="{ref}"{style}/>'
    if isinstance(value, Number) and not isinstance(value, bool):
        return f'<c r="{ref}"{style}><v>{value}</v></c>'
    text = escape(_clean(str(value)))
    return f'<c r="{ref}"{style} t="inlineStr"><is><t xml:space="preserve">{text}</t></is></c>'


def _sheet(header, rows):
    lines = []
    for r, row in enumerate([header, *rows], start=1):
        cells = "".join(_cell(f"{_column(c)}{r}", value, bold=r == 1) for c, value in enumerate(row))
        lines.append(f'<row r="{r}">{cells}</row>')
    widths = "".join(
        f'<col min="{i}" max="{i}" width="{min(max(len(str(h)) + 4, 12), 60)}" customWidth="1"/>'
        for i, h in enumerate(header, start=1)
    )
    return (
        f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<worksheet {NS}>'
        '<sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews>'
        f'<cols>{widths}</cols><sheetData>{"".join(lines)}</sheetData></worksheet>'
    )


def build_xlsx(sheets):
    """`sheets`: lista de (nombre, encabezado, filas). Devuelve los bytes del .xlsx."""
    buffer = io.BytesIO()
    names = []
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as book:
        for i, (name, header, rows) in enumerate(sheets, start=1):
            names.append(name.translate(INVALID_SHEET_CHARS)[:31] or f"Hoja {i}")
            book.writestr(f"xl/worksheets/sheet{i}.xml", _sheet(header, rows))
        overrides = "\n".join(
            f'<Override PartName="/xl/worksheets/sheet{i}.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            for i in range(1, len(names) + 1)
        )
        book.writestr("[Content_Types].xml", CONTENT_TYPES.format(sheets=overrides))
        book.writestr("_rels/.rels", ROOT_RELS)
        book.writestr("xl/styles.xml", STYLES)
        sheet_tags = "".join(
            f'<sheet name="{escape(name, {chr(34): "&quot;"})}" sheetId="{i}" r:id="rId{i}"/>'
            for i, name in enumerate(names, start=1)
        )
        book.writestr(
            "xl/workbook.xml",
            f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<workbook {NS} {REL_NS}><sheets>{sheet_tags}</sheets></workbook>',
        )
        rels = "".join(
            f'<Relationship Id="rId{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{i}.xml"/>'
            for i in range(1, len(names) + 1)
        )
        styles_id = len(names) + 1
        rels += (
            f'<Relationship Id="rId{styles_id}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
        )
        book.writestr(
            "xl/_rels/workbook.xml.rels",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
            f'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">{rels}</Relationships>',
        )
    return buffer.getvalue()
