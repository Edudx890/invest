from pathlib import Path
import zipfile

ROOT=Path(__file__).resolve().parents[1]
DEST=ROOT/"dist"/"CarteiraClara-homologacao.zip"
SKIP={".git",".venv","data","__pycache__",".pytest_cache","dist"}
REQUIRED={"app.py","requirements.txt","setup_windows.bat","run_windows.bat","src/portfolio_app/db.py","src/portfolio_app/calculations.py","tests/test_financial.py","tests/test_importers.py","tests/test_db.py","tests/test_market_data.py","docs/METODOLOGIA_FINANCEIRA.md","docs/TESTES.md","CHANGELOG.md"}
files=[p for p in ROOT.rglob("*") if p.is_file() and not any(part in SKIP for part in p.relative_to(ROOT).parts) and p.suffix not in {".pyc",".pyo"} and p.name!="secrets.toml"]
DEST.parent.mkdir(parents=True,exist_ok=True)
with zipfile.ZipFile(DEST,"w",zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
    for path in sorted(files):
        archive.write(path,Path("CarteiraClara")/path.relative_to(ROOT))
with zipfile.ZipFile(DEST) as archive:
    names=set(archive.namelist())
    missing=[f"CarteiraClara/{item}" for item in REQUIRED if f"CarteiraClara/{item}" not in names]
    if missing or archive.testzip():
        raise SystemExit(f"ZIP inválido/incompleto: {missing}")
    if any("/data/" in name or "/.venv/" in name or "/.git/" in name for name in names):
        raise SystemExit("ZIP contém dados locais/ambiente virtual.")
print(f"ZIP válido: {DEST} ({len(files)} arquivos)")
