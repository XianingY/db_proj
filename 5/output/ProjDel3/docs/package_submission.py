"""Package only submission files; never include venvs, caches, or absolute paths."""
import hashlib
import json
from pathlib import Path
from zipfile import ZipFile,ZIP_DEFLATED

ROOT=Path(__file__).resolve().parents[1]


def eligible(path):
    return path.is_file() and not any(part in {'.venv','__pycache__','.DS_Store','.git'}
        for part in path.relative_to(ROOT).parts) and path.suffix not in {'.pyc','.pyo'}


def main():
    manifest=ROOT/'evidence/package_manifest.json'
    files=sorted(p for p in ROOT.rglob('*') if eligible(p) and p!=manifest)
    entries=[{'path':str(p.relative_to(ROOT)),'bytes':p.stat().st_size,
              'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in files]
    manifest.write_text(json.dumps({'format':'ProjDel3 manifest v1','files':entries},ensure_ascii=False,indent=2)+'\n')
    files.append(manifest)
    archive=ROOT.parent/'ProjDel3.zip'
    with ZipFile(archive,'w',ZIP_DEFLATED) as package:
        for path in sorted(files):package.write(path,'ProjDel3/'+str(path.relative_to(ROOT)))
    with ZipFile(archive) as package:
        assert package.testzip() is None
        names=package.namelist()
        assert len(names)==len(files)==len(set(names))
        for entry in entries:
            assert hashlib.sha256(package.read('ProjDel3/'+entry['path'])).hexdigest()==entry['sha256']
        assert all(not n.startswith('/') and '..' not in Path(n).parts for n in names)
        assert all('.venv' not in n and '__pycache__' not in n for n in names)
    validation={'archive':'ProjDel3.zip','status':'passed','file_count':len(files),
        'bytes':archive.stat().st_size,'sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),
        'zip_crc_checked':True,'manifest_hashes_verified':True,'no_runtime_cache_or_venv':True}
    (ROOT.parent/'package_validation.json').write_text(json.dumps(validation,ensure_ascii=False,indent=2)+'\n')
    print('提交包验证通过：',json.dumps(validation,ensure_ascii=False))


if __name__=='__main__':main()
