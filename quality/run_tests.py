"""Executa a suíte complementar e os testes originais do backend."""
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
BACKEND = ROOT.parent / "backend"

def main():
    (ROOT / "evidence").mkdir(exist_ok=True)
    env = {**os.environ, "PYTHONPATH": str(BACKEND)}
    return subprocess.call([
        sys.executable, "-m", "pytest", "tests", str(BACKEND / "tests"),
        "--cov=" + str(BACKEND / "app"), "--cov-branch",
        "--cov-report=json:evidence/coverage.json",
        "--cov-report=html:evidence/htmlcov", "--cov-report=term",
        "--junitxml=evidence/junit.xml", *sys.argv[1:],
    ], cwd=ROOT, env=env)

if __name__ == "__main__":
    raise SystemExit(main())
