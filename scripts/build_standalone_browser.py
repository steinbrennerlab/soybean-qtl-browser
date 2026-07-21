"""Build a single-file soybean QTL browser that works from file:// URLs."""

import json
import tempfile
import time
from pathlib import Path


BASE = Path(__file__).resolve().parents[1]
BROWSER = BASE / "browser"
DATA = BASE / "data"
OUTPUT = BROWSER / "soybean_qtl_browser.html"


def load_json(path: Path):
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def javascript_json(value) -> str:
    """Serialize JSON without allowing data to terminate an inline script."""
    return (
        json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def main() -> None:
    html = (BROWSER / "index.html").read_text(encoding="utf-8")
    css = (BROWSER / "styles.css").read_text(encoding="utf-8")
    app = (BROWSER / "app.js").read_text(encoding="utf-8")

    payload = {
        "rows": load_json(DATA / "soybean_resistance_qtl_collation.json"),
        "manifest": load_json(DATA / "manifest.json"),
        "schema": load_json(DATA / "schema.json"),
        "prr": load_json(DATA / "prr_gene_calls.json"),
        "qtlPrrOverlaps": load_json(DATA / "qtl_prr_overlaps.json"),
        "geneManifest": load_json(DATA / "wm82_gene_manifest.json"),
    }

    stylesheet_tag = '<link rel="stylesheet" href="styles.css" />'
    application_tag = '<script src="app.js"></script>'
    if stylesheet_tag not in html or application_tag not in html:
        raise RuntimeError("browser/index.html no longer contains the expected asset tags")

    html = html.replace(stylesheet_tag, f"<style>\n{css}\n</style>", 1)
    scripts = (
        "<script>\n"
        f"globalThis.SOYBEAN_QTL_BROWSER_DATA={javascript_json(payload)};\n"
        "</script>\n"
        f"<script>\n{app}\n</script>"
    )
    html = html.replace(application_tag, scripts, 1)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        newline="\n",
        prefix=f".{OUTPUT.name}.staging-",
        dir=BROWSER,
        delete=False,
    ) as handle:
        handle.write(html)
        staging = Path(handle.name)
    for attempt in range(8):
        try:
            staging.replace(OUTPUT)
            break
        except PermissionError:
            if attempt == 7:
                raise
            time.sleep(0.25 * (attempt + 1))
    print(f"Wrote {OUTPUT.relative_to(BASE)} ({OUTPUT.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
