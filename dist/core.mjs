/** Pure domain functions. Browser and Node tests share this implementation. */
export const categories = Object.freeze({event:'行事・イベント', waste:'ごみ・リサイクル', health:'健康・介護', consult:'困りごとの相談', disaster:'防災の備え', city:'市役所・手続き'});
export const normalize = value => String(value).normalize('NFKC').toLowerCase().replace(/[ァ-ヶ]/g, c => String.fromCharCode(c.charCodeAt(0)-0x60)).replace(/\s+/g,' ').trim();
export const escapeHTML = value => String(value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
export function validDate(s) { return typeof s==='string' && /^\d{4}-\d{2}-\d{2}$/.test(s) && !Number.isNaN(Date.parse(s)) && new Date(s).toISOString().slice(0,10)===s; }
export function todayJST(date=new Date()) { return new Intl.DateTimeFormat('sv-SE',{timeZone:'Asia/Tokyo',year:'numeric',month:'2-digit',day:'2-digit'}).format(date); }
export function dateLabel(s) { if(!validDate(s)) return '日付未確認'; const [y,m,d]=s.split('-').map(Number); return `${y}年${m}月${d}日`; }
export function safeSource(s) { try {const u=new URL(s);return u.protocol==='https:' && u.hostname==='www.city.nabari.lg.jp' && !u.username && !u.password && !u.port;}catch{return false;} }
export function isExpired(record,today=todayJST()) {return Boolean(record.endDate && record.endDate<today);}
export function isStale(record,today=todayJST()) {return Date.parse(today)-Date.parse(record.verifiedAt)>30*86400000;}
export function validateDataset(d) {
  const errors=[];
  if(!d || typeof d!=='object' || Array.isArray(d)) return ['JSONの最上位はオブジェクトにしてください。'];
  if(d.schemaVersion!==1) errors.push('schemaVersion は 1 が必要です。');
  if(!validDate(d.asOf)) errors.push('asOf は有効な YYYY-MM-DD 日付が必要です。');
  if(!Array.isArray(d.items)||!d.items.length||d.items.length>500) return [...errors,'items は1〜500件の配列にしてください。'];
  const ids=new Set();
  d.items.forEach((r,i)=>{
    const p=`${i+1}件目`;
    if(!r||typeof r!=='object'||Array.isArray(r)){errors.push(`${p}: オブジェクトが必要です。`);return;}
    if(typeof r.id!=='string'||!(/^[a-z][a-z0-9-]{1,59}$/).test(r.id)||ids.has(r.id)) errors.push(`${p}: IDの形式または重複を確認してください。`);
    ids.add(r.id);
    if(!Object.hasOwn(categories,r.category))errors.push(`${p}: カテゴリが不正です。`);
    for(const k of ['title','summary','sourceTitle','sourceUrl','verifiedAt']) if(typeof r[k]!=='string'||!r[k].trim()||r[k].length>1000)errors.push(`${p}: ${k} は1〜1000文字で入力してください。`);
    if(!Array.isArray(r.body)||!r.body.length||r.body.length>20||r.body.some(t=>typeof t!=='string'||!t.trim()||t.length>1500))errors.push(`${p}: body は1〜20段落（各1500文字以内）が必要です。`);
    if(!Array.isArray(r.tags)||r.tags.length>30||r.tags.some(t=>typeof t!=='string'||t.length>60))errors.push(`${p}: tags は短い文字列の配列が必要です。`);
    if(!safeSource(r.sourceUrl))errors.push(`${p}: 出典URLは https://www.city.nabari.lg.jp/ 内に限定します。`);
    if(!validDate(r.verifiedAt)||r.verifiedAt>d.asOf)errors.push(`${p}: 確認日は基準日以前の有効な日付が必要です。`);
    for(const k of ['startDate','endDate','sourceUpdatedAt']) if(r[k]!==null&&!validDate(r[k])) errors.push(`${p}: ${k} は日付または null にしてください。`);
    if(r.category==='event' && (!validDate(r.startDate)||!validDate(r.endDate)))errors.push(`${p}: イベントは開始日・終了日が必要です。`);
    if(Boolean(r.startDate)!==Boolean(r.endDate)||r.startDate>r.endDate)errors.push(`${p}: 開始日・終了日の組を確認してください。`);
    if(r.phone!==null && (typeof r.phone!=='string'||!/^0\d{1,4}-\d{1,4}-\d{3,4}$/.test(r.phone)))errors.push(`${p}: 電話番号の形式を確認してください。`);
    for(const k of ['when','where','contact','notice'])if(typeof r[k]!=='string'||r[k].length>1000)errors.push(`${p}: ${k} は1000文字以内の文字列にしてください。`);
  }); return errors;
}
export function filterItems(items,{category='all',query='',includeExpired=false,today=todayJST()}={}) {
  const words=normalize(query).split(' ').filter(Boolean);
  return items.filter(r=>(category==='all'||r.category===category) && (includeExpired||!isExpired(r,today)) && words.every(w=>normalize([r.title,r.summary,...r.body,...r.tags,r.where,r.when,r.contact,r.phone||'',r.phone?'電話':'',categories[r.category]].join(' ')).includes(w)))
    .sort((a,b)=>{
      const ae=a.category==='event',be=b.category==='event';
      if(ae!==be)return ae?-1:1;
      return (ae?(a.startDate.localeCompare(b.startDate)):0)||a.id.localeCompare(b.id);
    });
}
