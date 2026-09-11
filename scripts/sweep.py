"""Run old and new parse_list over the whole corpus and compare."""
import importlib.util
import sqlite3
import sys

sys.path.insert(0, r"C:\Users\Aditya\Projects\AdhikaarAI")
from src.application import parse_list as new_parse                # noqa: E402

spec = importlib.util.spec_from_file_location(
    "old_application",
    r"C:\Users\Aditya\AppData\Local\Temp\claude"
    r"\C--Users-Aditya-Projects-AdhikaarAI"
    r"\34a2f36b-7097-413e-9a44-047d1f6433a8\scratchpad\application_backup.py")
old = importlib.util.module_from_spec(spec)
sys.modules["old_application"] = old
spec.loader.exec_module(old)
old_parse = old.parse_list

c = sqlite3.connect(r"C:\Users\Aditya\Projects\AdhikaarAI\data\schemes.db")

rows = c.execute(
    "SELECT slug, application_md FROM schemes "
    "WHERE application_md IS NOT NULL AND application_md != ''").fetchall()
print(f"English: {len(rows)} schemes with an apply section")

lost, grew, same, bigjump = 0, 0, 0, []
total_chars_old = total_chars_new = 0
for slug, md in rows:
    o, n = old_parse(md, 15), new_parse(md, 15)
    total_chars_old += sum(len(x) for x in o)
    total_chars_new += sum(len(x) for x in n)
    if not n and o:
        lost += 1
        if len(bigjump) < 5:
            bigjump.append(("LOST", slug, len(o), len(n)))
    elif len(n) > len(o) + 4:
        grew += 1
        if len(bigjump) < 10:
            bigjump.append(("GREW", slug, len(o), len(n)))
    elif len(n) == len(o):
        same += 1

print(f"  same count       : {same}")
print(f"  grew by >4 items : {grew}")
print(f"  produced nothing : {lost}")
print(f"  text kept        : {total_chars_new}/{total_chars_old} chars "
      f"({100 * total_chars_new / max(total_chars_old, 1):.1f}%)")
for kind, slug, a, b in bigjump:
    print(f"    {kind} {slug}: {a} -> {b}")

print()
hi = c.execute(
    "SELECT slug, application_md FROM scheme_i18n "
    "WHERE lang='hi' AND application_md IS NOT NULL AND application_md != ''"
).fetchall()
print(f"Hindi: {len(hi)} schemes with a translated apply section")

one_item_old = sum(1 for _, md in hi if len(old_parse(md, 15)) <= 2)
one_item_new = sum(1 for _, md in hi if len(new_parse(md, 15)) <= 2)
print(f"  collapsed to <=2 items, before : {one_item_old}")
print(f"  collapsed to <=2 items, after  : {one_item_new}")

# Structure should now agree between the two languages.
agree_before = agree_after = both = 0
en_by_slug = dict(rows)
for slug, md in hi:
    if slug not in en_by_slug:
        continue
    both += 1
    e_old, e_new = old_parse(en_by_slug[slug], 15), new_parse(en_by_slug[slug], 15)
    h_old, h_new = old_parse(md, 15), new_parse(md, 15)
    agree_before += len(e_old) == len(h_old)
    agree_after += len(e_new) == len(h_new)
print(f"  same step count as English, before: {agree_before}/{both} "
      f"({100 * agree_before / max(both, 1):.0f}%)")
print(f"  same step count as English, after : {agree_after}/{both} "
      f"({100 * agree_after / max(both, 1):.0f}%)")
