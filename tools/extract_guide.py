"""Extract structured content from AI-Development-Arabic-Guide.pdf -> guide.json

Two extractors, each broken differently:
  * pypdf   : correct Arabic/bidi ordering & punctuation, but silently DROPS glyphs
              (fi/fl/ff ligatures, لى/لأ/لإ ligatures, "$", text around «»).
  * pymupdf : keeps every glyph, gives layout (fonts, y, tables, drawings), but
              reverses Arabic ligature pairs (لا->ال, لى->ىل ...) and misplaces punctuation.
Per line we take pypdf (repaired with pymupdf's words as oracle) unless pymupdf shows words
pypdf lost, in which case we take pymupdf (repaired with pypdf's words as oracle).
"""
import re, json, base64, sys, itertools, difflib
import pymupdf
from pypdf import PdfReader

PDF = sys.argv[1] if len(sys.argv) > 1 else 'AI-Development-Arabic-Guide.pdf'
OUT = sys.argv[2] if len(sys.argv) > 2 else 'guide.json'
doc = pymupdf.open(PDF)
rd = PdfReader(PDF)

AR_LET = r'ء-ؿف-يٮ-ۓ'                 # arabic letters, NOT tatweel (ـ)
AR_L = AR_LET + r'ً-ْ،؛؟'                  # + marks + arabic punctuation
LAT = r'A-Za-z0-9'
FOOT = re.compile(r'^(AI IN DEVELOPMENT / EXPLAINER|Abdelaziz Farid \| September 2026( \d+)?|\d{1,2})$')
PUNCT = '.,،;:؛!?؟)(][»«"\'…'


def split_bound(s):
    """insert the spaces the PDF text lacks between arabic and latin runs, normalise punctuation spacing"""
    s = re.sub(rf'(?<=[{AR_L}])(?=[{LAT}$\[\(«"])', ' ', s)
    s = re.sub(rf'(?<=[{LAT}\)\]%»"])(?=[{AR_LET}])', ' ', s)
    s = re.sub(r'\bT (?=(ool|ask|oken|est|ech|eam)s?\b)', 'T', s)          # kerning artefact "T ool"
    s = re.sub(r'[ \t]+', ' ', s).strip()
    s = re.sub(r' +([،؛؟,.])', r'\1', s)
    s = re.sub(r'« ', '«', s); s = re.sub(r' »', '»', s)
    return s


REV = {'ال': 'لا', 'أل': 'لأ', 'إل': 'لإ', 'ىل': 'لى'}


def variants(w):
    """all combinations of un-reversing ligature pairs in a pymupdf arabic word"""
    pos = sorted(set((m.start(), m.group()) for k in REV for m in re.finditer(k, w)))[:5]
    out = {w}
    for n in range(1, len(pos) + 1):
        for combo in itertools.combinations(pos, n):
            s = list(w); ok = True
            for i, k in combo:
                if ''.join(s[i:i + 2]) != k: ok = False; break
                s[i:i + 2] = list(REV[k])
            if ok: out.add(''.join(s))
    return out


def core(tok):
    pre = post = ''
    while tok and tok[0] in PUNCT: pre += tok[0]; tok = tok[1:]
    while tok and tok[-1] in PUNCT: post = tok[-1] + post; tok = tok[:-1]
    return pre, tok, post


def is_ar(s): return re.search(r'[؀-ۿ]', s) is not None


LIG_LAT = ['ffi', 'fi', 'fl', 'ff']
LIG_AR = ['لى', 'لأ', 'لإ', 'لا']


def tokens(text):
    return [core(t)[1] for t in split_bound(text).split() if core(t)[1]]


def repair_py(text, mu_set):
    """pypdf text: re-insert dropped ligatures where the result is a word pymupdf saw"""
    out = []
    for tok in split_bound(text).split(' '):
        pre, c, post = core(tok)
        if not c or c in mu_set: out.append(tok); continue
        fixed = None
        for lig in (LIG_AR + LIG_LAT if is_ar(c) else LIG_LAT):
            for i in range(len(c) + 1):
                cand = c[:i] + lig + c[i:]
                if cand in mu_set: fixed = cand; break
            if fixed: break
        out.append(pre + (fixed or c) + post)
    return ' '.join(out)


def fix_mu(text, py_set, py_global):
    """pymupdf text: un-reverse arabic ligature pairs, using pypdf words as oracle"""
    out = []
    for tok in split_bound(text).split(' '):
        pre, c, post = core(tok)
        if not c or not is_ar(c): out.append(tok); continue
        vs = variants(c)
        best = None
        for oracle in (py_set, py_global):
            for v in sorted(vs, key=len):
                if v in oracle: best = v; break
            if best: break
            for v in vs:                       # pypdf may have dropped a ligature from this word
                for lig in LIG_AR:
                    if lig in v and v.replace(lig, '', 1) in oracle: best = v; break
                if best: break
            if best: break
        if best is None:
            best = c.replace('ىل', 'لى')       # ى is final-only: "ىل" can only be a reversed ligature
            best = re.sub(r'(?<=إ)ال\b', 'لا', best)
        out.append(pre + best + post)
    return ' '.join(out)


def merge_lines(py_txt, mu_txt):
    """pypdf order+punctuation as skeleton; words only pymupdf saw are inserted where pymupdf has them"""
    py_t, mu_t = py_txt.split(), mu_txt.split()
    key = lambda t: core(t)[1].replace('$', '').lower()
    sm = difflib.SequenceMatcher(None, [key(t) for t in py_t], [key(t) for t in mu_t], autojunk=False)
    out = []
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == 'equal':
            for a, b in zip(py_t[i1:i2], mu_t[j1:j2]):
                pre, c, post = core(a)
                bpre, bc, bpost = core(b)
                pre = ''.join(ch for ch in bpre if ch in '«»' and ch not in pre) + pre
                post = post + ''.join(ch for ch in bpost if ch in '«»' and ch not in post)
                out.append(pre + (bc if '$' in b else c) + post)
        elif op == 'delete':
            out.extend(py_t[i1:i2])
        else:
            out.extend(mu_t[j1:j2])
    return ' '.join(out)


def classify(font, size, text):
    bold = 'Bold' in font
    t = text.strip()
    if font.startswith('DejaVu-Sans-Mono'): return 'code'
    if font.startswith('DejaVu'): return 'diagram'
    if bold and size >= 14: return 'title'
    if bold and size <= 8.6 and t.isupper() and re.search(r'[A-Z]{3,}', t): return 'label'
    if not bold and size <= 8.1 and t.isupper() and re.search(r'[A-Z]{3,}', t): return 'kicker'
    if size <= 7.5: return 'small'
    if bold and 9.4 <= size <= 12.5: return 'bold'
    return 'body'


# global pypdf oracle (words recur across pages)
py_pages = [[l for l in pg.extract_text().split('\n') if l.strip() and not FOOT.match(l.strip())] for pg in rd.pages]
PY_GLOBAL = set(t for lines in py_pages for l in lines for t in tokens(l))

pages = []
for pno in range(len(doc)):
    p = doc[pno]
    py_lines = []
    for l in py_pages[pno]:
        if py_lines and re.fullmatch(r'\s*(\[R\d+\]\s*)+', l): py_lines[-1] += ' ' + l.strip()
        else: py_lines.append(l)
    mu_set = set()
    for w in p.get_text('words'):
        for t in tokens(w[4]):
            mu_set |= variants(t) if is_ar(t) else {t}
    py_set = set(t for l in py_lines for t in tokens(l))

    # --- visual lines from pymupdf (merge bidi sub-lines that share a baseline / class) ---
    STRUCT = {'kicker', 'title', 'label'}
    blocks = []
    for b in p.get_text('dict')['blocks']:
        if b['type'] != 0: continue
        for l in b['lines']:
            spans = [sp for sp in l['spans'] if sp['text'].strip()]
            if not spans: continue
            main = max(spans, key=lambda sp: len(sp['text']))
            txt = ''.join(sp['text'] for sp in l['spans'])
            cls = classify(main['font'], main['size'], txt)
            prev = blocks[-1] if blocks else None
            split = prev is None or abs(prev['bbox'][3] - l['bbox'][3]) > 6 or (prev['cls'] != cls and (cls in STRUCT or prev['cls'] in STRUCT))
            if split:
                blocks.append(dict(bbox=list(l['bbox']), font=main['font'], size=round(main['size'], 1), mu=txt, cls=cls))
            else:
                prev['mu'] += txt
                bb = prev['bbox']; prev['bbox'] = [min(bb[0], l['bbox'][0]), min(bb[1], l['bbox'][1]), max(bb[2], l['bbox'][2]), max(bb[3], l['bbox'][3])]
    blocks = [b for b in blocks if 35 < b['bbox'][1] < 805]
    merged = []
    for b in blocks:
        if merged and re.fullmatch(r'\s*(\[R\d+\]\s*)+', b['mu']) and b['size'] < 9:
            merged[-1]['mu'] += ' ' + b['mu'].strip()
        else: merged.append(b)
    blocks = merged
    diag_blocks = []
    if any(b['cls'] == 'diagram' for b in blocks):
        k = next(i for i, b in enumerate(blocks) if b['cls'] == 'diagram')
        diag_blocks, blocks, py_lines = blocks[k:], blocks[:k], py_lines[:k]
    aligned = len(py_lines) == len(blocks)
    if not aligned:
        print(f'WARN page {pno + 1}: pypdf lines {len(py_lines)} != mu lines {len(blocks)} -> pymupdf text', file=sys.stderr)

    lines = []
    n_mu_used = 0
    for i, b in enumerate(blocks):
        mu_txt = fix_mu(b['mu'], py_set, PY_GLOBAL)
        if b['cls'] == 'code':
            txt = (py_lines[i] if aligned else b['mu']).rstrip()
        elif aligned:
            py_txt = repair_py(py_lines[i], mu_set)
            lost = set(t for t in tokens(mu_txt) if len(t) > 1 and not re.fullmatch(r'[\W_]+', t)) - set(tokens(py_txt))
            if lost: txt = merge_lines(py_txt, mu_txt); n_mu_used += 1
            else: txt = py_txt
        else:
            txt = mu_txt
        lines.append(dict(y0=round(b['bbox'][1], 1), y1=round(b['bbox'][3], 1), x0=round(b['bbox'][0], 1), x1=round(b['bbox'][2], 1),
                          cls=b['cls'], font=b['font'], size=b['size'], text=txt))

    # --- tables: horizontal stroke segments are row boundaries; a fill directly above = header row ---
    drawings = p.get_drawings()
    segs = [(round(d['rect'].y0), round(d['rect'].x0), round(d['rect'].x1)) for d in drawings
            if d.get('fill') is None and d['rect'].height < 1 and d['rect'].width > 30]
    fills = [(round(d['rect'].x0), round(d['rect'].y0), round(d['rect'].x1), round(d['rect'].y1), d['fill']) for d in drawings if d.get('fill') is not None]
    groups = []
    for y in sorted(set(y for y, _, _ in segs)):
        if groups and y - groups[-1][-1] < 80: groups[-1].append(y)
        else: groups.append([y])
    py_raw = set(t for l in py_lines for t in split_bound(l).split())

    def cell_text(rect):
        t = fix_mu(p.get_text('text', clip=rect).replace('\n', ' '), py_set, PY_GLOBAL)
        toks = t.split(); tail = ''
        for i, tok in enumerate(toks):
            if tok == '.': toks[i] = ''; tail = '.'
            elif tok.endswith('.') and tok not in py_raw and i < len(toks) - 1: toks[i] = tok[:-1]; tail = '.'
        out = re.sub(r' +([،؛؟,.])', r'\1', re.sub(r'\s+', ' ', ' '.join(toks)).strip())
        out = re.sub(r'\( ', '(', re.sub(r' \)', ')', out))
        return out + (tail if tail and not out.endswith(('.', '؛', '،', '؟')) else '')

    tables = []
    for g in groups:
        if len(g) < 3: continue
        xs = sorted(set(x for y, x0, x1 in segs if y in g for x in (x0, x1)))
        cols = [xs[0]]
        for x in xs[1:]:
            if x - cols[-1] > 3: cols.append(x)
        header = False
        for x0, y0, x1, y1, fill in fills:
            if abs(y1 - g[0]) < 3 and y0 < g[0] - 5 and x0 >= cols[0] - 3 and x1 <= cols[-1] + 3:
                g.insert(0, y0); header = sum(fill[:3]) / 3 < 0.5; break
        rows = [[cell_text(pymupdf.Rect(cols[i], y0, cols[i + 1], y1)) for i in range(len(cols) - 1)] for y0, y1 in zip(g[:-1], g[1:])]
        tables.append(dict(cols=cols, bbox=[cols[0], g[0], cols[-1], g[-1]], rows=rows, header=header))

    def table_for(l):
        yc = (l['y0'] + l['y1']) / 2
        for t in tables:
            if t['bbox'][1] - 2 <= yc <= t['bbox'][3] + 2 and l['x0'] >= t['bbox'][0] - 5 and l['x1'] <= t['bbox'][2] + 5: return t
    new_lines, inserted = [], set()
    for l in lines:
        t = table_for(l)
        if t:
            if id(t) not in inserted:
                inserted.add(id(t)); new_lines.append(dict(cls='table', y0=t['bbox'][1], y1=t['bbox'][3], x0=0, x1=0, font='', size=0, text='', table=t))
            continue
        if l['cls'] == 'body' and re.fullmatch(r'\.?\d{1,2}\.?', l['text'].strip()): continue   # STEPS numbering
        new_lines.append(l)
    lines = [l for l in new_lines if l['cls'] in ('table', 'diagram') or l['text'].strip()]

    # --- diagram: render the region between the DIAGRAM label and its caption ---
    diagram = None
    if diag_blocks:
        lab = next(l for l in lines if l['cls'] == 'label' and l['text'] == 'DIAGRAM')
        cap = next(l for l in lines if l['cls'] == 'small' and l['y0'] > lab['y1'])
        rect = pymupdf.Rect(40, lab['y1'] + 4, 555, cap['y0'] - 2)
        pix = p.get_pixmap(matrix=pymupdf.Matrix(2.5, 2.5), clip=rect, alpha=False)
        diagram = dict(png=base64.b64encode(pix.tobytes('png')).decode(), caption=cap['text'])
        idx = lines.index(lab)
        lines.remove(cap)
        lines.insert(idx + 1, dict(cls='diagram', y0=lab['y1'], y1=cap['y0'], x0=0, x1=0, font='', size=0, text='', diagram=diagram))

    pages.append(dict(page=pno + 1, aligned=aligned, mu_lines_used=n_mu_used, lines=lines))

json.dump(pages, open(OUT, 'w'), ensure_ascii=False, indent=1)
print('pages', len(pages), 'aligned', sum(p['aligned'] for p in pages), 'lines from pymupdf', sum(p['mu_lines_used'] for p in pages))
