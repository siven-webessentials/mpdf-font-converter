"""
Rewrite a font's OpenType tables into the subset mpdf 8 can parse.

mpdf rejects two things modern fonts such as Kantumruy Pro use:
  * GSUB contextual substitution format 3 (LookupType 5) - rewritten, losslessly,
    as chaining contextual substitution format 3 with empty backtrack/lookahead;
  * GDEF mark filtering sets (LookupFlag 0x10) - dropped, so those lookups see
    every mark. This is lossy: in Kantumruy Pro, a consonant + vowel-sign AA
    ligature no longer forms across a subscript, and a standalone AA is drawn.

Usage (fontTools required: pip install fonttools):
    python mpdf_compat.py KantumruyPro-Regular.ttf KantumruyPro-Mpdf-Regular.ttf

Source fonts: https://github.com/anagata-design/kantumruy-pro (fonts/ttf).
"""
import sys

from fontTools.ttLib import TTFont
from fontTools.ttLib.tables import otTables as ot


def chain_from_context(subtable):
    chain = ot.ChainContextSubst()
    chain.Format = 3
    chain.BacktrackGlyphCount = 0
    chain.BacktrackCoverage = []
    chain.InputGlyphCount = subtable.GlyphCount
    chain.InputCoverage = subtable.Coverage
    chain.LookAheadGlyphCount = 0
    chain.LookAheadCoverage = []
    chain.SubstCount = subtable.SubstCount
    chain.SubstLookupRecord = subtable.SubstLookupRecord
    return chain


def convert(source, target):
    font = TTFont(source)

    for lookup in font['GSUB'].table.LookupList.Lookup:
        if lookup.LookupType == 5 and all(getattr(s, 'Format', None) == 3 for s in lookup.SubTable):
            lookup.SubTable = [chain_from_context(s) for s in lookup.SubTable]
            lookup.LookupType = 6

    for tag in ('GSUB', 'GPOS'):
        for lookup in font[tag].table.LookupList.Lookup:
            if lookup.LookupFlag & 0x10:
                lookup.LookupFlag &= ~0x10
                lookup.MarkFilteringSet = None

    gdef = font['GDEF'].table
    gdef.MarkGlyphSetsDef = None
    gdef.Version = 0x00010000

    font.save(target)


if __name__ == '__main__':
    convert(sys.argv[1], sys.argv[2])
