"""Render every final PDF page and record structural checks for visual QA."""
import json
import subprocess
from pathlib import Path

import pdfplumber
from PIL import Image,ImageOps,ImageDraw

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"tmp/pdfs/liquidity_on_trial"
POPPLER=Path("C:/Users/patri/.cache/codex-runtimes/codex-primary-runtime/dependencies/native/poppler/Library/bin/pdftoppm.exe")
report={}
for stem in ("liquidity_on_trial","connector_calculus_critique"):
    pdf=ROOT/"output/pdf"/f"{stem}.pdf"
    subprocess.run([str(POPPLER),"-r","90","-png",str(pdf),str(OUT/stem)],check=True,capture_output=True)
    pages=[]
    with pdfplumber.open(pdf) as doc:
        for index,page in enumerate(doc.pages,1):
            text=page.extract_text() or ""
            outside=[c for c in page.chars if c["x0"]<0 or c["x1"]>612.1 or c["top"]<0 or c["bottom"]>792.1]
            assert not outside,(stem,index,"text outside page")
            assert "[Missing figure" not in text and "\u25a0" not in text
            pages.append({"page":index,"characters":len(text),"text_outside_page":len(outside),
                          "first_body_line":text.splitlines()[1] if len(text.splitlines())>1 else ""})
    image_paths=sorted((p for p in OUT.glob(f"{stem}-*.png") if int(p.stem.rsplit("-",1)[-1])<=len(pages)),
                       key=lambda p:int(p.stem.rsplit("-",1)[-1]))
    assert len(image_paths)==len(pages)
    sheets=[]
    for offset in range(0,len(image_paths),4):
        group=image_paths[offset:offset+4]
        sheet=Image.new("RGB",(1530,2040),"#dce1e5")
        draw=ImageDraw.Draw(sheet)
        for j,path in enumerate(group):
            with Image.open(path) as im:
                im=ImageOps.contain(im.convert("RGB"),(745,990))
                x,y=(j%2)*765+10,(j//2)*1020+25
                sheet.paste(im,(x,y))
                draw.text((x,y-18),f"{stem} | page {offset+j+1}",fill="#1b2738")
        target=OUT/f"contact_{stem}_{offset//4+1}.png"
        sheet.save(target)
        sheets.append(str(target))
    report[stem]={"page_count":len(pages),"pages":pages,"contact_sheets":sheets}
(ROOT/"audit/pdf_qa.json").write_text(json.dumps(report,indent=2)+"\n")
print(json.dumps(report,indent=2))
