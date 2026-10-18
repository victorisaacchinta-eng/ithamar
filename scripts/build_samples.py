"""Build the sample statements the website ships, plus their Python audits.

  python scripts/build_samples.py web/public/samples

The site's story is driven by story.audit.json, written by the Python engine.
The live tool re-derives everything in the browser; scripts/parity.ts checks
that both engines agree on these files.
"""

import sys
from pathlib import Path

from ithamar.bench.synthetic import generate
from ithamar.parse import parse_pdf
from ithamar.report import audit, write_json

SAMPLES = [
    ("story", 11, "ashoka", 24, ["swap", "amount", "balance", "missing"]),
    ("clean", 12, "konark", 30, []),
    ("single-column", 13, "meridian", 30, ["amount", "swap"]),
]


def main(out: str) -> None:
    dest = Path(out)
    dest.mkdir(parents=True, exist_ok=True)
    for name, seed, layout, n, kinds in SAMPLES:
        pdf, _ = generate(dest, seed, layout, n, kinds)
        final = dest / f"{name}.pdf"
        pdf.replace(final)
        pdf.with_suffix(".truth.json").replace(dest / f"{name}.truth.json")
        _, payload = audit(parse_pdf(final))
        write_json(payload, dest / f"{name}.audit.json")
        s = payload["summary"]
        print(f"{name}: {s['rows']} rows, {s['verified']} verified, {s['repaired']} repaired, {s['broken']} broken")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "web/public/samples")
