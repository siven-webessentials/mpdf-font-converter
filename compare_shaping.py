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
words = sorted(set(re.findall(r'[\u1780-\u17FF]+', text)))       # Khmer block
diff = [w for w in words if original(w) != converted(w)]
print(f'{len(diff)} of {len(words)} words shape differently:', diff[:20])
