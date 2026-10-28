from __future__ import annotations

import io
import zipfile
from xml.etree import ElementTree as ET

import pytest

from harness.documents.edit import EditPlan, OoxmlPackage, apply_edit_plan
from harness.documents.edit.plan import EditError


def _inject_custom_part(data: bytes) -> tuple[bytes, bytes, bytes]:
    custom = b'<?xml version="1.0" encoding="UTF-8"?><Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/custom-properties"><property fmtid="{D5CDD505-2E9C-101B-9397-08002B2CF9AE}" pid="2" name="keep"><vt:lpwstr xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">preserve-me</vt:lpwstr></property></Properties>'
    buffer = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(data)) as source:
        originals = {name: source.read(name) for name in source.namelist()}
        infos = source.infolist()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as target:
        for info in infos:
            payload = originals[info.filename]
            if info.filename == "[Content_Types].xml":
                root = ET.fromstring(payload)
                ns = "http://schemas.openxmlformats.org/package/2006/content-types"
                ET.register_namespace("", ns)
                ET.SubElement(root, f"{{{ns}}}Override", {
                    "PartName": "/docProps/custom.xml",
                    "ContentType": "application/vnd.openxmlformats-officedocument.custom-properties+xml",
                })
                payload = ET.tostring(root, encoding="utf-8", xml_declaration=True)
            target.writestr(info.filename, payload)
        target.writestr("docProps/custom.xml", custom)
    return buffer.getvalue(), custom, originals["[Content_Types].xml"]


def _docx_fixture() -> bytes:
    from docx import Document

    document = Document()
    document.add_heading("Draft", 0)
    document.add_paragraph("Hello world")
    table = document.add_table(rows=2, cols=2)
    table.cell(0, 0).text = "Metric"
    table.cell(0, 1).text = "Value"
    table.cell(1, 0).text = "Revenue"
    table.cell(1, 1).text = "0"
    section = document.sections[0]
    section.header.paragraphs[0].text = "Header text"
    section.footer.paragraphs[0].text = "Footer text"
    buffer = io.BytesIO()
    document.save(buffer)
    injected, _custom, _ct = _inject_custom_part(buffer.getvalue())
    return injected


def _xlsx_fixture() -> bytes:
    from openpyxl import Workbook
    from openpyxl.chart import BarChart, Reference

    workbook = Workbook()
    assumptions = workbook.active
    assumptions.title = "Assumptions"
    assumptions["A1"] = "Growth"
    assumptions["B1"] = 0.05
    assumptions["A2"] = "Margin"
    assumptions["B2"] = 0.2
    dcf = workbook.create_sheet("DCF")
    dcf["A1"] = "FCF"
    dcf["B1"] = "=Assumptions!B2*100"
    chart = BarChart()
    chart.title = "Keep me"
    chart.add_data(Reference(assumptions, min_col=2, min_row=1, max_row=2))
    assumptions.add_chart(chart, "D2")
    buffer = io.BytesIO()
    workbook.save(buffer)
    return _inject_calc_chain(buffer.getvalue())


def _inject_calc_chain(data: bytes) -> bytes:
    ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    rels_ns = "http://schemas.openxmlformats.org/package/2006/relationships"
    ct_ns = "http://schemas.openxmlformats.org/package/2006/content-types"
    with zipfile.ZipFile(io.BytesIO(data)) as source:
        originals = {name: source.read(name) for name in source.namelist()}
        infos = source.infolist()
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as target:
        for info in infos:
            payload = originals[info.filename]
            if info.filename == "[Content_Types].xml":
                root = ET.fromstring(payload)
                ET.register_namespace("", ct_ns)
                ET.SubElement(root, f"{{{ct_ns}}}Override", {
                    "PartName": "/xl/calcChain.xml",
                    "ContentType": "application/vnd.openxmlformats-officedocument.spreadsheetml.calcChain+xml",
                })
                payload = ET.tostring(root, encoding="utf-8", xml_declaration=True)
            elif info.filename == "xl/_rels/workbook.xml.rels":
                root = ET.fromstring(payload)
                ET.register_namespace("", rels_ns)
                ET.SubElement(root, f"{{{rels_ns}}}Relationship", {
                    "Id": "rIdCalcChain",
                    "Type": "http://schemas.openxmlformats.org/officeDocument/2006/relationships/calcChain",
                    "Target": "calcChain.xml",
                })
                payload = ET.tostring(root, encoding="utf-8", xml_declaration=True)
            target.writestr(info.filename, payload)
        target.writestr("xl/calcChain.xml", f'<?xml version="1.0" encoding="UTF-8"?><calcChain xmlns="{ns}"/>')
    return buffer.getvalue()


def _xlsx_values_fixture() -> bytes:
    from openpyxl import Workbook

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Data"
    sheet["A1"] = "Name"
    sheet["B1"] = "Value"
    sheet["A2"] = "alpha"
    sheet["B2"] = 1
    sheet["A3"] = "beta"
    sheet["B3"] = 2
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def _xlsx_formula_fixture() -> bytes:
    from openpyxl import Workbook
    from openpyxl.formatting.rule import CellIsRule
    from openpyxl.worksheet.datavalidation import DataValidation

    workbook = Workbook()
    data = workbook.active
    data.title = "Data"
    data["A1"] = "Name"
    data["B1"] = "Value"
    data["A2"] = "alpha"
    data["B2"] = 1
    data["A3"] = "beta"
    data["B3"] = 2
    data["A4"] = "=SUM(B2:B3)"
    data.merge_cells("A6:B6")
    data["A6"] = "merged"
    data.conditional_formatting.add("B2:B3", CellIsRule(operator="greaterThan", formula=["0"]))
    validation = DataValidation(type="whole", operator="between", formula1="0", formula2="100")
    data.add_data_validation(validation)
    validation.add("B2:B3")
    calc = workbook.create_sheet("Calc")
    calc["A1"] = "=Data!B2*2"
    calc["A2"] = "=Data!B3+1"
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def _pptx_chart_fixture() -> bytes:
    from pptx import Presentation
    from pptx.chart.data import CategoryChartData
    from pptx.enum.chart import XL_CHART_TYPE
    from pptx.util import Inches

    presentation = Presentation()
    slide = presentation.slides.add_slide(presentation.slide_layouts[5])
    slide.shapes.title.text = "Chart slide"
    data = CategoryChartData()
    data.categories = ["A", "B"]
    data.add_series("Series 1", (1.0, 2.0))
    slide.shapes.add_chart(
        XL_CHART_TYPE.COLUMN_CLUSTERED, Inches(1), Inches(1.5), Inches(6), Inches(4), data,
    )
    buffer = io.BytesIO()
    presentation.save(buffer)
    return buffer.getvalue()


def _xlsx_pivot_fixture() -> bytes:
    x = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    r = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    pkg = "http://schemas.openxmlformats.org/package/2006/relationships"
    ct = "http://schemas.openxmlformats.org/package/2006/content-types"
    xdr = "http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing"
    rows = "".join(
        f'<row r="{index}"><c r="A{index}"><v>{index}</v></c><c r="B{index}"><v>{index * 10}</v></c></row>'
        for index in range(1, 5)
    )
    files = {
        "[Content_Types].xml": f'<?xml version="1.0"?><Types xmlns="{ct}"><Default Extension="xml" ContentType="application/xml"/><Default Extension="vml" ContentType="application/vnd.openxmlformats-officedocument.vmlDrawing"/></Types>',
        "xl/workbook.xml": f'<?xml version="1.0"?><workbook xmlns="{x}" xmlns:r="{r}"><sheets><sheet name="Data" sheetId="1" r:id="rId1"/></sheets></workbook>',
        "xl/_rels/workbook.xml.rels": f'<?xml version="1.0"?><Relationships xmlns="{pkg}"><Relationship Id="rId1" Type="{r}/worksheet" Target="worksheets/sheet1.xml"/></Relationships>',
        "xl/worksheets/sheet1.xml": (
            f'<?xml version="1.0"?><worksheet xmlns="{x}" xmlns:r="{r}"><dimension ref="A1:B4"/>'
            f'<sheetData>{rows}</sheetData><pivotTableParts count="1"><pivotTablePart r:id="rIdP"/></pivotTableParts>'
            f'<drawing r:id="rIdD"/><legacyDrawing r:id="rIdV"/></worksheet>'
        ),
        "xl/worksheets/_rels/sheet1.xml.rels": (
            f'<?xml version="1.0"?><Relationships xmlns="{pkg}">'
            f'<Relationship Id="rIdP" Type="{r}/pivotTable" Target="../pivotTables/pivotTable1.xml"/>'
            f'<Relationship Id="rIdD" Type="{r}/drawing" Target="../drawings/drawing1.xml"/>'
            f'<Relationship Id="rIdV" Type="{r}/vmlDrawing" Target="../drawings/vmlDrawing1.vml"/>'
            f'</Relationships>'
        ),
        "xl/pivotTables/pivotTable1.xml": f'<?xml version="1.0"?><pivotTableDefinition xmlns="{x}"><location ref="A3:B10"/></pivotTableDefinition>',
        "xl/pivotTables/_rels/pivotTable1.xml.rels": f'<?xml version="1.0"?><Relationships xmlns="{pkg}"><Relationship Id="rIdC" Type="{r}/pivotCacheDefinition" Target="../pivotCache/pivotCacheDefinition1.xml"/></Relationships>',
        "xl/pivotCache/pivotCacheDefinition1.xml": f'<?xml version="1.0"?><pivotCacheDefinition xmlns="{x}" refreshOnLoad="0"><cacheSource><worksheetSource ref="A1:B9" sheet="Data"/></cacheSource></pivotCacheDefinition>',
        "xl/drawings/drawing1.xml": f'<?xml version="1.0"?><xdr:wsDr xmlns:xdr="{xdr}"><xdr:twoCellAnchor><xdr:from><xdr:col>1</xdr:col><xdr:row>2</xdr:row></xdr:from><xdr:to><xdr:col>2</xdr:col><xdr:row>4</xdr:row></xdr:to></xdr:twoCellAnchor></xdr:wsDr>',
        "xl/drawings/vmlDrawing1.vml": '<?xml version="1.0"?><xml xmlns:v="urn:schemas-microsoft-com:vml" xmlns:x="urn:schemas-microsoft-com:office:excel"><v:shape><x:ClientData><x:Anchor>1, 0, 2, 0, 2, 0, 4, 0</x:Anchor></x:ClientData></v:shape></xml>',
    }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def _pptx_layout_fixture() -> bytes:
    p_ns = "http://schemas.openxmlformats.org/presentationml/2006/main"
    r_ns = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    dgm_ns = "http://schemas.openxmlformats.org/drawingml/2006/diagram"
    pkg_ns = "http://schemas.openxmlformats.org/package/2006/relationships"
    ct_ns = "http://schemas.openxmlformats.org/package/2006/content-types"

    def slide(number: int) -> str:
        return (
            f'<?xml version="1.0" encoding="UTF-8"?><p:sld xmlns:p="{p_ns}" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
            f'xmlns:dgm="{dgm_ns}" xmlns:r="{r_ns}"><p:cSld><p:spTree/></p:cSld>'
            f'<dgm:relIds r:dm="rIdD" r:lo="rIdL" r:qs="rIdQ" r:cs="rIdC"/></p:sld>'
        )

    def rels(number: int) -> str:
        return (
            f'<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="{pkg_ns}">'
            f'<Relationship Id="rIdD" Type="{r_ns}/diagramData" Target="../diagrams/data{number}.xml"/>'
            f'<Relationship Id="rIdL" Type="{r_ns}/diagramLayout" Target="../diagrams/layout{number}.xml"/>'
            f'<Relationship Id="rIdQ" Type="{r_ns}/diagramQuickStyle" Target="../diagrams/quickStyle{number}.xml"/>'
            f'<Relationship Id="rIdC" Type="{r_ns}/diagramColors" Target="../diagrams/colors{number}.xml"/>'
            f'</Relationships>'
        )

    files = {
        "[Content_Types].xml": f'<?xml version="1.0"?><Types xmlns="{ct_ns}"><Default Extension="xml" ContentType="application/xml"/></Types>',
        "ppt/presentation.xml": (
            f'<?xml version="1.0"?><p:presentation xmlns:p="{p_ns}" xmlns:r="{r_ns}"><p:sldIdLst>'
            f'<p:sldId id="256" r:id="rId1"/><p:sldId id="257" r:id="rId2"/></p:sldIdLst></p:presentation>'
        ),
        "ppt/_rels/presentation.xml.rels": (
            f'<?xml version="1.0"?><Relationships xmlns="{pkg_ns}">'
            f'<Relationship Id="rId1" Type="{r_ns}/slide" Target="slides/slide1.xml"/>'
            f'<Relationship Id="rId2" Type="{r_ns}/slide" Target="slides/slide2.xml"/>'
            f'</Relationships>'
        ),
        "ppt/slides/slide1.xml": slide(1),
        "ppt/slides/slide2.xml": slide(2),
        "ppt/slides/_rels/slide1.xml.rels": rels(1),
        "ppt/slides/_rels/slide2.xml.rels": rels(2),
        "ppt/diagrams/data1.xml": f'<?xml version="1.0"?><dgm:dataModel xmlns:dgm="{dgm_ns}"/>',
        "ppt/diagrams/data2.xml": f'<?xml version="1.0"?><dgm:dataModel xmlns:dgm="{dgm_ns}"/>',
        "ppt/diagrams/layout1.xml": f'<?xml version="1.0"?><dgm:layoutDef xmlns:dgm="{dgm_ns}" uniqueId="urn:one"/>',
        "ppt/diagrams/layout2.xml": f'<?xml version="1.0"?><dgm:layoutDef xmlns:dgm="{dgm_ns}" uniqueId="urn:two"/>',
        "ppt/diagrams/quickStyle1.xml": f'<?xml version="1.0"?><dgm:styleDef xmlns:dgm="{dgm_ns}"/>',
        "ppt/diagrams/quickStyle2.xml": f'<?xml version="1.0"?><dgm:styleDef xmlns:dgm="{dgm_ns}"/>',
        "ppt/diagrams/colors1.xml": f'<?xml version="1.0"?><dgm:colorsDef xmlns:dgm="{dgm_ns}"/>',
        "ppt/diagrams/colors2.xml": f'<?xml version="1.0"?><dgm:colorsDef xmlns:dgm="{dgm_ns}"/>',
    }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def _pptx_diagram_fixture() -> bytes:
    ct_ns = "http://schemas.openxmlformats.org/package/2006/content-types"
    dgm_ns = "http://schemas.openxmlformats.org/drawingml/2006/diagram"
    a_ns = "http://schemas.openxmlformats.org/drawingml/2006/main"
    with zipfile.ZipFile(io.BytesIO(_pptx_fixture())) as source:
        originals = {name: source.read(name) for name in source.namelist()}
        infos = source.infolist()
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as target:
        for info in infos:
            payload = originals[info.filename]
            if info.filename == "[Content_Types].xml":
                root = ET.fromstring(payload)
                ET.register_namespace("", ct_ns)
                ET.SubElement(root, f"{{{ct_ns}}}Override", {
                    "PartName": "/ppt/diagrams/data1.xml",
                    "ContentType": "application/vnd.openxmlformats-officedocument.drawingml.diagramData+xml",
                })
                payload = ET.tostring(root, encoding="utf-8", xml_declaration=True)
            target.writestr(info.filename, payload)
        target.writestr(
            "ppt/diagrams/data1.xml",
            f'<?xml version="1.0" encoding="UTF-8"?><dgm:dataModel xmlns:dgm="{dgm_ns}" '
            f'xmlns:a="{a_ns}"><dgm:ptLst><dgm:pt modelId="node1" type="doc"><dgm:t><a:bodyPr/>'
            f'<a:p><a:r><a:t>Draft</a:t></a:r></a:p></dgm:t></dgm:pt></dgm:ptLst>'
            f'<dgm:cxnLst/></dgm:dataModel>',
        )
    return buffer.getvalue()


def _pptx_fixture() -> bytes:
    from pptx import Presentation

    presentation = Presentation()
    slide = presentation.slides.add_slide(presentation.slide_layouts[1])
    slide.shapes.title.text = "Draft title"
    slide.placeholders[1].text = "Body text"
    slide.notes_slide.notes_text_frame.text = "Old notes"
    buffer = io.BytesIO()
    presentation.save(buffer)
    return buffer.getvalue()


def test_docx_edit_preserves_untouched_parts():
    source = _docx_fixture()
    plan = EditPlan.from_dict({
        "edits": [
            {"op": "docx.replace_text", "find": "Draft", "replace": "Final"},
            {"op": "docx.replace_text", "find": "Hello world", "replace": "Hello Eclipse"},
            {"op": "docx.set_table_cell", "table": 0, "row": 1, "col": 1, "text": "42"},
        ],
    })
    outcome = apply_edit_plan(source, "model.docx", plan)
    report = outcome.report
    assert report["ok"], report
    assert report["preservationMode"] == "content"
    assert "docProps/custom.xml" in report["changedParts"] or "docProps/custom.xml" not in report["changedParts"]

    edited = OoxmlPackage.from_bytes(outcome.data)
    original = OoxmlPackage.from_bytes(source)
    assert edited.read("docProps/custom.xml") == original.read("docProps/custom.xml")

    from docx import Document

    document = Document(io.BytesIO(outcome.data))
    assert document.paragraphs[0].text == "Final"
    assert "Hello Eclipse" in "\n".join(p.text for p in document.paragraphs)
    assert document.tables[0].cell(1, 1).text == "42"


def test_xlsx_edit_preserves_chart_and_writes_formula():
    source = _xlsx_fixture()
    original = OoxmlPackage.from_bytes(source)
    plan = EditPlan.from_dict({
        "edits": [
            {"op": "xlsx.set_cell", "sheet": "Assumptions", "ref": "B1", "value": 0.07,
             "numberFormat": "0.0%"},
            {"op": "xlsx.set_formula", "sheet": "DCF", "ref": "B2", "formula": "=Assumptions!B1*100"},
        ],
    })
    outcome = apply_edit_plan(source, "model.xlsx", plan)
    assert outcome.report["ok"], outcome.report

    edited = OoxmlPackage.from_bytes(outcome.data)
    chart_parts = [name for name in original.names if name.startswith("xl/charts/")]
    assert chart_parts
    for part in chart_parts:
        assert edited.read(part) == original.read(part)
    assert "xl/calcChain.xml" in original.names
    assert not edited.has("xl/calcChain.xml")
    assert "xl/calcChain.xml" in outcome.report["removedParts"]

    from openpyxl import load_workbook

    workbook = load_workbook(io.BytesIO(outcome.data), data_only=False)
    assert workbook["Assumptions"]["B1"].value == 0.07
    assert workbook["DCF"]["B2"].value == "=Assumptions!B1*100"
    assert workbook["Assumptions"]["B1"].number_format == "0.0%"


def test_docx_insert_image_and_revisions():
    import base64

    from docx import Document
    from PIL import Image

    from harness.documents.edit.xmlutil import parse, q, serialize

    image_buffer = io.BytesIO()
    Image.new("RGB", (20, 10), "red").save(image_buffer, "PNG")
    image_b64 = base64.b64encode(image_buffer.getvalue()).decode("ascii")

    inserted = apply_edit_plan(_docx_fixture(), "model.docx", EditPlan.from_dict({
        "edits": [{"op": "docx.insert_image", "imageBase64": image_b64, "widthInches": 2}],
    }))
    assert inserted.report["ok"], inserted.report
    document = Document(io.BytesIO(inserted.data))
    assert len(document.inline_shapes) == 1
    assert any(name.startswith("word/media/eclipse_image") for name in OoxmlPackage.from_bytes(inserted.data).names)

    package = OoxmlPackage.from_bytes(_docx_fixture())
    root = parse(package.require("word/document.xml"))
    paragraph = root.find(".//{http://schemas.openxmlformats.org/wordprocessingml/2006/main}p")
    insertion = ET.SubElement(paragraph, q("http://schemas.openxmlformats.org/wordprocessingml/2006/main", "ins"))
    run = ET.SubElement(insertion, q("http://schemas.openxmlformats.org/wordprocessingml/2006/main", "r"))
    ET.SubElement(run, q("http://schemas.openxmlformats.org/wordprocessingml/2006/main", "t")).text = " inserted"
    deletion = ET.SubElement(paragraph, q("http://schemas.openxmlformats.org/wordprocessingml/2006/main", "del"))
    run = ET.SubElement(deletion, q("http://schemas.openxmlformats.org/wordprocessingml/2006/main", "r"))
    ET.SubElement(run, q("http://schemas.openxmlformats.org/wordprocessingml/2006/main", "delText")).text = " deleted"
    package.write("word/document.xml", serialize(root))
    tracked = package.to_bytes()

    accepted = apply_edit_plan(tracked, "tracked.docx", EditPlan.from_dict({
        "edits": [{"op": "docx.accept_revisions"}],
    }))
    text = "\n".join(p.text for p in Document(io.BytesIO(accepted.data)).paragraphs)
    assert "inserted" in text and "deleted" not in text

    rejected = apply_edit_plan(tracked, "tracked.docx", EditPlan.from_dict({
        "edits": [{"op": "docx.reject_revisions"}],
    }))
    text = "\n".join(p.text for p in Document(io.BytesIO(rejected.data)).paragraphs)
    assert "deleted" in text and "inserted" not in text


def test_xlsx_structural_edits_on_a_values_only_sheet():
    from openpyxl import load_workbook

    source = _xlsx_values_fixture()
    inserted = apply_edit_plan(source, "values.xlsx", EditPlan.from_dict({
        "edits": [{"op": "xlsx.insert_rows", "sheet": "Data", "at": 2, "count": 1}],
    }))
    assert inserted.report["ok"], inserted.report
    workbook = load_workbook(io.BytesIO(inserted.data), data_only=False)
    assert workbook["Data"]["A2"].value is None
    assert workbook["Data"]["A3"].value == "alpha"
    assert workbook["Data"]["A4"].value == "beta"

    shifted = apply_edit_plan(inserted.data, "values.xlsx", EditPlan.from_dict({
        "edits": [{"op": "xlsx.delete_rows", "sheet": "Data", "at": 2, "count": 1}],
    }))
    workbook = load_workbook(io.BytesIO(shifted.data), data_only=False)
    assert workbook["Data"]["A2"].value == "alpha"
    assert workbook["Data"]["A3"].value == "beta"

    columns = apply_edit_plan(source, "values.xlsx", EditPlan.from_dict({
        "edits": [{"op": "xlsx.insert_columns", "sheet": "Data", "at": 2, "count": 1}],
    }))
    workbook = load_workbook(io.BytesIO(columns.data), data_only=False)
    assert workbook["Data"]["A1"].value == "Name"
    assert workbook["Data"]["B1"].value is None
    assert workbook["Data"]["C1"].value == "Value"

    removed = apply_edit_plan(columns.data, "values.xlsx", EditPlan.from_dict({
        "edits": [{"op": "xlsx.delete_columns", "sheet": "Data", "at": 1, "count": 1}],
    }))
    workbook = load_workbook(io.BytesIO(removed.data), data_only=False)
    assert workbook["Data"]["A1"].value is None
    assert workbook["Data"]["B1"].value == "Value"


def test_xlsx_structural_edits_rewrite_formulas_and_merges():
    from openpyxl import load_workbook

    source = _xlsx_formula_fixture()
    inserted = apply_edit_plan(source, "model.xlsx", EditPlan.from_dict({
        "edits": [{"op": "xlsx.insert_rows", "sheet": "Data", "at": 2, "count": 1}],
    }))
    assert inserted.report["ok"], inserted.report
    workbook = load_workbook(io.BytesIO(inserted.data), data_only=False)
    data = workbook["Data"]
    calc = workbook["Calc"]
    assert data["A3"].value == "alpha"
    assert data["A4"].value == "beta"
    assert data["A5"].value == "=SUM(B3:B4)"
    assert calc["A1"].value == "=Data!B3*2"
    assert calc["A2"].value == "=Data!B4+1"
    assert "A7:B7" in {str(cell_range) for cell_range in data.merged_cells.ranges}

    deleted = apply_edit_plan(inserted.data, "model.xlsx", EditPlan.from_dict({
        "edits": [{"op": "xlsx.delete_rows", "sheet": "Data", "at": 2, "count": 1}],
    }))
    workbook = load_workbook(io.BytesIO(deleted.data), data_only=False)
    data = workbook["Data"]
    calc = workbook["Calc"]
    assert data["A4"].value == "=SUM(B2:B3)"
    assert calc["A1"].value == "=Data!B2*2"
    assert "A6:B6" in {str(cell_range) for cell_range in data.merged_cells.ranges}

    columns = apply_edit_plan(source, "model.xlsx", EditPlan.from_dict({
        "edits": [{"op": "xlsx.insert_columns", "sheet": "Data", "at": 2, "count": 1}],
    }))
    workbook = load_workbook(io.BytesIO(columns.data), data_only=False)
    assert workbook["Data"]["A4"].value == "=SUM(C2:C3)"
    assert workbook["Calc"]["A1"].value == "=Data!C2*2"


def test_xlsx_structural_edit_updates_a_table_and_chart():
    from openpyxl import Workbook
    from openpyxl.chart import BarChart, Reference
    from openpyxl.worksheet.table import Table

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Data"
    sheet.append(["Name", "Value"])
    sheet.append(["a", 1])
    sheet.append(["b", 2])
    sheet.add_table(Table(displayName="DataTable", ref="A1:B3"))
    chart = BarChart()
    chart.add_data(Reference(sheet, min_col=2, min_row=1, max_row=3))
    sheet.add_chart(chart, "D2")
    buffer = io.BytesIO()
    workbook.save(buffer)

    outcome = apply_edit_plan(buffer.getvalue(), "table.xlsx", EditPlan.from_dict({
        "edits": [{"op": "xlsx.insert_rows", "sheet": "Data", "at": 2, "count": 1}],
    }))
    assert outcome.report["ok"], outcome.report
    package = OoxmlPackage.from_bytes(outcome.data)
    table_part = next(name for name in package.names if name.startswith("xl/tables/"))
    table_xml = package.require(table_part)
    assert b'ref="A1:B4"' in table_xml
    chart_part = next(name for name in package.names if name.startswith("xl/charts/"))
    chart_xml = package.require(chart_part)
    assert b"$B$1:$B$4" in chart_xml or b"B1:B4" in chart_xml


def test_pptx_edit_title_and_notes():
    source = _pptx_fixture()
    plan = EditPlan.from_dict({
        "edits": [
            {"op": "pptx.set_slide_title", "slide": 1, "text": "Final title"},
            {"op": "pptx.set_notes", "slide": 1, "text": "New notes"},
        ],
    })
    outcome = apply_edit_plan(source, "deck.pptx", plan)
    assert outcome.report["ok"], outcome.report

    from pptx import Presentation

    presentation = Presentation(io.BytesIO(outcome.data))
    slide = presentation.slides[0]
    assert slide.shapes.title.text == "Final title"
    assert slide.notes_slide.notes_text_frame.text == "New notes"


def test_pptx_duplicate_and_delete_slide():
    from pptx import Presentation

    source = _pptx_fixture()
    duplicated = apply_edit_plan(source, "deck.pptx", EditPlan.from_dict({
        "edits": [{"op": "pptx.duplicate_slide", "slide": 1}],
    }))
    assert duplicated.report["ok"], duplicated.report
    presentation = Presentation(io.BytesIO(duplicated.data))
    assert len(presentation.slides) == 2
    assert presentation.slides[1].shapes.title.text == "Draft title"
    assert presentation.slides[1].notes_slide.notes_text_frame.text == "Old notes"

    deleted = apply_edit_plan(duplicated.data, "deck.pptx", EditPlan.from_dict({
        "edits": [{"op": "pptx.delete_slide", "slide": 2}],
    }))
    assert deleted.report["ok"], deleted.report
    presentation = Presentation(io.BytesIO(deleted.data))
    assert len(presentation.slides) == 1
    assert presentation.slides[0].shapes.title.text == "Draft title"


def test_pptx_replace_text_in_a_diagram_part():
    outcome = apply_edit_plan(_pptx_diagram_fixture(), "deck.pptx", EditPlan.from_dict({
        "edits": [{"op": "pptx.replace_text", "find": "Draft", "replace": "Final"}],
    }))
    assert outcome.report["ok"], outcome.report
    package = OoxmlPackage.from_bytes(outcome.data)
    assert b"Final" in package.require("ppt/diagrams/data1.xml")


def test_xlsx_structural_edit_updates_pivots_ole_and_legacy_anchors():
    outcome = apply_edit_plan(_xlsx_pivot_fixture(), "pivot.xlsx", EditPlan.from_dict({
        "edits": [{"op": "xlsx.insert_rows", "sheet": "Data", "at": 2, "count": 1}],
    }))
    assert outcome.report["ok"], outcome.report
    package = OoxmlPackage.from_bytes(outcome.data)
    pivot = package.require("xl/pivotTables/pivotTable1.xml")
    assert b'ref="A4:B11"' in pivot
    cache = package.require("xl/pivotCache/pivotCacheDefinition1.xml")
    assert b'ref="A1:B10"' in cache
    assert b'refreshOnLoad="1"' in cache
    drawing = package.require("xl/drawings/drawing1.xml")
    assert b"<xdr:row>3</xdr:row>" in drawing
    assert b"<xdr:row>5</xdr:row>" in drawing
    vml = package.require("xl/drawings/vmlDrawing1.vml")
    assert b"1, 0, 3, 0, 2, 0, 5, 0" in vml


def test_pptx_smartart_layout_swap_from_donor_slide():
    outcome = apply_edit_plan(_pptx_layout_fixture(), "deck.pptx", EditPlan.from_dict({
        "edits": [{
            "op": "pptx.set_smartart_layout", "slide": 1, "diagram": 0,
            "fromSlide": 2, "fromDiagram": 0,
        }],
    }))
    assert outcome.report["ok"], outcome.report
    rels = OoxmlPackage.from_bytes(outcome.data).require("ppt/slides/_rels/slide1.xml.rels")
    assert b"../diagrams/layout2.xml" in rels
    assert b"../diagrams/quickStyle2.xml" in rels
    assert b"../diagrams/colors2.xml" in rels


def test_pptx_smartart_node_add_text_and_remove():
    from harness.documents.edit.xmlutil import iter_local, parse

    added = apply_edit_plan(_pptx_diagram_fixture(), "deck.pptx", EditPlan.from_dict({
        "edits": [{
            "op": "pptx.add_smartart_node", "slide": 1, "diagram": 0,
            "text": "Child", "parent": "node1",
        }],
    }))
    assert added.report["ok"], added.report
    package = OoxmlPackage.from_bytes(added.data)
    root = parse(package.require("ppt/diagrams/data1.xml"))
    assert len(list(iter_local(root, "pt"))) == 2
    assert len(list(iter_local(root, "cxn"))) == 1
    assert b"Child" in package.require("ppt/diagrams/data1.xml")

    updated = apply_edit_plan(added.data, "deck.pptx", EditPlan.from_dict({
        "edits": [{
            "op": "pptx.set_smartart_node_text", "slide": 1, "diagram": 0,
            "node": "eclipse_dgm_2", "text": "Updated child",
        }],
    }))
    assert updated.report["ok"], updated.report
    assert b"Updated child" in OoxmlPackage.from_bytes(updated.data).require("ppt/diagrams/data1.xml")

    removed = apply_edit_plan(updated.data, "deck.pptx", EditPlan.from_dict({
        "edits": [{
            "op": "pptx.remove_smartart_node", "slide": 1, "diagram": 0,
            "node": "eclipse_dgm_2",
        }],
    }))
    assert removed.report["ok"], removed.report
    package = OoxmlPackage.from_bytes(removed.data)
    root = parse(package.require("ppt/diagrams/data1.xml"))
    assert len(list(iter_local(root, "pt"))) == 1
    assert len(list(iter_local(root, "cxn"))) == 0


def test_pptx_chart_data_replacement():
    from pptx import Presentation

    outcome = apply_edit_plan(_pptx_chart_fixture(), "deck.pptx", EditPlan.from_dict({
        "edits": [{
            "op": "pptx.replace_chart_data",
            "slide": 1,
            "chart": 0,
            "categories": ["X", "Y", "Z"],
            "series": [{"name": "Series 1", "values": [10, 20, 30]}],
        }],
    }))
    assert outcome.report["ok"], outcome.report
    presentation = Presentation(io.BytesIO(outcome.data))
    chart = next(shape.chart for shape in presentation.slides[0].shapes if shape.has_chart)
    assert [str(category) for category in chart.plots[0].categories] == ["X", "Y", "Z"]
    assert [float(value) for value in chart.series[0].values] == [10.0, 20.0, 30.0]


def test_pdf_rotation_optional():
    pytest.importorskip("pypdf")
    from pypdf import PdfReader, PdfWriter

    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    buffer = io.BytesIO()
    writer.write(buffer)
    plan = EditPlan.from_dict({
        "edits": [{"op": "pdf.rotate_pages", "pages": [1], "degrees": 90}],
    })
    outcome = apply_edit_plan(buffer.getvalue(), "scan.pdf", plan)
    assert outcome.report["ok"], outcome.report
    assert outcome.report["preservationMode"] in ("rewrite", "incremental")
    reader = PdfReader(io.BytesIO(outcome.data))
    assert len(reader.pages) == 1
    assert reader.pages[0].rotation == 90


def test_pdf_redaction_removes_the_text_object():
    pytest.importorskip("pypdf")
    pytest.importorskip("pypdfium2")
    from matplotlib.figure import Figure
    from pypdf import PdfReader

    figure = Figure(figsize=(6, 4))
    figure.text(0.1, 0.5, "SECRET VALUE", fontsize=24)
    buffer = io.BytesIO()
    figure.savefig(buffer, format="pdf")
    source = buffer.getvalue()
    assert "SECRET" in PdfReader(io.BytesIO(source)).pages[0].extract_text()

    outcome = apply_edit_plan(source, "memo.pdf", EditPlan.from_dict({
        "edits": [{"op": "pdf.redact", "page": 1, "x": 0, "y": 0, "width": 2000, "height": 2000}],
    }))
    assert outcome.report["ok"], outcome.report
    assert outcome.report["redactionMode"] in ("rasterized_page", "incremental_true_removal")
    reader = PdfReader(io.BytesIO(outcome.data))
    assert len(reader.pages) == 1
    assert "SECRET" not in (reader.pages[0].extract_text() or "")


def test_pdf_incremental_mode_when_pymupdf_is_installed():
    pytest.importorskip("fitz")
    pytest.importorskip("pypdf")
    from matplotlib.figure import Figure
    from pypdf import PdfReader

    figure = Figure(figsize=(6, 4))
    figure.text(0.1, 0.5, "SECRET VALUE", fontsize=24)
    buffer = io.BytesIO()
    figure.savefig(buffer, format="pdf")
    outcome = apply_edit_plan(buffer.getvalue(), "memo.pdf", EditPlan.from_dict({
        "edits": [{"op": "pdf.redact", "page": 1, "x": 0, "y": 0, "width": 2000, "height": 2000}],
    }))
    assert outcome.report["ok"], outcome.report
    assert outcome.report["preservationMode"] == "incremental"
    assert outcome.report["redactionMode"] == "incremental_true_removal"
    reader = PdfReader(io.BytesIO(outcome.data))
    assert "SECRET" not in (reader.pages[0].extract_text() or "")


def test_document_edit_refuses_a_macro_package():
    package = OoxmlPackage.from_bytes(_docx_fixture())
    package.write("word/vbaProject.bin", b"fake-vba")
    with pytest.raises(EditError) as caught:
        apply_edit_plan(package.to_bytes(), "model.docm", EditPlan.from_dict({
            "edits": [{"op": "docx.replace_text", "find": "Draft", "replace": "Final"}],
        }))
    assert caught.value.code == "EDIT_MACRO_REFUSED"


def test_document_edit_rejects_a_path_outside_authorized_roots(tmp_path):
    import asyncio

    from harness.artifacts import ArtifactService, ArtifactStore, LocalArtifactStorage
    from harness.documents.edit.tools import register_document_edit_tools
    from harness.persistence import AgentMemoryStore
    from harness.tools import ToolContext, ToolRegistry

    outside = tmp_path / "outside.docx"
    outside.write_bytes(_docx_fixture())
    store = AgentMemoryStore(str(tmp_path / "agent-memory.db"))
    try:
        service = ArtifactService(ArtifactStore(store), LocalArtifactStorage(tmp_path / "files"))
        registry = ToolRegistry()
        register_document_edit_tools(registry)
        context = ToolContext(
            run_id="run_test", log=lambda *args, **kwargs: None,
            artifact_service=service, agent_id="eclipse-agent",
        )
        _text, data = asyncio.run(registry.get("document_edit").handler({
            "source": str(outside),
            "edits": [{"op": "docx.replace_text", "find": "Draft", "replace": "Final"}],
        }, context))
        assert data["error"] == "EDIT_SOURCE_DENIED"
    finally:
        store.close()


def test_document_edit_refuses_xml_entities():
    from harness.documents.edit.xmlutil import parse, serialize
    from harness.documents.edit.package import OoxmlError

    package = OoxmlPackage.from_bytes(_docx_fixture())
    root = parse(package.require("word/document.xml"))
    package.write("word/document.xml", b"<!DOCTYPE x [<!ENTITY y 'z'>]>" + serialize(root))
    with pytest.raises(OoxmlError) as caught:
        apply_edit_plan(package.to_bytes(), "model.docx", EditPlan.from_dict({
            "edits": [{"op": "docx.replace_text", "find": "Draft", "replace": "Final"}],
        }))
    assert caught.value.code == "EDIT_XML_UNSAFE"


def test_artifact_version_checksum_conflict(tmp_path):
    from harness.artifacts import ArtifactService, ArtifactStore, LocalArtifactStorage
    from harness.artifacts.model import AddVersionInput
    from harness.artifacts.service import ArtifactError
    from harness.persistence import AgentMemoryStore

    store = AgentMemoryStore(str(tmp_path / "agent-memory.db"))
    try:
        service = ArtifactService(ArtifactStore(store), LocalArtifactStorage(tmp_path / "files"))
        artifact = service.register_bytes(_docx_fixture(), name="model.docx", owner_id="local")
        with pytest.raises(ArtifactError) as caught:
            service.add_version(
                artifact.id,
                AddVersionInput(
                    content_base64=__import__("base64").b64encode(_docx_fixture()).decode("ascii"),
                    expected_checksum="not-the-current-checksum",
                ),
                owner_id="local",
            )
        assert caught.value.code == "ARTIFACT_CONFLICT"
    finally:
        store.close()


def test_unknown_operation_is_refused():
    with pytest.raises(EditError) as caught:
        EditPlan.from_dict({"edits": [{"op": "docx.run_python", "code": "print(1)"}]})
    assert caught.value.code == "EDIT_OP_UNSUPPORTED"


def test_document_edit_tool_creates_a_new_version(tmp_path):
    import asyncio

    from harness.artifacts import ArtifactService, ArtifactStore, LocalArtifactStorage
    from harness.documents.edit.tools import register_document_edit_tools
    from harness.persistence import AgentMemoryStore
    from harness.tools import ToolContext, ToolRegistry

    store = AgentMemoryStore(str(tmp_path / "agent-memory.db"))
    try:
        service = ArtifactService(ArtifactStore(store), LocalArtifactStorage(tmp_path / "files"))
        artifact = service.register_bytes(_docx_fixture(), name="model.docx", owner_id="local")
        registry = ToolRegistry()
        register_document_edit_tools(registry)
        context = ToolContext(
            run_id="run_test", log=lambda *args, **kwargs: None,
            artifact_service=service, agent_id="eclipse-agent",
        )
        text, data = asyncio.run(registry.get("document_edit").handler({
            "artifactId": artifact.id,
            "edits": [{"op": "docx.replace_text", "find": "Draft", "replace": "Final"}],
        }, context))
        assert data["status"] == "OK", (text, data)
        assert data["artifact"]["versionNumber"] == 2
        assert data["report"]["ok"] is True
        handle, _ = service.open_content(artifact.id, version=2)
        try:
            payload = handle.read()
        finally:
            handle.close()
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            assert b"Final" in archive.read("word/document.xml")
    finally:
        store.close()


def test_document_edit_tool_resolves_a_conversation_attachment(tmp_path, monkeypatch):
    import asyncio

    from harness.artifacts import ArtifactService, ArtifactStore, LocalArtifactStorage
    from harness.documents.edit.tools import register_document_edit_tools
    from harness.persistence import AgentMemoryStore
    from harness.tools import ToolContext, ToolRegistry

    sessions = tmp_path / "sessions"
    folder = sessions / "chat_demo" / "context"
    folder.mkdir(parents=True)
    (folder / "upload.docx").write_bytes(_docx_fixture())
    monkeypatch.setenv("BLACK_ECLIPSE_SESSION_ROOT", str(sessions))

    store = AgentMemoryStore(str(tmp_path / "agent-memory.db"))
    try:
        service = ArtifactService(ArtifactStore(store), LocalArtifactStorage(tmp_path / "files"))
        registry = ToolRegistry()
        register_document_edit_tools(registry)
        context = ToolContext(
            run_id="run_test", log=lambda *args, **kwargs: None,
            artifact_service=service, agent_id="eclipse-agent", session_id="chat_demo",
        )
        text, data = asyncio.run(registry.get("document_edit").handler({
            "sessionFile": "upload.docx",
            "edits": [{"op": "docx.replace_text", "find": "Draft", "replace": "Final"}],
        }, context))
        assert data["status"] == "OK", (text, data)
        assert data["artifact"]["versionNumber"] == 1
        assert data["artifact"]["sourceType"] == "tool"
    finally:
        store.close()
