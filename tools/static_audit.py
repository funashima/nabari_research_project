#!/usr/bin/env python3
"""Source-level checks only. This does not replace browser/screen-reader QA."""
from html.parser import HTMLParser
from pathlib import Path
import json,re,subprocess,hashlib
ROOT=Path(__file__).resolve().parents[1]
class Page(HTMLParser):
    def __init__(self):super().__init__();self.ids=[];self.refs=[];self.lang=None;self.title=False;self.viewport=False
    def handle_starttag(self,tag,attrs):
        d=dict(attrs)
        if 'id' in d:self.ids.append(d['id'])
        if tag=='html':self.lang=d.get('lang')
        if tag=='title':self.title=True
        if tag=='meta' and d.get('name')=='viewport':self.viewport=True
        for attr in ('href','src'):
            if attr in d:self.refs.append(d[attr])
def luminance(hexcolor):
    rgb=[int(hexcolor[i:i+2],16)/255 for i in (1,3,5)]
    c=[x/12.92 if x<=.04045 else ((x+.055)/1.055)**2.4 for x in rgb]
    return sum(x*y for x,y in zip(c,(.2126,.7152,.0722)))
def contrast(a,b):
    x,y=sorted((luminance(a),luminance(b)));return(y+.05)/(x+.05)
def main():
    checks=[]
    def check(name,ok,detail=''):checks.append(dict(name=name,passed=bool(ok),detail=detail))
    for f in sorted((ROOT/'dist').glob('*.html')):
        p=Page();p.feed(f.read_text())
        check(f.name+': Japanese language / title / viewport',p.lang=='ja' and p.title and p.viewport)
        check(f.name+': unique static IDs',len(p.ids)==len(set(p.ids)))
        missing=[]
        for s in p.refs:
            if s.startswith(('#','http:','https:','data:','tel:','about:')):continue
            if not (f.parent/s.split('?')[0].split('#')[0]).exists():missing.append(s)
        check(f.name+': local asset references',not missing,', '.join(missing))
    for f in sorted((ROOT/'dist').glob('*.mjs')):
        r=subprocess.run(['node','--check',str(f)],capture_output=True,text=True)
        check(f.name+': JavaScript syntax',r.returncode==0,r.stderr.strip())
    css=(ROOT/'dist/style.css').read_text()
    themes={}
    for name,selector in [('normal',r':root \{([^}]+)'),('high',r':root\.high\{([^}]+)')]:
        themes[name]=dict(re.findall(r'--([a-z-]+):(#[0-9a-f]{3,6})',re.search(selector,css).group(1)))
    def expand(c):return '#'+''.join(v*2 for v in c[1:]) if len(c)==4 else c
    contrasts=[]
    for theme,t in themes.items():
        for fg,bg in [('ink','paper'),('muted','paper'),('blue','paper'),('blue','pale'),('muted','pale'),('alert','alert-bg')]:
            ratio=contrast(expand(t[fg]),expand(t[bg]));contrasts.append(dict(theme=theme,foreground=t[fg],background=t[bg],ratio=round(ratio,2)));check(f'{theme}: {fg}/{bg} text contrast >=4.5',ratio>=4.5)
    check('CSS includes keyboard focus rules',':focus-visible' in css)
    check('CSS includes responsive breakpoint','@media(max-width:700px)' in css)
    check('CSS includes print stylesheet','@media print' in css)
    check('App renders source text with escaping',"escapeHTML as e" in (ROOT/'dist/app.mjs').read_text())
    data=(ROOT/'dist/data/information.json').read_bytes()
    report={'scope':'SOURCE_ONLY_NOT_BROWSER_QA','checks':checks,'passed':sum(c['passed'] for c in checks),'total':len(checks),'textContrastPairs':contrasts,'datasetSha256':hashlib.sha256(data).hexdigest(),'unverified':['Browser rendering at desktop/mobile widths and 200% zoom','Keyboard focus behavior in real browser','Screen-reader announcements','Japanese speech playback','Print dialog output','WebMCP in a supported browser']}
    (ROOT/'results').mkdir(exist_ok=True);(ROOT/'results/static_audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:report[k] for k in ('scope','passed','total','datasetSha256')},indent=2));raise SystemExit(0 if all(c['passed']for c in checks) else 1)
if __name__=='__main__':main()
