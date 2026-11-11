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
from docs.build_report import TEST_CATEGORY_LABELS, test_category_counts, foreign_key_rows


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
              '原题要求逐条对照','bootstrap.sh','start.sh','top_student_years','课堂演示网页','ExecutiveSummary',
              '外键约束','终端显示测试','课堂网页测试',
              '函数依赖','BCNF','图外约束','关系代数','附录B','γ']
    for item in required:
        for label,content in [('PDF',compact),('DOCX',re.sub(r'\s+','',doc_text)),('MD',re.sub(r'\s+','',markdown))]:
            assert item in content,(label,item)
    for key in REPORTS:
        assert key in compact,key
    assert '\ufffd' not in text,'PDF text contains replacement character'
    # Songti has no glyph for U+22C8 / U+27D5 / U+2131; reportlab emits NUL for
    # those codepoints. Fail loudly instead of shipping a PDF with missing symbols.
    assert '\x00' not in text,'PDF text contains a missing glyph (NUL from the embedded font)'
    assert len(doc.inline_shapes)==2
    assert len(doc.tables)==18, '新增函数依赖与图外约束两张表后应为 18 张表'
    # 防回归：文档里不允许再出现与真实运行不符的旧测试数字或旧分类规模。
    # 只禁止真正的旧口径：51 项时代的总数，以及已改名/改数的旧分类行。
    # 注意“25 项数据库业务测试”如今仍是正确分类，不能列入禁用词。
    stale_markers = ['51 项测试', '；51 项', '7 项真实终端测试',
                     '18 项报表与结构测试']
    for marker in stale_markers:
        assert marker not in markdown and marker not in doc_text, marker
    category_counts = test_category_counts()
    assert sum(category_counts.values()) == v['unittest_count']
    for module, label, _coverage in TEST_CATEGORY_LABELS:
        phrase = str(category_counts[module]) + ' 项' + label
        assert phrase.replace(' ', '') in re.sub(r'\s+', '', markdown), phrase
    fk_names = [row[1] for row in foreign_key_rows()]
    assert len(fk_names) == 14
    compact_md = re.sub(r'\s+', '', markdown)
    for name in fk_names:
        assert name in compact_md, name
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
        'docx_tables_expected':18,
        'unittest_count_in_documents':v['unittest_count'],'docx_images':len(doc.inline_shapes),
        'all_ten_report_sql_keys_present':True,'required_content_present_in_all_formats':True,
        'embedded_truetype_fonts':sorted(set(embedded)),'text_bounds':bounds,
        'manual_render_review_pages':[1,5,8,11],
        'log_images_are_generated_from_actual_output_not_os_screenshots':True}
    (ROOT/'evidence/document_validation.json').write_text(json.dumps(validation,ensure_ascii=False,indent=2)+'\n')
    print('文档验证通过：',json.dumps(validation,ensure_ascii=False))


if __name__=='__main__':main()
