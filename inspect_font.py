import sys
from collections import Counter
from fontTools.ttLib import TTFont

f = TTFont(sys.argv[1])
for tag in ('GSUB', 'GPOS'):
    c = Counter()
    for lk in f[tag].table.LookupList.Lookup:
        ext = lk.LookupType == (7 if tag == 'GSUB' else 9)      # extension wrapper
        for st in lk.SubTable:
            real = st.ExtSubTable if ext else st
            typ = st.ExtensionLookupType if ext else lk.LookupType
            c[f"type{typ} format{getattr(real, 'Format', '-')}"
              f"{' +markset' if lk.LookupFlag & 0x10 else ''}"] += 1
    print(tag, dict(c))
gdef = f['GDEF'].table
print('mark filtering sets:', bool(getattr(gdef, 'MarkGlyphSetsDef', None)))
