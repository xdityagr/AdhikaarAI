"""Find user-visible English that is not going through t()."""
import re, sys, pathlib, json

ROOT = pathlib.Path(".")
FILES = sorted([p for p in ROOT.rglob("*.tsx") if "node_modules" not in p.parts]
               + [p for p in ROOT.rglob("*.ts") if "node_modules" not in p.parts
                  and "i18n" not in p.parts and not p.name.endswith(".d.ts")])

# JSX text nodes: >text< where text has a letter and isn't an expression
TEXT = re.compile(r">(?!\s*[<{])\s*([A-Z][^<>{}\n]{3,}?)\s*<")
# user-facing string props
PROP = re.compile(r'\b(placeholder|title|alt|aria-label|label|lede|eyebrow|blurb)\s*=\s*"([^"]{4,})"')
# object literals that look like display strings
FIELD = re.compile(r'\b(label|blurb|title|heading|description)\s*:\s*"([^"]{4,})"')

WORDS = re.compile(r"[A-Za-z]{2,}")
SKIP = re.compile(r"^(https?:|/|#|[A-Z_]+$|\d)")

findings = {}
for path in FILES:
    src = path.read_text(encoding="utf-8")
    hits = []
    for lineno, line in enumerate(src.splitlines(), 1):
        stripped = line.strip()
        if stripped.startswith("//") or stripped.startswith("*"):
            continue
        for rx, group in ((TEXT, 1), (PROP, 2), (FIELD, 2)):
            for m in rx.finditer(line):
                txt = m.group(group).strip()
                if SKIP.match(txt) or len(WORDS.findall(txt)) < 2:
                    continue
                if "t(" in line and txt not in line.split("t(")[0]:
                    pass
                hits.append((lineno, txt))
    if hits:
        findings[str(path).replace("\\", "/")] = hits

order = sorted(findings.items(), key=lambda kv: -len(kv[1]))
total = sum(len(v) for v in findings.values())
print(f"{total} suspect strings across {len(findings)} files\n")
for path, hits in order:
    print(f"{path}  ({len(hits)})")
    for lineno, txt in hits[:4]:
        print(f"    {lineno}: {txt[:70]}")
    if len(hits) > 4:
        print(f"    ... +{len(hits)-4} more")
