import {categories,filterItems,dateLabel,todayJST,isExpired,isStale,validateDataset,escapeHTML as e} from './core.mjs';
const $=s=>document.querySelector(s); const params=new URLSearchParams(location.search);
const study=params.get('study')==='1'; const baseline=params.get('view')==='baseline';
const state={category:'all',query:'',includeExpired:false,today:todayJST()};
let dataset;let reading=false;let lastFocus='';
const storage={get(k,f){try{return localStorage.getItem(k)||f;}catch{return f;}},set(k,v){try{localStorage.setItem(k,v);}catch{}}};
function preferences(){const size=study?'normal':storage.get('nabari-size','normal');document.documentElement.dataset.size=size;document.documentElement.classList.toggle('high',!study&&storage.get('nabari-contrast','normal')==='high');document.querySelectorAll('[data-size-button]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.sizeButton===size)));$('#contrast').setAttribute('aria-pressed',String(document.documentElement.classList.contains('high')));}
function signal(action,id=''){if(study&&window.parent!==window)window.parent.postMessage({type:'nabari-action',action,id},location.origin);}
function setSize(size){document.documentElement.dataset.size=size;if(!study)storage.set('nabari-size',size);document.querySelectorAll('[data-size-button]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.sizeButton===size)));}
function stopReading(){if('speechSynthesis'in window)window.speechSynthesis.cancel();reading=false;const b=$('#speak');if(b)b.textContent='この案内を読み上げる';}
function renderCategories(){const focusCategory=document.activeElement?.dataset?.category;const box=$('#categories');box.replaceChildren();for(const [id,label]of Object.entries(categories)){const b=document.createElement('button');b.type='button';b.dataset.category=id;b.setAttribute('aria-pressed',String(state.category===id));const n=filterItems(dataset.items,{...state,category:id,query:''}).length;b.innerHTML=`<span>${label}</span><small>${n}件の案内</small>`;b.onclick=()=>{state.category=state.category===id?'all':id;signal('category',state.category);renderList();};box.append(b);if(focusCategory===id)b.focus();}}
function renderList(){
  stopReading();$('#detail').hidden=true;$('#listing').hidden=false;document.title='なばり くらしの案内';
  const rows=filterItems(dataset.items,state);const title=state.category==='all'?'すべての案内':categories[state.category];
  $('#results-title').textContent=`${title}（${rows.length}件）`;$('#result-status').textContent=`${rows.length}件の案内があります。`;$('#reset').hidden=state.category==='all'&&!state.query;
  renderCategories(); const cards=$('#cards');cards.replaceChildren();
  if(!rows.length){cards.innerHTML='<div class="empty"><h3>見つかりませんでした</h3><p>言葉を短くするか、カテゴリを変えてください。</p><button id="empty-reset" type="button">条件を戻してすべて見る</button></div>';$('#empty-reset').onclick=reset;return;}
  if(baseline){const ul=document.createElement('ul');ul.className='base-list';for(const r of rows){const li=document.createElement('li');li.innerHTML=`<a id="link-${e(r.id)}" href="#detail/${e(r.id)}">${e(r.title)}</a>`;ul.append(li);}cards.append(ul);return;}
  for(const r of rows){const c=document.createElement('article');c.className='card';c.innerHTML=`<span class="badge">${categories[r.category]}</span>${r.startDate?`<p class="date">${e(dateLabel(r.startDate))}${r.endDate!==r.startDate?' 〜 '+e(dateLabel(r.endDate)):''}</p>`:''}<h3><a id="link-${e(r.id)}" href="#detail/${e(r.id)}">${e(r.title)}</a></h3><p>${e(r.summary)}</p>${isExpired(r,state.today)?'<p class="status">終了したイベントです</p>':''}${isStale(r,state.today)?'<p class="status">確認から30日超：公式情報をご確認ください</p>':''}<p class="meta">確認日：${e(dateLabel(r.verifiedAt))}</p>`;cards.append(c);}
}
function reset(){state.category='all';state.query='';$('#query').value='';signal('reset');renderList();$('#query').focus();}
function renderDetail(id){
  stopReading();const r=dataset.items.find(x=>x.id===id);$('#listing').hidden=true;const box=$('#detail');box.hidden=false;lastFocus=id;
  if(!r){box.innerHTML='<h1 tabindex="-1">この案内は見つかりません</h1><a class="button" href="#">案内の一覧に戻る</a>';box.querySelector('h1').focus();return;}
  document.title=r.title+' | なばり くらしの案内';
  box.innerHTML=`<a class="button" href="#">案内の一覧に戻る</a><div style="margin-top:1.2rem"><span class="badge">${categories[r.category]}</span></div><h1 tabindex="-1">${e(r.title)}</h1>${isExpired(r,state.today)?'<p class="notice alert">このイベントは終了しています。記録として表示しています。</p>':''}${isStale(r,state.today)?'<p class="notice alert">確認から30日を過ぎています。変更の有無を公式ページで確認してください。</p>':''}${r.notice?`<p class="notice alert">${e(r.notice)}</p>`:''}<div id="readable"><p>${e(r.summary)}</p><dl>${[['日時・受付',r.when],['場所',r.where],['問い合わせ先',r.contact]].filter(x=>x[1]).map(([k,v])=>`<dt>${k}</dt><dd>${e(v)}</dd>`).join('')}</dl>${r.body.map(p=>`<p>${e(p)}</p>`).join('')}</div><div class="actions"><a class="button primary" href="${e(r.sourceUrl)}" target="_blank" rel="noopener noreferrer" data-source="${e(r.id)}">名張市の公式ページを見る（別タブ）</a>${r.phone?`<a class="button" href="tel:${r.phone}">電話：${r.phone}</a>`:''}</div><div class="actions"><button type="button" id="speak">この案内を読み上げる</button><button type="button" id="print">この案内を印刷する</button></div><p id="speech-status" class="status-msg" role="status"></p><div class="source"><p class="meta">出典：${e(r.sourceTitle)}<br>出典の更新日：${r.sourceUpdatedAt?e(dateLabel(r.sourceUpdatedAt)):'記載を確認できず'}<br>内容の確認日：${e(dateLabel(r.verifiedAt))}</p><p class="meta">このページは研究用に要約した案内です。変更や詳しい条件は公式ページで確認してください。</p></div>`;
  box.querySelector('h1').focus();signal('detail',id);$('#print').onclick=()=>window.print();
  $('[data-source]').onclick=ev=>{signal('source',id);if(study){ev.preventDefault();$('#speech-status').textContent='実験では、この案内の中の情報を使って回答してください。';}};
  if(study){$('[data-source]').textContent='公式ページ（実験中は開きません）';$('[data-source]').setAttribute('aria-disabled','true');const tel=box.querySelector('a[href^="tel:"]');if(tel){tel.textContent='電話番号：'+r.phone+'（実験中は発信しません）';tel.setAttribute('aria-disabled','true');tel.onclick=ev=>ev.preventDefault();}}
  $('#speak').onclick=()=>{
    if(reading){stopReading();return;}
    if(!('speechSynthesis'in window)||!('SpeechSynthesisUtterance'in window)){$('#speech-status').textContent='このブラウザでは読み上げを利用できません。画面の文章をご覧ください。';return;}
    const u=new SpeechSynthesisUtterance(r.title+'。'+[r.notice,r.when,r.where,...r.body].filter(Boolean).join('。'));u.lang='ja-JP';u.rate=.9;reading=true;$('#speak').textContent='読み上げを止める';
    u.onend=()=>stopReading();u.onerror=()=>{stopReading();if($('#speech-status'))$('#speech-status').textContent='音声を再生できませんでした。端末の日本語音声・音量をご確認ください。';};window.speechSynthesis.speak(u);
  };
}
function route(){let id='';try{id=decodeURIComponent(location.hash.replace(/^#detail\//,''));}catch{}if(location.hash.startsWith('#detail/'))renderDetail(id);else{renderList();if(lastFocus)document.getElementById('link-'+lastFocus)?.focus();}}
async function init(){
  preferences();document.querySelectorAll('[data-size-button]').forEach(b=>b.onclick=()=>setSize(b.dataset.sizeButton));$('#contrast').onclick=()=>{const high=document.documentElement.classList.toggle('high');$('#contrast').setAttribute('aria-pressed',String(high));if(!study)storage.set('nabari-contrast',high?'high':'normal');};
  try{const res=await fetch('./data/information.json',{cache:'no-store'});if(!res.ok)throw Error('HTTP '+res.status);dataset=await res.json();const errors=validateDataset(dataset);if(errors.length)throw Error(errors.join('\n'));}
  catch{$('#loading').innerHTML='<h1>案内を読み込めませんでした</h1><p>通信を確認して再読み込みしてください。ファイルを直接開いた場合は、READMEの起動方法で開いてください。</p><a class="button" href="https://www.city.nabari.lg.jp/">名張市の公式サイトを見る</a>';return;}
  if(study){state.today=dataset.asOf;$('#study-note').hidden=false;$('#study-note').textContent=`比較実験：${dateLabel(dataset.asOf)}の情報で固定しています。`;}
  $('#loading').hidden=true;$('#app').hidden=false;$('#checked').textContent='収録情報の基準日：'+dateLabel(dataset.asOf);
  if(baseline){$('#category-section').hidden=true;$('#search').hidden=true;$('#font-controls').hidden=true;$('#contrast').hidden=true;$('#cards').style.display='block';}
  $('#search').onsubmit=ev=>{ev.preventDefault();state.query=$('#query').value;signal('search');renderList();};$('#reset').onclick=reset;$('#expired').onchange=()=>{state.includeExpired=$('#expired').checked;renderList();};
  window.addEventListener('hashchange',route);window.addEventListener('pagehide',stopReading);route();signal('ready');
  // Optional WebMCP; browsing and assistance use the exact same state as the UI.
  if(document.modelContext?.registerTool){const life=new AbortController();window.addEventListener('pagehide',()=>life.abort(),{once:true});try{await document.modelContext.registerTool({name:'search_nabari_information',title:'名張の案内を探す',description:'公開済みの案内を検索して、画面の一覧と同じ結果を表示する。',inputSchema:{type:'object',properties:{query:{type:'string',maxLength:100},category:{type:'string',enum:['all',...Object.keys(categories)]}},required:['query'],additionalProperties:false},annotations:{readOnlyHint:false,untrustedContentHint:true},execute(input){if(!input||typeof input.query!=='string'||input.query.length>100||Object.keys(input).some(k=>!['query','category'].includes(k))||(input.category!==undefined&&input.category!=='all'&&!Object.hasOwn(categories,input.category)))throw Error('検索条件が不正です');state.query=input.query;state.category=input.category||'all';$('#query').value=input.query;history.replaceState(null,'',location.pathname+location.search);renderList();return filterItems(dataset.items,state).map(({id,title,sourceUrl})=>({id,title,sourceUrl}));}},{signal:life.signal});}catch{/* The normal interface is available without WebMCP. */}}
}
init();
