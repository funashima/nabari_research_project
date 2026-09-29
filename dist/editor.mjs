import {categories,validateDataset,todayJST}from'./core.mjs';
const $=s=>document.querySelector(s);let data,selected=-1,dirty=false;
const keys=['id','title','summary','when','where','contact','phone','notice','sourceTitle','sourceUrl','sourceUpdatedAt','verifiedAt','startDate','endDate'];
const names={id:'ID（英小文字・数字・ハイフン）',title:'題名',summary:'一覧の短い説明',when:'日時・受付',where:'場所',contact:'問い合わせ先',phone:'電話番号',notice:'注意事項',sourceTitle:'公式ページの題名',sourceUrl:'公式ページのURL',sourceUpdatedAt:'公式ページ更新日',verifiedAt:'内容の確認日',startDate:'イベント開始日',endDate:'イベント終了日'};
function msg(t){$('#message').textContent=t;}
function renderOptions(){const select=$('#records');select.replaceChildren();data.items.forEach((r,i)=>select.add(new Option(r.title,String(i))));select.value=String(selected);$('#asof').value=data.asOf;}
function fill(){if(selected<0)return;const r=data.items[selected];for(const k of keys)$('#f-'+k).value=r[k]||'';$('#f-category').value=r.category;$('#f-body').value=r.body.join('\n');$('#f-tags').value=r.tags.join('、');}
function read(){const r={};for(const k of keys)r[k]=$('#f-'+k).value.trim();for(const k of['phone','sourceUpdatedAt','startDate','endDate'])r[k]=r[k]||null;r.category=$('#f-category').value;r.body=$('#f-body').value.split('\n').map(t=>t.trim()).filter(Boolean);r.tags=$('#f-tags').value.split(/[、,]/).map(t=>t.trim()).filter(Boolean);return r;}
function apply(){const candidate=structuredClone(data);candidate.asOf=$('#asof').value;if(selected<0)candidate.items.push(read());else candidate.items[selected]=read();const errors=validateDataset(candidate);if(errors.length){msg(errors.join('\n'));return false;}data=candidate;if(selected<0)selected=data.items.length-1;dirty=true;renderOptions();msg('編集内容を作業中のデータに反映しました。最後にJSONを書き出してください。');return true;}
function download(){const blob=new Blob([JSON.stringify(data,null,2)+'\n'],{type:'application/json'});const u=URL.createObjectURL(blob);const a=document.createElement('a');a.href=u;a.download='information.json';a.click();setTimeout(()=>URL.revokeObjectURL(u),2000);dirty=false;msg('JSONを書き出しました。公開中の案内はまだ変わっていません。');}
async function init(){
  const container=$('#fields');for(const k of keys){const label=document.createElement('label');label.textContent=names[k];const input=document.createElement('input');input.id='f-'+k;input.type=/Date$|verifiedAt|UpdatedAt/.test(k)?'date':k==='sourceUrl'?'url':'text';if(['title','summary','notice','sourceUrl'].includes(k))label.className='full';label.append(input);container.append(label);}
  Object.entries(categories).forEach(([id,title])=>$('#f-category').add(new Option(title,id)));
  try{const res=await fetch('./data/information.json',{cache:'no-store'});if(!res.ok)throw Error();data=await res.json();const errors=validateDataset(data);if(errors.length)throw Error(errors.join('\n'));selected=0;renderOptions();fill();$('#editor').hidden=false;}
  catch{msg('元のデータを読み込めません。READMEの起動方法を確認してください。');return;}
  $('#records').onchange=()=>{if(dirty&&!confirm('未書き出しの編集があります。入力欄を切り替えますか？')){$('#records').value=String(selected);return;}selected=Number($('#records').value);fill();};
  $('#form').onsubmit=ev=>{ev.preventDefault();apply();};$('#form').oninput=()=>{dirty=true;};$('#asof').oninput=()=>dirty=true;
  $('#new').onclick=()=>{if(dirty&&!confirm('入力中の内容を破棄して新しい案内を作りますか？'))return;selected=-1;$('#form').reset();$('#f-verifiedAt').value=todayJST();$('#asof').value=todayJST();dirty=true;msg('新しい案内を入力してください。');$('#f-id').focus();};
  $('#delete').onclick=()=>{if(selected<0||data.items.length<=1){msg('少なくとも1件の案内が必要です。');return;}if(confirm('選択中の案内を作業中のデータから削除しますか？')){data.items.splice(selected,1);selected=0;dirty=true;renderOptions();fill();msg('作業中のデータから削除しました。反映するにはJSONを書き出してください。');}};
  $('#export').onclick=()=>{if(apply())download();};
  $('#import').onchange=async()=>{const f=$('#import').files[0];if(!f)return;if(f.size>2_000_000){msg('2MB以下のJSONを選んでください。');return;}if(dirty&&!confirm('未書き出しの編集を破棄し、JSONを読み込みますか？'))return;try{const candidate=JSON.parse(await f.text());const errors=validateDataset(candidate);if(errors.length)throw Error(errors.join('\n'));data=candidate;selected=0;dirty=true;renderOptions();fill();msg('JSONを読み込みました。公開中の案内はまだ変わっていません。');}catch(e){msg('読み込めません：'+e.message);}};
  window.addEventListener('beforeunload',ev=>{if(dirty){ev.preventDefault();ev.returnValue='';}});
}
init();
