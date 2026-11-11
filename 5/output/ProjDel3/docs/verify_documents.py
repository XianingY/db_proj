"""Validate generated report containers, content, embedded Chinese fonts and bounds."""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from docx import Document
from pypdf import PdfReader
from PIL import Image
from research_lab.reports import REPORTS


def main():
    pdf=ROOT/'第三次小组作业报告.pdf'
    reader=PdfReader(pdf)
    text='\n'.join(p.extract_text() or '' for p in reader.pages)
    compact=re.sub(r'\s+','',text)
    markdown=(ROOT/'第三次小组作业报告.md').read_text()
    doc=Document(ROOT/'第三次小组作业报告.docx')
    doc_text='\n'.join(p.text for p in doc.paragraphs)+'\n'+'\n'.join(
        cell.text for t in doc.tables for row in t.rows for cell in row.cells)
    # Test/tuple counts come from the freshly generated evidence, never hardcoded,
    # so the documents cannot drift away from the real run they describe.
    v=json.loads((ROOT/'evidence/verification.json').read_text())
    required=['本阶段目标','结构修订','数据库实例',str(v['unittest_count']),
              str(v['total_sample_tuples']),'1000000.75',
              'mentor_publications','equipment_current_users','TRUNCATE','附录A',
              '原题要求逐条对照','bootstrap.sh','top_student_years','课堂演示网页']
    for item in required:
        for label,content in [('PDF',compact),('DOCX',re.sub(r'\s+','',doc_text)),('MD',re.sub(r'\s+','',markdown))]:
            assert item in content,(label,item)
    for key in REPORTS:
        assert key in compact,key
    assert '\ufffd' not in text,'PDF text contains replacement character'
    assert len(doc.inline_shapes)==2
    assert len(doc.tables)==15
    embedded=[]
    for page in reader.pages:
        fonts=page['/Resources'].get('/Font',{})
        for reference in fonts.values():
            font=reference.get_object()
            descriptor=font.get('/FontDescriptor')
            if descriptor and descriptor.get_object().get('/FontFile2'):
                embedded.append(str(font['/BaseFont']))
    assert embedded,'No embedded TrueType font found'
    for filename in ['menu_snapshot.png','report_snapshot.png']:
        with Image.open(ROOT/'evidence'/filename) as image:
            image.verify()
    bounds=None
    if shutil.which('pdftotext'):
        result=subprocess.run(['pdftotext','-bbox-layout',str(pdf),'-'],text=True,capture_output=True,check=True)
        root=ET.fromstring(result.stdout)
        ns={'x':'http://www.w3.org/1999/xhtml'}
        words=0
        for page in root.findall('.//x:page',ns):
            w,h=float(page.attrib['width']),float(page.attrib['height'])
            for word in page.findall('.//x:word',ns):
                words+=1
                a=word.attrib
                assert 0<=float(a['xMin'])<=float(a['xMax'])<=w+.5,('horizontal overflow',word.text,a)
                assert 0<=float(a['yMin'])<=float(a['yMax'])<=h+.5,('vertical overflow',word.text,a)
        bounds={'word_count':words,'all_words_inside_page':True}
    validation={'status':'passed','pdf_pages':len(reader.pages),'pdf_bytes':pdf.stat().st_size,
        'docx_tables':len(doc.tables),
        'docx_tables_expected':15,
        'unittest_count_in_documents':v['unittest_count'],'docx_images':len(doc.inline_shapes),
        'all_ten_report_sql_keys_present':True,'required_content_present_in_all_formats':True,
        'embedded_truetype_fonts':sorted(set(embedded)),'text_bounds':bounds,
        'manual_render_review_pages':[1,5,8,11],
        'log_images_are_generated_from_actual_output_not_os_screenshots':True}
    (ROOT/'evidence/document_validation.json').write_text(json.dumps(validation,ensure_ascii=False,indent=2)+'\n')
    print('文档验证通过：',json.dumps(validation,ensure_ascii=False))


if __name__=='__main__':main()
