from pathlib import Path
import sys
from pathlib import Path as _Path

# Ensure repository root in sys.path for local imports (consistency with other tests)
sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))


def test_index_has_status_autorefresh():
    html = Path("templates/index.html").read_text(encoding="utf-8")
    # Verifica que hay un setInterval que llama a refreshStatus periódicamente
    assert "setInterval" in html and "refreshStatus" in html
