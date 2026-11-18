"""Licence audit: every installed Python dependency must carry a commercial-use licence.
Fails CI on non-commercial or unknown licences (competition rule: list and comply)."""

import subprocess
import sys
import json

ALLOWED = ("MIT", "BSD", "Apache", "ISC", "PSF", "Python Software Foundation", "MPL", "Unlicense", "CC0", "HPND", "Zope")
BLOCKED = ("NonCommercial", "Non-Commercial", "CC-BY-NC", "Commons Clause", "SSPL", "BUSL", "AGPL")


def main() -> int:
    out = subprocess.run([sys.executable, "-m", "piplicenses", "--format=json", "--with-system"], capture_output=True, text=True)
    if out.returncode != 0:
        print(out.stderr)
        return 1
    bad = []
    for pkg in json.loads(out.stdout):
        lic = pkg["License"]
        if any(b.lower() in lic.lower() for b in BLOCKED) or not any(a.lower() in lic.lower() for a in ALLOWED):
            if pkg["Name"] in ("setu", "pip", "setuptools", "wheel"):
                continue
            bad.append(f"{pkg['Name']} {pkg['Version']}: {lic}")
    if bad:
        print("✗ licences needing review:\n  " + "\n  ".join(bad))
        return 1
    print("✓ all Python dependency licences permit commercial use")
    return 0


if __name__ == "__main__":
    sys.exit(main())
