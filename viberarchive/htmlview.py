"""Static HTML viewer: one page per chat and month, in the look of the Viber app, for comparing with the real thing.

    python archive.py html --archive archive/archive.db --out site

Writes site/index.html (chats, and a month grid per chat), site/<chat>/<YYYY-MM>.html, style.css and app.js. Nothing is
loaded from the network; open index.html in a browser. Media is not embedded: a photo, video or file shows as a labelled
placeholder with its caption and original file name.
"""
import html
import json
import os
import re
import shutil
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import emoticons, schema

TZ = timezone(timedelta(hours=7))
REACTIONS = {1: "💙", 2: "\U0001F602", 3: "\U0001F62E", 4: "\U0001F622", 5: "\U0001F621", 6: "\U0001F44D"}
PICTURE_EXT = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".heic"}
MOVIE_EXT = {".mp4", ".mov", ".3gp", ".mkv", ".webm"}
KIND_LABEL = {"image": "Photo", "video": "Video", "file": "File", "voice": "Voice message", "sticker": "Sticker",
              "link": "Link", "system": "System message", "reaction": "Reaction"}
MONTH_NAMES = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
               "November", "December"]
SHOWN_FLAGS = ("resent_superseded", "edit_ref_missing", "status_129", "tick_unknown", "time_is_delivery",
               "phone_time_fixed", "no_token")
URL_RE = re.compile(r"(https?://[^\s<]+)")

CSS = """
:root{--bg:#001121;--panel:#0b1c2f;--in:#1f242b;--out:#5345ae;--text:#f2f2f8;--dim:#a3a4be;--accent:#9b8cff;
--pill:#34355052;--warn:#ffb454}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);font:14px/1.2 "Segoe UI",system-ui,-apple-system,sans-serif}
a{color:var(--accent)}
header.top{position:sticky;top:0;z-index:5;background:var(--panel);padding:8px 14px;display:flex;flex-wrap:wrap;
gap:10px;align-items:center;border-bottom:1px solid #00000040}
header.top h1{font-size:16px;margin:0 8px 0 0}
header.top a.nav{text-decoration:none;padding:4px 10px;border-radius:14px;background:var(--in);color:var(--text)}
header.top select,header.top input{background:var(--in);color:var(--text);border:0;border-radius:14px;padding:4px 10px}
header.top label{color:var(--dim);font-size:13px}
main{padding:12px 0 60px}
.day{text-align:center;margin:18px 0 8px}
.day span{background:var(--in);color:var(--dim);padding:3px 12px;border-radius:12px;font-size:13px}
.row{position:relative;display:flex;margin:2.8px 0;padding:0 max(16px,calc((100% - 740px) / 2));content-visibility:auto;contain-intrinsic-size:auto 44px}
.row.out{justify-content:flex-end}
.bubble{position:relative;max-width:78%;padding:8px 12px 7px;border-radius:14px;background:var(--in);
word-wrap:break-word;overflow-wrap:anywhere}
.row.out .bubble{background:var(--out)}
.row.first.in .bubble{border-top-left-radius:2px}
.row.first.out .bubble{border-top-right-radius:2px}
.who{font-size:12px;color:var(--accent);margin-bottom:1px}
.txt{white-space:pre-wrap}
.meta{font-size:12px;line-height:15px;height:15px;color:#ffffffa8;margin-top:12px;white-space:nowrap;
display:flex;justify-content:flex-end;align-items:center}
.row.in .meta{color:var(--dim)}
.tick{margin-left:4px;letter-spacing:-3px}
.tick.sent{color:#ffffff80}
.tick.seen{color:#53d2fa}
.edited{font-size:11px;color:#ffffffb0;margin-right:6px}
.side{display:flex;align-items:center;gap:3px;margin:0 5px;align-self:center}
.react{background:var(--panel);border:1px solid #00000050;border-radius:11px;padding:0 6px;font-size:13px;
white-space:nowrap}
.react-img{height:1.2em;width:1.2em;vertical-align:-0.25em}
.react-btn{display:flex;align-items:center;justify-content:center;width:26px;height:26px;border-radius:50%;
background:#ffffff14;color:#ffffff80;font-size:15px;line-height:1}
.seen-img{height:12px;width:auto;margin-left:4px}
.bubble.hasmedia{padding:4px 6px 3px}
.bubble.hasmedia .txt{padding:2px 4px 0}
.bubble.hasmedia .meta{padding-right:4px}
.quote b{display:block;font-weight:600}
.quote{border-left:3px solid var(--accent);padding:2px 8px;margin:0 0 5px;background:#00000026;border-radius:4px;
font-size:13px;color:#ffffffd0;max-height:3.9em;overflow:hidden}
.row.bare .bubble{background:none;padding:0;display:flex;flex-direction:column}
.row.bigq .bubble{display:flex;flex-direction:column}
.row.bigq.out .emoji-pic,.row.bigq.out .stk,.row.bigq.out .big{align-self:flex-end}
.row.bigq.in .emoji-pic,.row.bigq.in .stk,.row.bigq.in .big{align-self:flex-start}
.row.bigq .meta{align-self:flex-end}
.row.bare.out .bubble{align-items:flex-end}
.row.bare.in .bubble{align-items:flex-start}
.row.bare .meta{display:inline-block;background:#00000070;border-radius:10px;padding:1px 9px;margin-top:4px;color:#fff}
.big{font-size:50px;line-height:1.15;text-align:center}
.emo{height:1.5em;width:1.5em;vertical-align:-0.35em}
.stk{display:block;width:100px;height:100px;object-fit:contain}
.emoji-pic{display:block;width:60px;height:60px;object-fit:contain}
.pic{display:block;max-width:100%;max-height:360px;border-radius:10px;margin-bottom:2px}
.media{background:#00000030;border-radius:10px;padding:14px 16px;margin-bottom:4px;text-align:center;font-size:13px}
.media small{display:block;color:var(--dim);word-break:break-all}
.system{text-align:center;color:var(--dim);font-size:13px;margin:6px 0}
.src{display:none;position:absolute;top:50%;margin-top:-5px;width:10px;height:10px;border-radius:50%}
.row.out .src{right:calc(max(16px,(100% - 740px) / 2) - 14px)}
.row.in .src{left:calc(max(16px,(100% - 740px) / 2) - 14px)}
body.markers .src{display:block}
.src.pc{background:#4fc3f7}.src.phone{background:#ffb454}
.legend{display:none;font-size:12px;color:var(--dim)}
body.markers .legend{display:inline}
body.verify .alt{display:block}
.row.superseded{display:none}
body.verify .row.superseded{display:flex;opacity:.4}
.alt{display:none;font-size:10px;color:#ffffff80;text-align:right}
.flag{font-size:10px;color:var(--warn);text-align:right}
div.gridwrap{overflow-x:auto}
table.grid{border-collapse:collapse;margin:8px 0 22px}
table.grid th,table.grid td{padding:4px 8px;text-align:center;font-size:13px}
table.grid td a{display:block;padding:2px 6px;border-radius:6px;text-decoration:none;color:var(--text);background:var(--in)}
table.grid td.pc a{outline:2px solid #4fc3f7}table.grid td.phone a{outline:2px solid #ffb454}
.day{scroll-margin-top:90px}
#floatday{position:fixed;left:50%;transform:translateX(-50%);z-index:4;background:#000000a0;color:#fff;padding:3px 14px;
border-radius:12px;font-size:13px;pointer-events:none}
.datebtn{background:var(--in);color:var(--text);border:0;border-radius:14px;padding:4px 12px;cursor:pointer;font:inherit}
.cal{display:none;position:absolute;top:100%;left:14px;z-index:9;background:var(--panel);border:1px solid #ffffff20;
border-radius:12px;padding:10px;width:280px;box-shadow:0 8px 24px #000a}
.cal.open{display:block}
.calhead{display:flex;justify-content:space-between;align-items:center;margin-bottom:6px}
.calhead a,.calfoot a{cursor:pointer;color:var(--accent);padding:2px 8px;border-radius:8px;user-select:none}
.calgrid{display:grid;grid-template-columns:repeat(7,1fr);gap:2px;text-align:center}
.calgrid i{font-style:normal;color:var(--dim);font-size:11px}
.calday{position:relative;padding:6px 0 9px;border-radius:8px;cursor:pointer;color:var(--text)}
.calday:hover{background:var(--in)}
.calday.empty{color:#ffffff40;cursor:default}.calday.empty:hover{background:none}
.calday.cur{outline:2px solid var(--accent)}
.cal u{display:inline-block;width:6px;height:6px;border-radius:50%;text-decoration:none}
.calday u{position:absolute;bottom:3px}
.calday u.pc{left:calc(50% - 7px)}.calday u.ph{left:calc(50% + 1px)}
.cal u.pc{background:#4fc3f7}.cal u.ph{background:#ffb454}
.calfoot{display:flex;justify-content:space-between;margin-top:8px;font-size:12px}
.callegend{margin-top:6px;font-size:11px;color:var(--dim)}
.cards a{display:block;background:var(--panel);padding:10px 14px;margin:6px 0;border-radius:10px;
text-decoration:none;color:var(--text)}
.cards small{color:var(--dim)}
.srch{width:200px}
.results{display:none;position:fixed;top:56px;left:50%;transform:translateX(-50%);width:min(720px,calc(100% - 24px));
max-height:72vh;overflow:auto;z-index:8;background:var(--panel);border:1px solid #ffffff20;border-radius:12px;
box-shadow:0 8px 24px #000a;padding:6px}
.results.open{display:block}
.rhead{display:flex;justify-content:space-between;gap:10px;padding:6px 10px;color:var(--dim);font-size:12px}
.rhead label{cursor:pointer}
.res{display:block;padding:7px 10px;border-radius:8px;cursor:pointer;color:var(--text);text-decoration:none}
.res:hover,.res.sel{background:var(--in)}
.res small{display:block;color:var(--dim);font-size:11px}
.res mark{background:#f5c54299;color:#fff;border-radius:3px;padding:0 1px}
.rmore{display:block;margin:6px auto;background:var(--in);color:var(--text);border:0;border-radius:14px;padding:5px 16px;cursor:pointer}
.row.hit .bubble{outline:2px solid #f5c542;outline-offset:2px}
"""


JS = """
(function(){
var d=document, b=d.body, cfg=window.CHAT||{};
function save(k,v){try{localStorage.setItem(k,v?'1':'0')}catch(e){}}
function load(k){try{return localStorage.getItem(k)==='1'}catch(e){return false}}
var m=d.getElementById('markers'), v=d.getElementById('verify');
if(m){m.checked=load('markers');b.classList.toggle('markers',m.checked);
 m.onchange=function(){b.classList.toggle('markers',m.checked);save('markers',m.checked)}}
if(v){v.checked=load('verify');b.classList.toggle('verify',v.checked);
 v.onchange=function(){b.classList.toggle('verify',v.checked);save('verify',v.checked)}}
var clk=d.getElementById('clock'), h24=false;
try{h24=localStorage.getItem('clock')==='24'}catch(e){}
function p2(n){return (n<10?'0':'')+n}
function times(){d.querySelectorAll('time[data-ms]').forEach(function(e){
 var t=new Date(+e.dataset.ms+25200000), h=t.getUTCHours(), m=p2(t.getUTCMinutes());
 e.textContent=h24?p2(h)+':'+m:p2(h%12||12)+':'+m+' '+(h<12?'AM':'PM')})}
if(clk){clk.value=h24?'24':'12';clk.onchange=function(){h24=clk.value==='24';
 try{localStorage.setItem('clock',clk.value)}catch(e){} times()}}
times();
var sel=d.getElementById('month');
if(sel){sel.onchange=function(){location.href=sel.value}}
var MONTHS=["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"], DAYS=window.DAYS||{}, keys=Object.keys(DAYS).sort();
var hdr=d.querySelector('header.top'), fl=d.getElementById('floatday'), btn=d.getElementById('datebtn'), cal=d.getElementById('cal');
var cur=cfg.month?cfg.month+'-01':keys[0], view=null;
function ymd(y,mo,dd){return y+'-'+p2(mo)+'-'+p2(dd)}
function nice(k){var q=k.split('-');return p2(+q[2])+'/'+p2(+q[1])+'/'+q[0]}
function go(k){var mo=k.slice(0,7), el=d.getElementById('d'+k);
 if(mo===cfg.month&&el){el.scrollIntoView();} else {location.href=mo+'.html#d'+k}}
function differs(k){return DAYS[k]&&(DAYS[k][1]||DAYS[k][2])}
function step(dir){var list=keys.filter(differs), i;
 if(dir>0){for(i=0;i<list.length;i++){if(list[i]>cur){go(list[i]);return}}}
 else{for(i=list.length-1;i>=0;i--){if(list[i]<cur){go(list[i]);return}}}}
function render(){
 var first=new Date(Date.UTC(view.y,view.m-1,1)), dow=(first.getUTCDay()+6)%7, n=new Date(Date.UTC(view.y,view.m,0)).getUTCDate(), i, h;
 h='<div class="calhead"><a data-a="prev">‹</a><b>'+MONTHS[view.m-1]+' '+view.y+'</b><a data-a="next">›</a></div><div class="calgrid">';
 'MTWTFSS'.split('').forEach(function(x){h+='<i>'+x+'</i>'});
 for(i=0;i<dow;i++){h+='<span></span>'}
 for(i=1;i<=n;i++){var k=ymd(view.y,view.m,i), info=DAYS[k], cls='calday'+(info?'':' empty')+(k===cur?' cur':'');
  h+='<a class="'+cls+'" data-d="'+k+'">'+i+(info&&info[1]?'<u class="pc"></u>':'')+(info&&info[2]?'<u class="ph"></u>':'')+'</a>'}
 h+='</div><div class="calfoot"><a data-a="pd">« earlier difference</a><a data-a="nd">later difference »</a></div>'
  +'<div class="callegend"><u class="pc"></u> only in the PC export <u class="ph"></u> only on the phone · '+keys.filter(differs).length+' days differ</div>';
 cal.innerHTML=h}
function show(){var q=cur.split('-');view={y:+q[0],m:+q[1]};render();cal.classList.add('open')}
if(btn&&cal){btn.onclick=function(e){e.stopPropagation();if(cal.classList.contains('open')){cal.classList.remove('open')}else{show()}};
 cal.onclick=function(e){e.stopPropagation();var t=e.target.closest('a');if(!t)return;
  if(t.dataset.d&&!t.classList.contains('empty')){go(t.dataset.d)}
  else if(t.dataset.a==='prev'){view.m--;if(view.m<1){view.m=12;view.y--}render()}
  else if(t.dataset.a==='next'){view.m++;if(view.m>12){view.m=1;view.y++}render()}
  else if(t.dataset.a==='pd'){step(-1)} else if(t.dataset.a==='nd'){step(1)}};
 d.addEventListener('click',function(){cal.classList.remove('open')});
 d.addEventListener('keydown',function(e){if(e.key==='Escape'){cal.classList.remove('open')}})}
var dayEls=[].slice.call(d.querySelectorAll('.day')), ticking=false;
function where(){ticking=false;if(!dayEls.length)return;var line=(hdr?hdr.offsetHeight:0)+12, pick=dayEls[0], i;
 for(i=0;i<dayEls.length;i++){if(dayEls[i].getBoundingClientRect().top<=line){pick=dayEls[i]}else{break}}
 var k=pick.id.slice(1);
 if(fl){fl.style.top=((hdr?hdr.offsetHeight:0)+8)+'px';fl.textContent=pick.textContent;fl.style.visibility=pick.getBoundingClientRect().top>(hdr?hdr.offsetHeight:0)?'hidden':'visible'}
 if(k!==cur){cur=k;if(btn){btn.textContent=nice(k)}if(cal&&cal.classList.contains('open')){render()}}}
if(btn){btn.textContent=nice(cur)}
window.addEventListener('scroll',function(){if(!ticking){ticking=true;requestAnimationFrame(where)}},{passive:true});
window.addEventListener('resize',where);
where();
})();
"""

SEARCH_BOX = '<input id="q" class="srch" type="search" placeholder="Search (press /)" title="Search this chat">'
SEARCH_JS = """
(function(){
var d=document, q=d.getElementById('q'), box=d.getElementById('results'), cfg=window.CHAT||{};
function flash(id){var el=d.getElementById(id);if(!el)return;el.scrollIntoView({block:'center'});el.classList.add('hit');
 setTimeout(function(){el.classList.remove('hit')},3500)}
if(location.hash.indexOf('#m')===0){setTimeout(function(){flash(location.hash.slice(1))},80)}
if(!q||!box)return;
var data=null, fcache={}, accents=false, loading=false, found=[], shown=0, newest=true, whole=false, sel=-1, timer=null, PAGE=60;
try{whole=localStorage.getItem('wholeword')==='1';accents=localStorage.getItem('matchaccents')==='1'}catch(e){}
var WORD=/[\\p{L}\\p{N}_]/u;
function isw(c){return !!c&&WORD.test(c)}
function find(ft,t,from){var k=ft.indexOf(t,from);
 if(!whole)return k;
 while(k>=0){var a=t.charAt(0), z=t.charAt(t.length-1);
  if(!(isw(a)&&isw(ft.charAt(k-1)))&&!(isw(z)&&isw(ft.charAt(k+t.length)))){return k}
  k=ft.indexOf(t,k+1)}
 return -1}
function fold(s){if(accents){return s.normalize('NFC').toLowerCase()}
 return s.normalize('NFD').replace(/[\\u0300-\\u036f]/g,'').replace(/\\u0111/g,'d').replace(/\\u0110/g,'d').toLowerCase()}
function getF(){var k=accents?'a':'x';if(!fcache[k]){fcache[k]=data.r.map(function(r){return fold(r[4])})}return fcache[k]}
function esc(s){return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')}
function p2(n){return (n<10?'0':'')+n}
function when(ms){var t=new Date(ms+25200000);return p2(t.getUTCDate())+'/'+p2(t.getUTCMonth()+1)+'/'+t.getUTCFullYear()+' '+p2(t.getUTCHours())+':'+p2(t.getUTCMinutes())}
function load(cb){
 if(data){cb();return}
 if(loading)return;loading=true;box.classList.add('open');box.innerHTML='<div class="rhead">Loading the search index…</div>';
 var s=d.createElement('script');s.charset='utf-8';s.src='search.js';
 s.onload=function(){data=window.SEARCH;loading=false;cb()};
 s.onerror=function(){loading=false;box.innerHTML='<div class="rhead">search.js was not found next to this page.</div>'};
 d.head.appendChild(s)}
function snippet(text,ft,terms){
 var marks=[],at=-1,i;
 terms.forEach(function(t){var p=0,k;while((k=find(ft,t,p))>=0){marks.push([k,k+t.length]);p=k+t.length}});
 marks.sort(function(x,y){return x[0]-y[0]});
 at=marks.length?marks[0][0]:0;
 var from=Math.max(0,at-50), to=Math.min(text.length,at+(marks.length?marks[0][1]-at:0)+90), h;
 if(ft.length===text.length){var out='',pos=from;
  marks.forEach(function(m){if(m[0]>=pos&&m[1]<=to){out+=esc(text.slice(pos,m[0]))+'<mark>'+esc(text.slice(m[0],m[1]))+'</mark>';pos=m[1]}});
  h=out+esc(text.slice(pos,to))}
 else{h=esc(text.slice(from,to))}
 return (from>0?'…':'')+h+(to<text.length?'…':'')}
function paint(){
 var terms=fold(q.value.trim()).split(/\\s+/).filter(Boolean), html='', i, end=Math.min(found.length,shown);
 html+='<div class="rhead"><span>'+found.length.toLocaleString()+' message'+(found.length===1?'':'s')+' found</span>'
  +'<span><label><input type="checkbox" id="whole"'+(whole?' checked':'')+'> whole word</label> &nbsp; '
  +'<label><input type="checkbox" id="accents"'+(accents?' checked':'')+'> match accents</label> &nbsp; '
  +'<label><input type="checkbox" id="newest"'+(newest?' checked':'')+'> newest first</label></span></div>';
 for(i=0;i<end;i++){var r=data.r[found[i]], mo=data.m[r[0]];
  html+='<a class="res" data-i="'+i+'" href="'+mo+'.html#m'+r[1]+'"><small>'+when(r[2])+' · '+esc(data.a[r[3]])+'</small>'+snippet(r[4],getF()[found[i]],terms)+'</a>'}
 if(end<found.length){html+='<button class="rmore" id="rmore">Show more</button>'}
 if(!found.length){html+='<div class="rhead">Nothing matches.</div>'}
 box.innerHTML=html;box.classList.add('open');sel=-1}
function run(){
 var raw=q.value.trim();if(!raw){box.classList.remove('open');return}
 load(function(){
  var terms=fold(raw).split(/\\s+/).filter(Boolean), res=[], i, j, ok, F=getF();
  for(i=0;i<F.length;i++){ok=true;for(j=0;j<terms.length;j++){if(find(F[i],terms[j],0)<0){ok=false;break}}if(ok)res.push(i)}
  found=newest?res.reverse():res;shown=PAGE;paint()})}
q.addEventListener('input',function(){clearTimeout(timer);timer=setTimeout(run,220)});
q.addEventListener('focus',function(){load(function(){})});
box.addEventListener('click',function(e){
 e.stopPropagation();
 if(e.target.id==='rmore'){shown+=PAGE*2;paint();return}
 if(e.target.id==='newest'){newest=e.target.checked;found.reverse();paint();return}
 if(e.target.id==='accents'){accents=e.target.checked;try{localStorage.setItem('matchaccents',accents?'1':'0')}catch(x){}run();return}
 if(e.target.id==='whole'){whole=e.target.checked;try{localStorage.setItem('wholeword',whole?'1':'0')}catch(x){}run();return}
 var a=e.target.closest('a.res');if(!a)return;
 var r=data.r[found[+a.dataset.i]];
 if(data.m[r[0]]===cfg.month&&d.getElementById('m'+r[1])){e.preventDefault();flash('m'+r[1]);box.classList.remove('open')}});
d.addEventListener('click',function(e){if(e.target!==q){box.classList.remove('open')}});
q.addEventListener('click',function(){if(q.value.trim()&&found.length){box.classList.add('open')}});
d.addEventListener('keydown',function(e){
 if(e.key==='Escape'){box.classList.remove('open');q.blur()}
 else if(e.key==='/'&&d.activeElement!==q&&!/input|select|textarea/i.test((d.activeElement||{}).tagName||'')){e.preventDefault();q.focus();q.select()}
 else if(e.key==='Enter'&&d.activeElement===q){var f=box.querySelector('a.res');if(f){f.click()}}});
})();
"""


def _t(ms, fmt):
    return datetime.fromtimestamp(ms / 1000, TZ).strftime(fmt)


def _stamp(ms, shown_as_pill=False):
    """A time that the browser re-formats in the system's own style; the text is the fallback."""
    cls = ' class="t pill"' if shown_as_pill else ' class="t"'
    return f'<time{cls} data-ms="{ms}">{_t(ms, "%I:%M %p")}</time>'


def _linkify(text):
    out = []
    for part in URL_RE.split(text):
        if URL_RE.fullmatch(part):
            href = html.escape(part, quote=True)
            out.append(f'<a href="{href}" target="_blank" rel="noreferrer">{html.escape(part)}</a>')
        else:
            out.append(html.escape(part))
    return "".join(out)


def _slug(index):
    return f"chat{index}"


def _hidden(row):
    """True for a message the viewer hides (a failed send that was redone), so it is left out of the day counts."""
    return "resent_superseded" in (row[-2] or "")


class Viewer:  # pylint: disable=too-many-instance-attributes,too-few-public-methods
    """Reads the archive and writes the site."""

    def __init__(  # pylint: disable=too-many-arguments,too-many-positional-arguments
            self, archive_path, out_dir, bubble_time="composed", media_mode="link", emoticon_dir=None, seen_icon=None,
            chat_names=None):
        self.arc = schema.connect(archive_path)
        self.out = Path(out_dir)
        self.bubble_time = bubble_time
        self.media_mode = media_mode
        self.pack = emoticons.Pack(emoticon_dir, seen_icon)
        self.chat_names = {}
        if chat_names:
            self.chat_names = json.loads(Path(chat_names).read_text(encoding="utf-8-sig"))
        self.big = False
        self.authors = {}
        self.photos = {}
        for mid, path, confidence in self.arc.execute(
                "SELECT message_id, original_path, confidence FROM message_media ORDER BY confidence DESC"):
            self.photos[mid] = (path, confidence)
        self.names = {n: (name or n) for n, name in self.arc.execute("SELECT number, name FROM contact")}
        self.reactions = defaultdict(dict)
        for mid, who, rid in self.arc.execute("SELECT message_id, reactor, reaction_id FROM reaction_effective"):
            self.reactions[mid][who] = rid
        pc = [r[0] for r in self.arc.execute("SELECT id FROM source_snapshot WHERE source LIKE 'pc-%'")]
        ph = [r[0] for r in self.arc.execute("SELECT id FROM source_snapshot WHERE source LIKE 'phone%'")]
        self.in_pc = self._lineage(pc)
        self.in_phone = self._lineage(ph)
        self.have_both = bool(pc and ph)

    def chat_name(self, key, kind, title):
        """Name shown for a chat: your override, else the stored title, else the contact's name, else a plain label."""
        if self.chat_names.get(key):
            return self.chat_names[key]
        if title:
            return title
        if kind == "notes" or key == "notes":
            return "My Notes"
        if key.startswith("direct:"):
            number = key.split(":", 1)[1]
            return self.names.get(number) or f"+{number}"
        return "Group chat"

    def _lineage(self, snapshot_ids):
        if not snapshot_ids:
            return set()
        marks = ",".join(map(str, snapshot_ids))
        return {r[0] for r in self.arc.execute(
            f"SELECT entity_id FROM source_record WHERE entity = 'message' AND snapshot_id IN ({marks})")}

    def _media_src(self, mid):
        """Address of the photo for this message, relative to a month page (two folders below the site root)."""
        path, confidence = self.photos[mid]
        source = Path(path)
        if self.media_mode == "copy":
            folder = self.out / "media"
            folder.mkdir(exist_ok=True)
            target = folder / f"{mid}{source.suffix.lower() if source.suffix.lower() != '.image' else '.jpg'}"
            if not target.exists():
                shutil.copy2(source, target)
            return "../media/" + target.name, confidence
        try:
            rel = os.path.relpath(source, self.out / "chatX").replace(os.sep, "/")
        except ValueError:  # other drive on Windows
            rel = source.resolve().as_uri()
        return rel, confidence

    def _emoticon_html(self, name):
        if self.pack.has(name):
            return (f'<img class="emoji-pic" loading="lazy" decoding="async" '
                    f'src="../emoticons/{emoticons.slug(name)}.png" alt="({name})" title="({name})">')
        return f'<div class="big" title="({name})">{emoticons.emoji(name)}</div>'

    def _media_html(self, mid, kind, label, name=""):
        if mid not in self.photos or not Path(self.photos[mid][0]).exists():
            tip = f' title="{html.escape(name, quote=True)}"' if name and kind in ("image", "video") else ""
            return f'<div class="media"{tip}>{html.escape(label)}</div>'
        src, confidence = self._media_src(mid)
        src = html.escape(src, quote=True)
        if kind == "sticker":
            return f'<img class="stk" src="{src}" alt="Sticker">'
        note = "" if confidence.startswith("exact") else ' title="matched by time, not proof"'
        if kind == "video":
            return f'<video class="pic" controls preload="none" src="{src}"{note}></video>'
        return (f'<a href="{src}" target="_blank"><img class="pic" loading="lazy" decoding="async" '
                f'src="{src}"{note} alt="Photo"></a>')

    def _quote_author(self, token, kind_chat):
        """'You' or the other person's name for the message a reply points at (found by its Viber token)."""
        found = self.authors.get(str(token)) if token is not None else None
        if not found:
            return ""
        direction, author, _text = found
        if direction == "out":
            return "You"
        return self.names.get(author, author or "") if kind_chat != "notes" else "You"

    # -- one message ---------------------------------------------------------------------------------------------
    def _bubble(self, row, kind_chat, first=False):  # pylint: disable=too-many-locals
        (mid, direction, author, composed, sent, kind, text, caption, reply, media, tick, flags, version_count) = row
        flag_list = json.loads(flags or "[]")
        shown = sent if (self.bubble_time == "sent" and sent) else composed
        if kind in ("system", "reaction"):
            return f'<div class="system" id="m{mid}">{html.escape(text or KIND_LABEL.get(kind, ""))}</div>'
        inner = []
        big = has_pic = False
        if kind_chat == "group" and direction == "in":
            inner.append(f'<div class="who">{html.escape(self.names.get(author, author or "?"))}</div>')
        if reply:
            try:
                data = json.loads(reply) or {}
            except ValueError:
                data = {}
            data = data if isinstance(data, dict) else {}
            earlier = self.authors.get(str(data.get("token"))) if data.get("token") is not None else None
            quote = emoticons.to_emoji(data.get("text") or (earlier[2] if earlier else ""))[:200]
            who = self._quote_author(data.get("token"), kind_chat)
            inner.append(f'<div class="quote">{f"<b>{html.escape(who)}</b>" if who else ""}'
                         f'{html.escape(quote) or "Replied message"}</div>')
        if kind in KIND_LABEL and kind != "link":
            caption = "" if (caption or "").startswith(("content://", "file://")) else caption
            name = "" if "://" in (media or "") else (media or "").replace("\\", "/").rsplit("/", 1)[-1]
            suffix = Path(name).suffix.lower()
            if kind == "file" and suffix in PICTURE_EXT:        # a photo Viber sent as a file: treat as a photo
                kind = "image"
            elif kind == "file" and suffix in MOVIE_EXT:
                kind = "video"
            label = KIND_LABEL[kind] + (f" ({name})" if name and kind == "file" else "")
            inner.append(self._media_html(mid, kind, label, name))
            shown_pic = mid in self.photos and Path(self.photos[mid][0]).exists()
            big = kind == "sticker" and shown_pic
            has_pic = kind in ("image", "video") and shown_pic
            if caption:
                inner.append(f'<div class="txt">{_linkify(caption)}</div>')
        else:
            name = self.pack.whole(text) if kind == "text" else None
            if name:
                inner.append(self._emoticon_html(name))
                big = True
            else:
                inner.append(f'<div class="txt">{self.pack.inline(_linkify(text or ""))}</div>')
        meta = []
        if version_count > 1:
            meta.append('<span class="edited">Edited</span>')
        meta.append(_stamp(shown))
        if direction == "out" and tick in ("seen", "sent"):
            if tick == "sent":
                meta.append('<span class="tick sent">✓</span>')
            elif self.pack.has("seen"):
                meta.append('<img class="seen-img" decoding="async" src="../emoticons/seen.png" '
                            'alt="seen" title="seen">')
            else:
                meta.append('<span class="tick seen">✓✓</span>')
        inner.append(f'<div class="meta" title="{_t(shown, "%d/%m/%Y %H:%M:%S")}">{"".join(meta)}</div>')
        alt = f"composed {_t(composed, '%H:%M:%S')}" + (f" · phone {_t(sent, '%H:%M:%S')}" if sent else "")
        inner.append(f'<div class="alt">{alt}</div>')
        shown_flags = [f for f in flag_list if f in SHOWN_FLAGS]
        if shown_flags:
            inner.append(f'<div class="flag alt">{" · ".join(shown_flags)}</div>')
        chips = self.reactions.get(mid, {})
        side = "".join(f'<span class="react" title="{who}">{self._reaction_glyph(rid)}</span>'
                       for who, rid in sorted(chips.items()))
        if "me" not in chips:
            side += '<span class="react-btn" title="react">♡</span>'
        marker = ""
        if self.have_both:
            pcs, phs = mid in self.in_pc, mid in self.in_phone
            marker = '<span class="src pc" title="only in the PC export"></span>' if pcs and not phs else (
                '<span class="src phone" title="only on the phone"></span>' if phs and not pcs else "")
        cls = "row out" if direction == "out" else "row in"
        if first:
            cls += " first"
        if "resent_superseded" in flag_list:
            cls += " superseded"
        if big:                       # a picture that quotes another message keeps its bubble, like Viber
            cls += " bigq" if reply else " bare"
        bubble_cls = "bubble hasmedia" if has_pic else "bubble"
        bubble = f'<div class="{bubble_cls}">{"".join(inner)}</div>'
        side = f'<div class="side">{side}</div>'
        order = side + bubble if direction == "out" else bubble + side
        order += marker
        return f'<div class="{cls}" id="m{mid}">{order}</div>'

    def _reaction_glyph(self, rid):
        if rid == 1 and self.pack.has("blue_heart"):
            return '<img class="react-img" src="../emoticons/blue_heart.png" alt="heart">'
        return REACTIONS.get(rid, "?")

    # -- pages -----------------------------------------------------------------------------------------------------
    def _page(self, title, head, body, depth, extra=""):
        up = "../" * depth
        return (f'<!doctype html><html lang="en"><head><meta charset="utf-8"><title>{html.escape(title)}</title>'
                '<meta name="viewport" content="width=device-width,initial-scale=1">'
                f'<link rel="stylesheet" href="{up}style.css"></head><body>{head}{body}'
                f'{extra}<script src="{up}app.js"></script></body></html>')

    def run(self):
        """Write everything. Returns {'chats': n, 'pages': n, 'messages': n}."""
        self.out.mkdir(parents=True, exist_ok=True)
        (self.out / "style.css").write_text(CSS, encoding="utf-8")
        self.pack.publish(self.out / "emoticons")
        (self.out / "app.js").write_text(JS + SEARCH_JS, encoding="utf-8")
        chats = self.arc.execute(
            "SELECT c.chat_key, c.kind, c.title, count(m.id), min(m.composed_ms), max(m.composed_ms) FROM chat c"
            " JOIN message m ON m.chat_key = c.chat_key GROUP BY c.chat_key ORDER BY 4 DESC").fetchall()
        summary = {"chats": len(chats), "pages": 0, "messages": 0}
        cards = []
        for index, (key, kind, title, count, first, last) in enumerate(chats, 1):
            months = self._write_chat(index, key, kind, self.chat_name(key, kind, title))
            summary["pages"] += len(months)
            summary["messages"] += count
            label = self.chat_name(key, kind, title)
            cards.append(f'<a href="{_slug(index)}/index.html">{html.escape(label)}<br>'
                         f'<small>{kind} · {count:,} messages · '
                         f"{_t(first, '%d/%m/%Y')} to {_t(last, '%d/%m/%Y')}</small></a>")
        head = '<header class="top"><h1>Viber archive</h1></header>'
        body = '<main><div class="cards">' + "".join(cards) + "</div></main>"
        (self.out / "index.html").write_text(self._page("Viber archive", head, body, 0), encoding="utf-8")
        self.arc.close()
        summary["emoticons"] = len(self.pack.files)
        summary["seen_icon"] = str(self.pack.files.get("seen", ""))
        return summary

    def _write_chat(self, index, key, kind, title):
        rows = self.arc.execute(
            "SELECT id, direction, author, composed_ms, sent_ms, kind, text, caption, reply_json, media_path, tick,"
            " flags, version_count FROM message WHERE chat_key = ? ORDER BY composed_ms, sort_order, seq, id", (key,))
        folder = self.out / _slug(index)
        folder.mkdir(exist_ok=True)
        by_month = defaultdict(list)
        rows_all = rows.fetchall()
        needed = set()
        for row in rows_all:
            if row[8]:
                try:
                    token = (json.loads(row[8]) or {}).get("token")
                except (ValueError, AttributeError):
                    token = None
                if token is not None:
                    needed.add(str(token))
        self.authors = {t: (d, a, x[:200] if t in needed else "") for t, d, a, x in self.arc.execute(
            "SELECT token, direction, author, text FROM message WHERE chat_key = ? AND token IS NOT NULL", (key,))}
        for row in rows_all:
            by_month[_t(row[3], "%Y-%m")].append(row)
        months = sorted(by_month)
        label = title  # already the display name
        days = defaultdict(lambda: [0, 0, 0])
        for row in rows_all:
            if _hidden(row):
                continue
            entry = days[_t(row[3], "%Y-%m-%d")]
            entry[0] += 1
            if self.have_both:
                in_pc, in_ph = row[0] in self.in_pc, row[0] in self.in_phone
                entry[1] += in_pc and not in_ph
                entry[2] += in_ph and not in_pc
        self._write_search_index(folder, by_month, months)
        payload = json.dumps(days, separators=(",", ":"))
        (folder / "days.js").write_text(f"window.DAYS={payload};", encoding="utf-8")
        for month in months:
            parts, day, previous = [], None, None
            for row in by_month[month]:
                this_day = _t(row[3], "%Y-%m-%d")
                if this_day != day:
                    day = this_day
                    previous = None
                    nice = _t(row[3], "%A, %d %B %Y")
                    parts.append(f'<div class="day" id="d{day}"><span>{nice}</span></div>')
                who = (row[1], row[2])
                parts.append(self._bubble(row, kind, first=who != previous))
                previous = None if row[5] in ("system", "reaction") else who
            position = months.index(month)
            nav = []
            if position:
                nav.append(f'<a class="nav" href="{months[position - 1]}.html">‹</a>')
            options = "".join(
                f'<option value="{m}.html"{" selected" if m == month else ""}>{MONTH_NAMES[int(m[5:]) - 1]} {m[:4]}'
                f" ({len(by_month[m]):,})</option>" for m in months)
            nav.append(f'<select id="month">{options}</select>')
            if position < len(months) - 1:
                nav.append(f'<a class="nav" href="{months[position + 1]}.html">›</a>')
            head = (f'<header class="top"><h1><a class="nav" href="index.html">{html.escape(label)}</a></h1>'
                    f'{"".join(nav)}'
                    f'{SEARCH_BOX}<button id="datebtn" class="datebtn" title="Pick a date">date</button>'
                    '<select id="clock" title="Clock"><option value="12">12-hour</option>'
                    '<option value="24">24-hour</option></select>'
                    '<label><input type="checkbox" id="markers"> source markers</label>'
                    '<label><input type="checkbox" id="verify"> times and flags</label>'
                    '<span class="legend"><span style="color:#4fc3f7">●</span> only PC · '
                    '<span style="color:#ffb454">●</span> only phone</span><div id="cal" class="cal"></div></header>'
                    '<div id="floatday"></div><div id="results" class="results"></div>')
            script = (f'<script>window.CHAT={{months:{json.dumps(months)},month:"{month}"}};</script>'
                      '<script src="days.js"></script>')
            (folder / f"{month}.html").write_text(
                self._page(f"{label} {month}", head, f"<main>{''.join(parts)}</main>", 1, script), encoding="utf-8")
        self._write_chat_index(folder, label, months, by_month)
        return months

    def _write_search_index(self, folder, by_month, months):
        """search.js: every searchable message of the chat as [month index, message id, ms, who index, text]."""
        who, rows = [], []
        for number, month in enumerate(months):
            for row in by_month[month]:
                if _hidden(row) or row[5] in ("system", "reaction", "sticker"):
                    continue
                text = (row[6] if row[5] in ("text", "link") else row[7]) or ""
                if not text.strip() or text.startswith(("content://", "file://")):
                    continue
                name = "You" if row[1] == "out" else self.names.get(row[2], row[2] or "?")
                if name not in who:
                    who.append(name)
                rows.append([number, row[0], row[3], who.index(name), text])
        payload = json.dumps({"m": months, "a": who, "r": rows}, ensure_ascii=False, separators=(",", ":"))
        (folder / "search.js").write_text(f"window.SEARCH={payload};", encoding="utf-8")

    def _write_chat_index(self, folder, label, months, by_month):
        years = defaultdict(dict)
        for month in months:
            years[month[:4]][int(month[5:])] = month
        pc_only = defaultdict(int)
        phone_only = defaultdict(int)
        if self.have_both:
            for month in months:
                for row in by_month[month]:
                    if _hidden(row):
                        continue
                    in_pc, in_ph = row[0] in self.in_pc, row[0] in self.in_phone
                    if in_pc and not in_ph:
                        pc_only[month] += 1
                    elif in_ph and not in_pc:
                        phone_only[month] += 1
        lines = ['<table class="grid"><tr><th></th>' + "".join(f"<th>{m[:3]}</th>" for m in MONTH_NAMES) + "</tr>"]
        for year in sorted(years):
            cells = []
            for number in range(1, 13):
                month = years[year].get(number)
                if not month:
                    cells.append("<td></td>")
                    continue
                cls = "pc" if pc_only[month] else ("phone" if phone_only[month] else "")
                tip = f"{len(by_month[month]):,} messages"
                if pc_only[month] or phone_only[month]:
                    tip += f" · {pc_only[month]:,} only PC · {phone_only[month]:,} only phone"
                cells.append(f'<td class="{cls}"><a href="{month}.html" title="{tip}">'
                             f'{len(by_month[month]):,}</a></td>')
            lines.append(f"<tr><th>{year}</th>{''.join(cells)}</tr>")
        lines.append("</table>")
        note = ("<p class='legend' style='display:block'><span style='color:#4fc3f7'>●</span> "
                "a month with messages only in "
                "the PC export, <span style='color:#ffb454'>●</span> only on the phone (outlined cells).</p>")
        head = ('<header class="top"><h1><a class="nav" href="../index.html">All chats</a> '
                f'{html.escape(label)}</h1>{SEARCH_BOX}</header><div id="results" class="results"></div>')
        body = f"<main>{note}<div class='gridwrap'>{''.join(lines)}</div></main>"
        (folder / "index.html").write_text(
            self._page(label, head, body, 1, "<script>window.CHAT={month:null};</script>"), encoding="utf-8")


def build(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        archive_path, out_dir, bubble_time="composed", media_mode="link", emoticon_dir=None, seen_icon=None,
        chat_names=None):
    """Write the site; returns the counts."""
    return Viewer(archive_path, out_dir, bubble_time, media_mode, emoticon_dir, seen_icon, chat_names).run()
