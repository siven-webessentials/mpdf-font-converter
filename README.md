# mPDF Font Converter

Convert modern OpenType fonts such as **Kantumruy Pro** into a form that **mPDF** can load and shape, so Khmer text (and other complex scripts) renders correctly in generated PDFs.

This repository contains the static Kantumruy Pro fonts, the ready-to-use converted files, and three small Python scripts to inspect, convert, and verify any other font that runs into the same problem.

> **Just need the fonts?** Copy `KantumruyPro-Mpdf-Regular.ttf` and `KantumruyPro-Mpdf-Bold.ttf` into your project and jump to [Using the fonts in Laravel / mPDF](#6-using-the-fonts-in-laravel--mpdf).

---

## Table of contents

- [Why mPDF fails on modern fonts](#why-mpdf-fails-on-modern-fonts)
- [Repository contents](#repository-contents)
- [Requirements](#requirements)
- [Conversion pipeline](#conversion-pipeline)
  - [1. Get static font files](#1-get-static-font-files)
  - [2. Set up the Python environment](#2-set-up-the-python-environment)
  - [3. Inspect the font](#3-inspect-the-font-inspect_fontpy)
  - [4. Convert the font](#4-convert-the-font-mpdf_compatpy)
  - [5. Compare shaping before and after](#5-compare-shaping-before-and-after-compare_shapingpy)
  - [6. Using the fonts in Laravel / mPDF](#6-using-the-fonts-in-laravel--mpdf)
- [Known limitations](#known-limitations)
- [Troubleshooting](#troubleshooting)
- [Credits and license](#credits-and-license)

---

## Why mPDF fails on modern fonts

mPDF does not use HarfBuzz or the operating system to lay out text. It has its own PHP font parser (`TTFontFile.php`) and its own OpenType Layout (OTL) engine. Those support a **subset** of the OpenType specification. Modern fonts such as Kantumruy Pro use two features that fall outside that subset:

| Feature in the font | What it is | What mPDF does |
| --- | --- | --- |
| **GSUB Lookup Type 5, Format 3** | Contextual substitution, coverage-based | Not supported. Font loading fails with a "Lookup Type 5 / Format 3" error. |
| **Mark Filtering Sets** (`LookupFlag 0x10`, GDEF v1.2 `MarkGlyphSetsDef`) | Lets a lookup ignore all marks except a specific set | Not supported. The lookups are misread or rejected. |

Running `inspect_font.py` on the original Kantumruy Pro Regular shows both problems:

```text
GSUB {..., 'type6 format3 +markset': 12, ..., 'type5 format3': 1}
GPOS {..., 'type6 format1 +markset': 6}
mark filtering sets: True
```

The fix is to rewrite the font so it only uses features mPDF understands:

1. **Type 5 Format 3 → Type 6 Format 3.** A contextual substitution is the same thing as a *chaining* contextual substitution with an empty backtrack and lookahead. mPDF supports Type 6 Format 3, so this rewrite loses nothing.
2. **Drop mark filtering sets.** Clear flag `0x10` on every lookup, remove `MarkGlyphSetsDef`, and downgrade GDEF to version 1.0. This part is **lossy** (see [Known limitations](#known-limitations)).

---

## Repository contents

| File | Purpose |
| --- | --- |
| `KantumruyPro-*.ttf` | Original static Kantumruy Pro fonts (all weights and italics) |
| `KantumruyPro-Mpdf-Regular.ttf` | **Converted** Regular, ready for mPDF |
| `KantumruyPro-Mpdf-Bold.ttf` | **Converted** Bold, ready for mPDF |
| `inspect_font.py` | Lists the GSUB/GPOS lookup types a font uses and flags the ones mPDF can't handle |
| `mpdf_compat.py` | Rewrites a font into the mPDF-compatible subset |
| `compare_shaping.py` | Shapes real text with the original and converted fonts and reports which words differ |
| `kh.txt` / `kh.php` | Sample Khmer strings (a Laravel translation file) used as test text |
| `ftenv/` | Python virtual environment with `fonttools` and `uharfbuzz` |

---

## Requirements

- Python 3.8+ (tested with 3.12)
- [`fonttools`](https://github.com/fonttools/fonttools): reads and writes font tables
- [`uharfbuzz`](https://github.com/harfbuzz/uharfbuzz): HarfBuzz bindings, used only for comparing shaping
- mPDF 8.x (for the PHP side)

---

## Conversion pipeline

```text
static .ttf ──► inspect_font.py ──► mpdf_compat.py ──► inspect_font.py ──► compare_shaping.py ──► mPDF
               (find problems)      (convert)         (confirm clean)    (measure the difference)
```

### 1. Get static font files

mPDF **cannot** load variable fonts (e.g. `KantumruyPro[wght].ttf`). Always use the static, single-weight `.ttf` files. They are already in this repository. To download them again from upstream:

```bash
curl -LO https://raw.githubusercontent.com/anagata-design/kantumruy-pro/main/fonts/ttf/KantumruyPro-Regular.ttf
curl -LO https://raw.githubusercontent.com/anagata-design/kantumruy-pro/main/fonts/ttf/KantumruyPro-Bold.ttf
curl -LO https://raw.githubusercontent.com/anagata-design/kantumruy-pro/main/OFL.txt
```

### 2. Set up the Python environment

```bash
# Create the virtual environment
python3 -m venv ftenv

# Install the dependencies
ftenv/bin/python -m pip install fonttools uharfbuzz
```

On Debian/Ubuntu, `python3 -m venv` can fail with `ensurepip is not available`. Create the environment without pip and bootstrap pip yourself:

```bash
python3 -m venv --without-pip ftenv

curl -sLO https://bootstrap.pypa.io/get-pip.py
ftenv/bin/python get-pip.py
rm get-pip.py

ftenv/bin/python -m pip install fonttools uharfbuzz
```

(Alternatively, `sudo apt install python3-venv` installs `ensurepip` so the normal command works.)

### 3. Inspect the font (`inspect_font.py`)

This script walks every lookup in the `GSUB` (substitution) and `GPOS` (positioning) tables and counts them by lookup type and subtable format. Extension lookups (GSUB type 7, GPOS type 9) are unwrapped so you see the real type underneath. Lookups that use a mark filtering set are tagged `+markset`. Finally it reports whether GDEF defines any mark filtering sets.

> ⚠️ Name the file `inspect_font.py`, **not** `inspect.py`. A file called `inspect.py` shadows Python's built-in `inspect` module and causes a circular-import crash (see [Troubleshooting](#troubleshooting)).

```python
# inspect_font.py
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
```

Run it:

```bash
ftenv/bin/python inspect_font.py KantumruyPro-Regular.ttf
```

In the output, look for:

- `type5 format3` under **GSUB**: needs converting
- any key ending in `+markset`, or `mark filtering sets: True`: needs converting

If neither appears, mPDF can probably load the font as it is.

### 4. Convert the font (`mpdf_compat.py`)

This script makes two changes:

1. **Every GSUB Type 5 lookup whose subtables are all Format 3** is rebuilt as a Type 6 Format 3 (chaining contextual) lookup. The input coverage and substitution records are copied over unchanged, and backtrack and lookahead are left empty. This is lossless.
2. **Mark filtering sets are removed.** On every GSUB and GPOS lookup, flag `0x10` is cleared and `MarkFilteringSet` is dropped. Then GDEF's `MarkGlyphSetsDef` is deleted and GDEF is set back to version 1.0. This is lossy.

```python
# mpdf_compat.py
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

    # 1. GSUB type 5 format 3  ->  type 6 format 3 (lossless)
    for lookup in font['GSUB'].table.LookupList.Lookup:
        if lookup.LookupType == 5 and all(getattr(s, 'Format', None) == 3 for s in lookup.SubTable):
            lookup.SubTable = [chain_from_context(s) for s in lookup.SubTable]
            lookup.LookupType = 6

    # 2. Remove mark filtering sets (lossy)
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
```

Convert each weight you need:

```bash
ftenv/bin/python mpdf_compat.py KantumruyPro-Regular.ttf KantumruyPro-Mpdf-Regular.ttf
ftenv/bin/python mpdf_compat.py KantumruyPro-Bold.ttf    KantumruyPro-Mpdf-Bold.ttf
```

Then inspect the output again to make sure it's clean:

```bash
ftenv/bin/python inspect_font.py KantumruyPro-Mpdf-Regular.ttf
```

```text
GSUB {'type1 format-': 26, 'type3 format-': 1, 'type6 format1': 2, 'type2 format-': 2, 'type6 format3': 28, 'type4 format-': 4}
GPOS {'type2 format1': 1, 'type2 format2': 1, 'type4 format1': 3, 'type6 format1': 6}
mark filtering sets: False
```

`type5 format3` is gone (it's now counted under `type6 format3`), no `+markset` remains, and GDEF has no filtering sets.

### 5. Compare shaping before and after (`compare_shaping.py`)

Removing mark filtering sets changes how some glyphs combine, so check how much it affects **your actual text** before you ship. This script:

1. Loads both fonts into HarfBuzz, the same shaping engine browsers use.
2. Pulls every unique Khmer word (Unicode block `U+1780–U+17FF`) out of a text file.
3. Shapes each word with both fonts and compares the glyph IDs, offsets, and advances.
4. Prints how many words differ and lists up to 20 of them.

```python
# compare_shaping.py
import re, sys
import uharfbuzz as hb

def shaper(path):
    font = hb.Font(hb.Face(open(path, 'rb').read()))
    def shape(text):
        buf = hb.Buffer(); buf.add_str(text); buf.guess_segment_properties()
        hb.shape(font, buf, {})
        return [(i.codepoint, p.x_offset, p.y_offset, p.x_advance)
                for i, p in zip(buf.glyph_infos, buf.glyph_positions)]
    return shape

original, converted = shaper(sys.argv[1]), shaper(sys.argv[2])
text = open(sys.argv[3], encoding='utf-8').read()
words = sorted(set(re.findall(r'[ក-៿]+', text)))       # Khmer block
diff = [w for w in words if original(w) != converted(w)]
print(f'{len(diff)} of {len(words)} words shape differently:', diff[:20])
```

Run it on your own strings (for example a Laravel `lang/km/*.php` file):

```bash
ftenv/bin/python compare_shaping.py KantumruyPro-Regular.ttf KantumruyPro-Mpdf-Regular.ttf kh.txt
```

```text
18 of 49 words shape differently: ['ការបង្ហាញមេរៀន', 'កំណត់សម្គាល់', 'ថ្នាក់', 'មុខវិជ្ជា', 'សប្តាហ៍', ...]
```

A difference doesn't always mean the word looks wrong. It means the glyph sequence changed. Render the listed words in a test PDF and check them by eye. The script only works with a text file, so copy strings out of other formats first.

### 6. Using the fonts in Laravel / mPDF

**6.1 Copy the converted fonts** into your project:

```bash
cp KantumruyPro-Mpdf-*.ttf /path/to/laravel-app/resources/fonts/
```

**6.2 Register the font family** wherever you build the mPDF instance (in our project that's `LessonPlanHelper.php`). Merge it with mPDF's default font directories and font data so the built-in fonts keep working:

```php
<?php

namespace App\Helpers;

use Mpdf\Config\ConfigVariables;
use Mpdf\Config\FontVariables;
use Mpdf\Mpdf;

class LessonPlanHelper
{
    /**
     * Default font per application locale.
     */
    private const LOCALE_FONTS = [
        'km' => 'kantumruypro',
        'en' => 'kantumruypro',   // Kantumruy Pro also contains Latin glyphs
    ];

    public static function makeMpdf(string $locale): Mpdf
    {
        $fontDirs = (new ConfigVariables())->getDefaults()['fontDir'];
        $fontData = (new FontVariables())->getDefaults()['fontdata'];

        return new Mpdf([
            'mode'     => 'utf-8',
            'format'   => 'A4',
            'tempDir'  => storage_path('framework/cache/mpdf'),

            'fontDir'  => array_merge($fontDirs, [resource_path('fonts')]),
            'fontdata' => $fontData + [
                'kantumruypro' => [
                    'R'      => 'KantumruyPro-Mpdf-Regular.ttf',
                    'B'      => 'KantumruyPro-Mpdf-Bold.ttf',
                    'useOTL' => 0xFF,   // enable OpenType Layout (required for Khmer)
                ],
            ],

            'default_font'     => self::LOCALE_FONTS[$locale] ?? 'kantumruypro',
            'autoScriptToLang' => true,   // detect Khmer script in mixed text
            'autoLangToFont'   => true,   // pick the right font for the detected language
        ]);
    }
}
```

Key points:

| Option | Why it matters |
| --- | --- |
| `'useOTL' => 0xFF` | Turns on mPDF's OpenType Layout engine for **all** scripts in the font. Without it, Khmer subscripts (coeng) and vowel reordering are not applied. |
| `'R'` / `'B'` | mPDF picks the file by font style. Set every style your HTML uses (`<b>`, `<strong>`, `font-weight: bold`, headings). |
| `fontDir` merge | Keeps mPDF's bundled fonts available alongside yours. |
| `tempDir` | Where mPDF caches parsed font metrics. You must clear it after replacing a font file. |
| `LOCALE_FONTS` | Maps the app locale (`app()->getLocale()`) to an mPDF font key, so each language gets the right default font. |

Use the font in your Blade/HTML template, and add a `lang` attribute so mPDF's language-to-font mapping can do its job:

```html
<body lang="km" style="font-family: kantumruypro;">
    <h1>ផែនការបង្រៀន</h1>
</body>
```

**6.3 Clear the mPDF font cache.** mPDF caches font data in `tempDir`. After you replace or re-convert a font, delete the cache, or mPDF will keep using the old data:

```bash
rm -rf storage/framework/cache/mpdf/*
```

If you haven't set `tempDir`, the default cache location is `vendor/mpdf/mpdf/tmp/`.

---

## Known limitations

Dropping mark filtering sets is **lossy**. The original font used them so that some lookups looked past every mark except a chosen set. Once they're removed, those lookups see every mark. In Kantumruy Pro this means:

- A **consonant + vowel sign AA (ា)** ligature no longer forms when a subscript consonant sits between them, so AA is drawn as a separate glyph.
- A few words such as `ថ្នាក់`, `សប្តាហ៍`, and `មុខវិជ្ជា` shape slightly differently from the original font (18 of 49 unique words in `kh.txt`).

The text stays readable and correct, but some ligatures differ slightly from the original design. If exact rendering matters, consider a PDF engine backed by HarfBuzz (e.g. a headless browser) instead of mPDF.

---

## Troubleshooting

| Symptom / error | Cause | Solution |
| --- | --- | --- |
| mPDF throws a font error mentioning **Lookup Type 5, Format 3** | The font uses GSUB contextual substitution Format 3, which mPDF's parser doesn't support. | Run `mpdf_compat.py` on the font. Register the converted `*-Mpdf-*.ttf` file and clear the mPDF cache. |
| `ImportError: cannot import name 'TTFont' from partially initialized module ...` (**circular import**) | The script was saved as `inspect.py`. Python imports it in place of the standard library `inspect` module, which fontTools depends on. | Rename it to `inspect_font.py`. Delete any leftover `inspect.py` and the `__pycache__/` folder next to it. |
| `The virtual environment was not created successfully because ensurepip is not available` | Debian/Ubuntu ship Python without `ensurepip` unless `python3-venv` is installed. | Run `python3 -m venv --without-pip ftenv`, then bootstrap with `get-pip.py` ([step 2](#2-set-up-the-python-environment)). Or run `sudo apt install python3-venv`. |
| **Bold** text renders as empty boxes (□) while regular text is fine | The file registered under `'B'` has no glyphs for the script (common with fonts whose Bold covers fewer scripts, e.g. FreeSerif Bold for Bengali). The `'B'` file may also be missing, or the wrong file was set. | Check that the `'B'` file exists in `fontDir` and contains the script. As a workaround, map the Regular file to the Bold slot too: `'B' => 'KantumruyPro-Mpdf-Regular.ttf'`. Clear the cache afterwards. |
| Khmer **subscripts don't stack**: coeng (្) shows as a separate mark, vowels are in the wrong order | OpenType Layout is disabled. Either `useOTL` is missing or `0x00`, or the font was rejected and mPDF fell back to another font. | Set `'useOTL' => 0xFF` in the `fontdata` entry. Make sure the converted font is the one in use. Clear `tempDir`. |
| Changes to the font or config have no effect | mPDF is still serving cached font metrics from `tempDir`. | Run `rm -rf storage/framework/cache/mpdf/*` (or your configured `tempDir`). |
| mPDF can't load the font at all / variable font errors | A variable font (`[wght].ttf`) was used. | Use the static per-weight `.ttf` files. |

---

## Credits and license

- **Kantumruy Pro** by [Anagata Design](https://github.com/anagata-design/kantumruy-pro), licensed under the [SIL Open Font License 1.1](https://openfontlicense.org). The converted `*-Mpdf-*.ttf` files are modified versions of it and are distributed under the same license.
- Font tooling: [fontTools](https://github.com/fonttools/fonttools) and [uharfbuzz](https://github.com/harfbuzz/uharfbuzz).
- PDF generation: [mPDF](https://github.com/mpdf/mpdf).
