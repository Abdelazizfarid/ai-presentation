"""Build index.html (Arabic explainer guide) from guide.json produced by extract_guide.py"""
import json, re, html, sys

SRC = sys.argv[1] if len(sys.argv) > 1 else 'guide.json'
OUT = sys.argv[2] if len(sys.argv) > 2 else 'index.html'
pages = json.load(open(SRC))

LABELS = {'EXPLANATION': 'الشرح', 'EXAMPLE': 'مثال تقني', 'REAL-LIFE EXAMPLE': 'مثال من الحياة', 'TAKEAWAY': 'الخلاصة', 'DETAILS': 'تفاصيل', 'STEPS': 'الخطوات',
          'COMPARISON': 'مقارنة', 'CODE': 'كود', 'DIAGRAM': 'رسم توضيحي'}
SECTION_AR = {'INTRODUCTION': 'مقدمة', 'INTELLIGENCE': 'الذكاء', 'ADOPTION': 'الانتشار', 'MODELS & TOOLS': 'الـmodels والـtools',
              'PROMPT ENGINEERING': 'الـprompt engineering', 'AGENT WORKFLOWS': 'الـagent workflows', 'AUTOMATION PLATFORMS': 'منصات الـautomation',
              'RISK & ROLLOUT': 'المخاطر والتطبيق', 'CLAUDE CODE': 'Claude Code', 'OPEN AGENTS': 'الـopen agents', 'SOURCES': 'المصادر'}

def item_id_of(it):
    if it['kind'] == 'slide': return f"slide-{it['num']:02d}"
    if it['kind'] == 'mcp': return it['num']
    return {'intro': 'intro', 'glossary': 'glossary', 'refs': 'references'}.get(it['kind'], 'misc')


SKIP_SLIDES = {13, 16, 26, 27, 28, 29, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45, 48, 51, 52, 53, 54, 55, 56, 57, 58, 59, 60, 61, 62, 63, 64, 65, 66, 67, 68, 69, 70}  # removed from the deck too

# ---------------------------------------------------------------- assemble items
items = []
cur = blk = None


def new_item(kind, **kw):
    global cur, blk
    cur = dict(kind=kind, title='', blocks=[], **kw)
    blk = None
    items.append(cur)


def new_block(label):
    global blk
    blk = dict(label=label, content=[])
    cur['blocks'].append(blk)


for page in pages:
    pn = page['page']
    if pn in (1, 3): continue                     # cover (hard-coded hero) and table of contents (regenerated)
    last = None
    for l in page['lines']:
        c = l['cls']
        if c == 'kicker':
            m = re.match(r'SLIDE (\d+) / (.+)', l['text'])
            if m:
                num = int(m.group(1))
                if num in SKIP_SLIDES:
                    cur = dict(kind='skip', title='', blocks=[]); blk = None; last = None; continue
                shift = sum(1 for k in SKIP_SLIDES if k < num)
                new_item('slide', num=num - shift, section=m.group(2).strip(), kicker=f'SLIDE {num - shift:02d} / {m.group(2).strip()}')
            elif l['text'].startswith('MCP DEEP DIVE'):
                new_item('mcp', num=l['text'].split('/')[-1].strip(), section='MCP DEEP DIVE', kicker=l['text'])
            elif l['text'].startswith('READING GUIDE'): new_item('intro', section='READING GUIDE', kicker=l['text'])
            elif l['text'].startswith('QUICK REFERENCE'):
                if not (cur and cur['kind'] == 'glossary'): new_item('glossary', section='GLOSSARY', kicker=l['text'])
            elif l['text'].startswith('SOURCES'): cur = dict(kind='skip', title='', blocks=[]); blk = None; last = None; continue
            else: new_item('misc', section=l['text'], kicker=l['text'])
            last = None
        elif c == 'title':
            if cur['title'] and cur['kind'] != 'glossary':
                if not blk: new_block(None)
                blk['content'].append(dict(type='h3', text=l['text']))
            elif not cur['title']: cur['title'] = 'Glossary' if cur['kind'] == 'glossary' else l['text']
            last = None
        elif c == 'label':
            new_block(l['text']); last = None
        elif c in ('body', 'bold', 'small'):
            if blk is None: new_block(None)
            prev = blk['content'][-1] if blk['content'] else None
            same_para = (prev and prev['type'] == 'p' and last and last['cls'] == c and pn == last['page']
                         and 0 < l['y0'] - last['y0'] < 20.5)
            if same_para: prev['text'] += ' ' + l['text']
            else: blk['content'].append(dict(type='p', text=l['text'], cls=c))
            last = dict(cls=c, y0=l['y0'], page=pn, size=l['size'])
        elif c == 'code':
            if blk is None: new_block('CODE')
            prev = blk['content'][-1] if blk['content'] else None
            if prev and prev['type'] == 'code' and last and last['cls'] == 'code' and l['y0'] - last['y0'] < 16:
                prev['lines'].append(l['text'])
            else: blk['content'].append(dict(type='code', lines=[l['text']]))
            last = dict(cls='code', y0=l['y0'], page=pn, size=l['size'])
        elif c == 'table':
            if blk is None: new_block(None)
            blk['content'].append(dict(type='table', **l['table'])); last = None
        elif c == 'diagram':
            if blk is None: new_block('DIAGRAM')
            blk['content'].append(dict(type='img', **l['diagram'])); last = None

# real-life examples (content/real_examples.json: id -> Arabic text), inserted after EXAMPLE
import os
def remap(d):
    out = {}
    for k, v in d.items():
        m = re.match(r'slide-(\d+)$', k)
        if m:
            n = int(m.group(1))
            if n in SKIP_SLIDES: continue
            k = f'slide-{n - sum(1 for x in SKIP_SLIDES if x < n):02d}'
        out[k] = v
    return out
REAL = remap(json.load(open('content/real_examples.json'))) if os.path.exists('content/real_examples.json') else {}
for it in items:
    if it['kind'] not in ('slide', 'mcp'): continue
    txt = REAL.get(item_id_of(it))
    if not txt: continue
    blk_new = dict(label='REAL-LIFE EXAMPLE', content=[dict(type='p', text=txt, cls='body')])
    labels = [b['label'] for b in it['blocks']]
    pos = labels.index('EXAMPLE') + 1 if 'EXAMPLE' in labels else (labels.index('TAKEAWAY') if 'TAKEAWAY' in labels else len(labels))
    it['blocks'].insert(pos, blk_new)

# per-slide extras (content/extras.json: id -> [ {label, text} | {label, table:{header,rows}} ]); inserted after EXPLANATION.
# an extra with a label that already exists on the slide REPLACES that block.
EXTRAS = remap(json.load(open('content/extras.json'))) if os.path.exists('content/extras.json') else {}
for it in items:
    if it['kind'] not in ('slide', 'mcp'): continue
    for ex in EXTRAS.get(item_id_of(it), []):
        if 'table' in ex:
            content = [dict(type='table', header=True, rows=[list(reversed(ex['table']['header']))] + [list(reversed(r)) for r in ex['table']['rows']])]
        else:
            content = [dict(type='p', text=ex['text'], cls='body')]
        blk_new = dict(label=ex['label'], content=content)
        labels = [b['label'] for b in it['blocks']]
        if ex['label'] in labels:
            it['blocks'][labels.index(ex['label'])] = blk_new
        else:
            pos = labels.index('EXPLANATION') + 1 if 'EXPLANATION' in labels else 0
            it['blocks'].insert(pos, blk_new)

# intro: replace the source's verification-scope note (specifics were removed from the guide)
for it in items:
    if it['kind'] != 'intro': continue
    for b in it['blocks']:
        for e in b['content']:
            if e['type'] == 'p' and 'independently verified' in e['text']:
                e['text'] = 'نطاق التحقق: الشرح مبني على الـdeck المرفقة. آليات الـMCP وبعض تفاصيل الـproducts اتراجعت بمصادر رسمية، أسماء الـmodels والتواريخ والأسعار والأرقام اللي ماقدرناش نتأكد منها اتشالت من الشرح، والفكرة نفسها فضلت زي ما هي.'

# references: "[Rn] Title" paragraph followed by a URL paragraph
for it in items:
    if it['kind'] != 'refs': continue
    for b in it['blocks']:
        out, i = [], 0
        while i < len(b['content']):
            e = b['content'][i]
            m = e['type'] == 'p' and re.match(r'^\[R(\d+)\]\s*(.+?)\s*(https?://\S+)$', e['text'])
            if m: out.append(dict(type='ref', id='R' + m.group(1), title=m.group(2), url=m.group(3)))
            else: out.append(e)
            i += 1
        b['content'] = out

# ---------------------------------------------------------------- render helpers
def esc(s): return html.escape(s, quote=False)


def inline(text):
    t = esc(text).replace('».»', '».')
    t = re.sub(r'\s*\[R\d+\]', '', t)
    t = re.sub(r'\b(M(?:0[1-9]|1[0-4]))\b', r'<a class="xref" href="#\1">\1</a>', t)
    t = re.sub(r'\b[Ss]lide (\d{1,2})\b', lambda m: f'<a class="xref" href="#slide-{int(m.group(1)):02d}">{m.group(0)}</a>', t)
    return t


def item_id(it):
    if it['kind'] == 'slide': return f"slide-{it['num']:02d}"
    if it['kind'] == 'mcp': return it['num']
    return {'intro': 'intro', 'glossary': 'glossary', 'refs': 'references'}.get(it['kind'], 'misc')


SENT_END = re.compile(r'(?<=[.؟!])\s+(?=\S)')
BULLET_LABELS = set()   # paragraphs, not bullets (user request)


def sentences(text):
    parts = SENT_END.split(text.strip())
    out = []
    for p in parts:
        if out and re.fullmatch(r'(\[R\d+\]\s*)+', p): out[-1] += ' ' + p      # keep [R1] with its sentence
        elif out and len(p) < 12: out[-1] += ' ' + p                                # tiny fragment -> join
        else: out.append(p)
    return out


def sentence_html(sent):
    """one bullet; 'lead: A، و B، و C' becomes lead + nested bullets"""
    m = re.match(r'^(.{6,}?):\s+(.+)$', sent)
    if m and m.group(2).count('، و') >= 2:
        items = [i.strip(' ،') for i in re.split(r'،\s*و(?=\s)', m.group(2)) if i.strip(' ،')]
        items = [re.sub(r'^و\s+', '', i) for i in items]
        return f'{inline(m.group(1))}:<ul>' + ''.join(f'<li>{inline(i)}</li>' for i in items) + '</ul>'
    return inline(sent)


def bullets(text):
    sents = sentences(text)
    if len(sents) == 1 and ':' not in sents[0]:
        return f'<p>{inline(sents[0])}</p>'
    return '<ul>' + ''.join(f'<li>{sentence_html(x)}</li>' for x in sents) + '</ul>'


def render_content(e, label):
    if e['type'] == 'p':
        if label in BULLET_LABELS and e.get('cls') != 'bold':
            return bullets(e['text'])
        return f'<p>{inline(e["text"])}</p>'
    if e['type'] == 'h3':
        return f'<h3 dir="auto">{esc(e["text"])}</h3>'
    if e['type'] == 'code':
        return f'<pre dir="ltr"><code>{esc(chr(10).join(e["lines"]))}</code></pre>'
    if e['type'] == 'img':
        return f'<figure><img src="data:image/png;base64,{e["png"]}" alt="{esc(e["caption"])}"><figcaption dir="auto">{esc(e["caption"])}</figcaption></figure>'
    if e['type'] == 'table':
        rows = [list(reversed(r)) for r in e['rows']]          # visual L->R cells -> logical RTL order
        out = ['<div class="tbl"><table>']
        if e['header']:
            out.append('<thead><tr>' + ''.join(f'<th>{inline(c)}</th>' for c in rows[0]) + '</tr></thead>'); rows = rows[1:]
        out.append('<tbody>' + ''.join('<tr>' + ''.join(f'<td>{inline(c)}</td>' for c in r) + '</tr>' for r in rows) + '</tbody></table></div>')
        return ''.join(out)
    return ''


def render_block(b):
    label = b['label']
    body = []
    if label == 'STEPS':
        body.append('<ol>' + ''.join(f'<li>{inline(e["text"])}</li>' for e in b['content'] if e['type'] == 'p') + '</ol>')
        body += [render_content(e, label) for e in b['content'] if e['type'] != 'p']
    else:
        body = [render_content(e, label) for e in b['content']]
    cls = 'blk' + (f' blk-{label.lower().replace(" ", "-")}' if label else '')
    head = f'<div class="lbl"><span class="en">{esc(label)}</span><span class="ar">{LABELS.get(label, "")}</span></div>' if label else ''
    return f'<div class="{cls}">{head}{"".join(body)}</div>'


def render_item(it):
    kicker = it.get('kicker', '')
    return (f'<article class="item item-{it["kind"]}" id="{item_id(it)}">'
            f'<div class="kicker">{esc(kicker)}</div>'
            f'<h2 dir="auto">{esc(it["title"])}</h2>'
            + ''.join(render_block(b) for b in it['blocks']) + '</article>')


# ---------------------------------------------------------------- nav
sections = []
for it in items:
    if it['kind'] in ('slide', 'mcp'):
        if not sections or sections[-1]['name'] != it['section']: sections.append(dict(name=it['section'], items=[]))
        sections[-1]['items'].append(it)
nav = ['<nav class="toc"><div class="toc-title">المحتويات</div>',
       '<a class="toc-top" href="#intro">إزاي تستخدم الدليل ده</a>']
for s in sections:
    nav.append(f'<details open><summary>{esc(s["name"].title() if s["name"] != "MCP DEEP DIVE" else "MCP Deep Dive")}'
               f'<span class="ar">{SECTION_AR.get(s["name"], "")}</span></summary><ul>')
    for it in s['items']:
        num = f'{it["num"]:02d}' if it['kind'] == 'slide' else it['num']
        nav.append(f'<li><a href="#{item_id(it)}"><b>{num}</b> {esc(it["title"])}</a></li>')
    nav.append('</ul></details>')
nav.append('<a class="toc-top" href="#glossary">Glossary · مصطلحات</a>')
nav.append('<a class="toc-top ext" href="presentation.html" target="_blank">افتح الـpresentation ↗</a></nav>')

# ---------------------------------------------------------------- page
main = []
for it in items:
    if it['kind'] in ('slide', 'mcp'):
        first = next((s for s in sections if s['items'] and s['items'][0] is it), None)
        if first:
            main.append(f'<h1 class="sec" id="sec-{re.sub(r"[^a-z0-9]+", "-", first["name"].lower())}" dir="auto">{esc(first["name"].title() if first["name"] != "MCP DEEP DIVE" else "MCP Deep Dive")}'
                        f'<span class="ar">{SECTION_AR.get(first["name"], "")}</span></h1>')
    main.append(render_item(it))

CSS = r"""
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+Arabic:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500&display=swap');
:root{--paper:#F7F5F0;--ink:#1B1C20;--muted:#6B6E76;--line:#E2DED5;--teal:#163F50;--teal-2:#22596F;--accent:#C8552A;--tint:#EEF3F5;--card:#FFFFFF;--code:#1B1C20;}
*{box-sizing:border-box}
html{scroll-behavior:smooth;scroll-padding-top:16px}
body{margin:0;background:var(--paper);color:var(--ink);font-family:'IBM Plex Sans Arabic','Segoe UI',Tahoma,Arial,sans-serif;font-size:17px;line-height:1.95;}
a{color:var(--teal-2)}
.hero{background:var(--teal);color:#fff;padding:56px 32px 44px;}
.hero .in{max-width:1180px;margin:0 auto;display:grid;grid-template-columns:1.2fr 1fr;gap:32px;align-items:end}
.hero .kicker{direction:ltr;text-align:left;color:#F3B08F;letter-spacing:.18em;font-size:12px;font-family:'IBM Plex Mono',monospace;text-transform:uppercase}
.hero h1{text-align:left;font-size:clamp(40px,6vw,72px);line-height:1.05;margin:10px 0 18px;font-weight:700;letter-spacing:-.02em}
.hero .sub{font-size:clamp(22px,3vw,30px);font-weight:600;margin:0 0 10px}
.hero .desc{font-size:17px;opacity:.85;max-width:560px;margin:0}
.hero .badges{display:flex;flex-direction:column;gap:10px;text-align:left}
.hero .badge{border:1px solid rgba(255,255,255,.28);padding:10px 14px;font-family:'IBM Plex Mono',monospace;font-size:12px;letter-spacing:.12em;text-transform:uppercase}
.hero .meta{grid-column:1/-1;border-top:1px solid rgba(255,255,255,.2);padding-top:16px;display:flex;justify-content:space-between;font-size:13px;opacity:.75;font-family:'IBM Plex Mono',monospace;flex-wrap:wrap;gap:8px}
.wrap{max-width:1180px;margin:0 auto;display:grid;grid-template-columns:280px minmax(0,1fr);gap:40px;padding:32px 24px 80px}
.toc{position:sticky;top:16px;align-self:start;max-height:calc(100vh - 32px);overflow:auto;font-size:13.5px;line-height:1.6;padding-inline-end:8px}
.toc-title{font-weight:700;font-size:15px;margin-bottom:8px}
.toc details{border-top:1px solid var(--line);padding:6px 0}
.toc summary{cursor:pointer;font-weight:600;font-family:'IBM Plex Mono',monospace;font-size:12px;letter-spacing:.06em;text-transform:uppercase;color:var(--teal)}
.toc summary .ar{font-family:'IBM Plex Sans Arabic','Segoe UI',Tahoma,Arial,sans-serif;font-weight:500;text-transform:none;letter-spacing:0;color:var(--muted);margin-inline-start:8px;font-size:12.5px}
.toc ul{list-style:none;margin:4px 0 0;padding:0}
.toc li a{display:block;padding:2px 6px;color:var(--ink);text-decoration:none;border-radius:4px;direction:ltr;text-align:left}
.toc li a:hover{background:var(--tint)}
.toc li b{color:var(--accent);font-family:'IBM Plex Mono',monospace;font-weight:500;font-size:11.5px;margin-inline-end:6px}
.toc-top{display:block;padding:6px;color:var(--teal);font-weight:600;text-decoration:none}
.toc-top.ext{color:var(--accent)}
main{min-width:0}
h1.sec{font-size:30px;margin:48px 0 16px;padding-bottom:10px;border-bottom:3px solid var(--teal);color:var(--teal);direction:ltr;text-align:left}
h1.sec:first-child{margin-top:0}
h1.sec .ar{font-size:17px;color:var(--muted);font-weight:500;margin-left:14px;direction:rtl;display:inline-block}
.item{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:28px 30px 20px;margin:0 0 22px;box-shadow:0 1px 2px rgba(0,0,0,.03)}
.item .kicker{font-family:'IBM Plex Mono',monospace;font-size:11.5px;letter-spacing:.16em;color:var(--accent);text-transform:uppercase;direction:ltr;text-align:left}
.item h2{font-size:26px;line-height:1.25;margin:6px 0 18px;letter-spacing:-.01em;direction:ltr;text-align:left}
.item h3{font-size:19px;margin:22px 0 8px;direction:ltr;text-align:left}
.blk{margin:0 0 18px}
.lbl{display:flex;gap:10px;align-items:baseline;margin-bottom:4px}
.lbl .en{font-family:'IBM Plex Mono',monospace;font-size:11px;letter-spacing:.16em;color:var(--teal);font-weight:600}
.lbl .ar{font-size:14px;color:var(--muted);font-weight:500}
.blk p{margin:0 0 12px;line-height:2.05;text-align:justify}
.blk-real-life-example{background:#FBF4EE;border-inline-start:4px solid var(--accent);padding:14px 18px 4px;border-radius:6px}
.blk-real-life-example .lbl .en{color:var(--accent)}
.blk-takeaway{background:var(--tint);border-inline-start:4px solid var(--teal);padding:14px 18px 6px;border-radius:6px}
.blk-takeaway p{font-weight:600}
.blk ol{margin:0 0 12px;padding-inline-start:26px}
.blk ol li{margin-bottom:6px}
.blk ul{margin:0 0 14px;padding-inline-start:22px;list-style:none}
.blk ul li{position:relative;margin-bottom:7px;padding-inline-start:4px}
.blk ul li::before{content:'';position:absolute;inset-inline-start:-16px;top:.85em;width:7px;height:7px;border-radius:50%;background:var(--accent)}
.blk ul ul{margin:4px 0 2px;padding-inline-start:20px}
.blk ul ul li::before{width:5px;height:5px;background:var(--teal-2);top:.9em}
pre{background:var(--code);color:#F3F1EA;padding:16px 18px;border-radius:8px;overflow:auto;font-family:'IBM Plex Mono',monospace;font-size:13.5px;line-height:1.6;margin:8px 0 14px;text-align:left}
.tbl{overflow:auto;margin:6px 0 14px}
table{border-collapse:collapse;width:100%;font-size:15px;line-height:1.6}
th,td{border:1px solid var(--line);padding:9px 12px;vertical-align:top;text-align:start}
th{background:var(--teal);color:#fff;font-weight:600}
tbody tr:nth-child(even){background:#FAF9F6}
td:first-child{font-weight:600;white-space:nowrap}
figure{margin:8px 0 14px;text-align:center}
figure img{max-width:100%;height:auto;border:1px solid var(--line);border-radius:8px;background:#fff}
figcaption{font-size:13px;color:var(--muted);margin-top:6px}
a.ref{font-family:'IBM Plex Mono',monospace;font-size:12px;text-decoration:none;color:var(--accent);vertical-align:super}
a.xref{text-decoration:none;border-bottom:1px dotted var(--teal-2)}
.item-refs .refs{list-style:none;padding:0;margin:0}
.item-refs .refs li{padding:8px 0;border-bottom:1px solid var(--line);direction:ltr;text-align:left}
.item-refs .refs b{font-family:'IBM Plex Mono',monospace;color:var(--accent);font-weight:500;margin-right:8px}
.item-refs .refs a{word-break:break-all;font-size:14px}
.item-glossary td:first-child{width:22%}
footer{max-width:1180px;margin:0 auto;padding:0 24px 40px;color:var(--muted);font-size:13px;font-family:'IBM Plex Mono',monospace;direction:ltr;text-align:left}
@media (max-width:900px){.wrap{grid-template-columns:1fr;gap:20px}.toc{position:static;max-height:none;background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px}.hero .in{grid-template-columns:1fr}.item{padding:20px 18px 12px}body{font-size:16px}}
@media print{.toc,.toc-top{display:none}.wrap{display:block;padding:0}.item{break-inside:avoid;box-shadow:none}.hero{-webkit-print-color-adjust:exact;print-color-adjust:exact}}
"""

# references rendering override (list layout)
def render_refs(it):
    out = [f'<article class="item item-refs" id="references"><div class="kicker">{esc(it["kicker"])}</div><h2 dir="auto">{esc(it["title"])}</h2>']
    for b in it['blocks']:
        paras = [e for e in b['content'] if e['type'] == 'p']
        refs = [e for e in b['content'] if e['type'] == 'ref']
        pre = [e for e in b['content'] if e['type'] == 'p' and b['content'].index(e) < (b['content'].index(refs[0]) if refs else 0)]
        out += [f'<p>{inline(e["text"])}</p>' for e in pre]
        if refs:
            out.append('<ul class="refs">' + ''.join(f'<li id="ref-{r["id"]}"><b>[{r["id"]}]</b>{esc(r["title"])}<br><a href="{esc(r["url"])}" target="_blank" rel="noopener">{esc(r["url"])}</a></li>' for r in refs) + '</ul>')
        out += [f'<p class="note">{inline(e["text"])}</p>' for e in paras if e not in pre]
    return ''.join(out) + '</article>'

main = []
for it in items:
    if it['kind'] in ('slide', 'mcp'):
        first = next((s for s in sections if s['items'] and s['items'][0] is it), None)
        if first:
            nm = first['name'].title() if first['name'] != 'MCP DEEP DIVE' else 'MCP Deep Dive'
            main.append(f'<h1 class="sec" id="sec-{re.sub(r"[^a-z0-9]+", "-", first["name"].lower())}">{esc(nm)}<span class="ar">{SECTION_AR.get(first["name"], "")}</span></h1>')
    main.append(render_refs(it) if it['kind'] == 'refs' else render_item(it))

HERO = """<header class="hero"><div class="in">
<div><div class="kicker">Engineering Field Guide / 2026</div>
<h1 dir="ltr">AI in<br>Development</h1>
<p class="sub">شرح تفصيلي بالعامية المصرية</p>
<p class="desc">لكل الـ70 slides، مع examples من Odoo والـAPIs، وشرح موسّع للـMCP خطوة بخطوة.</p></div>
<div class="badges" dir="ltr"><div class="badge">70 slides explained</div><div class="badge">14 MCP deep-dive chapters</div><div class="badge">Arabic explanation / English terminology</div></div>
<div class="meta" dir="ltr"><span>Prepared for Abdelaziz Farid</span><span>14 September 2026</span></div>
</div></header>"""

doc = f"""<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>AI in Development — شرح بالعامية المصرية</title>
<style>{CSS}</style>
</head>
<body>
{HERO}
<div class="wrap">
{''.join(nav)}
<main>
{''.join(main)}
</main>
</div>
<footer>AI in Development / Explainer · Abdelaziz Farid · September 2026 · <a href="AI-Development-Arabic-Guide.pdf">PDF version</a></footer>
</body>
</html>"""
open(OUT, 'w').write(doc)
print('items', len(items), 'sections', [s['name'] for s in sections], 'bytes', len(doc))
