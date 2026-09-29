export const taskSets={
 X:[{id:'X1',target:'art-exhibition',prompt:'名張市美術展覧会の会場を調べ、建物の名前を答えてください。',answer:'名張市総合福祉センター「ふれあい」'},
 {id:'X2',target:'bulky-waste',prompt:'粗大ごみの戸別収集を申し込む電話番号を調べてください。',answer:'0595-64-8700'},
 {id:'X3',target:'machi-hokenshitsu',prompt:'まちの保健室の平日の業務時間を調べてください。',answer:'9:00〜16:30'}],
 Y:[{id:'Y1',target:'sports-festival',prompt:'なばりスポーツフェスティバル2026の開催日を調べてください。',answer:'2026年10月12日'},
 {id:'Y2',target:'battery-waste',prompt:'市役所で乾電池を出せる場所を、1か所答えてください。',answer:'1階ロビー、または環境対策室'},
 {id:'Y3',target:'city-office',prompt:'名張市役所の平日の窓口受付時間を調べてください。',answer:'9:00〜16:30'}]
};
export function schedule(participant){if(!/^P\d{3}$/.test(participant)||participant==='P000')throw Error('参加者番号はP001〜P999です。');const group=(Number(participant.slice(1))-1)%4;const plans=[['enhanced','X','baseline','Y'],['baseline','X','enhanced','Y'],['enhanced','Y','baseline','X'],['baseline','Y','enhanced','X']];const p=plans[group];return{group:group+1,tasks:[...taskSets[p[1]].map(t=>({...t,condition:p[0],period:1,set:p[1]})),...taskSets[p[3]].map(t=>({...t,condition:p[2],period:2,set:p[3]}))]};}
export function effectiveTime(outcome,elapsed,limit=180){if(!['success','failure','timeout','assisted'].includes(outcome)||!Number.isFinite(elapsed)||elapsed<0||elapsed>limit+.5)throw Error('Invalid observation');return outcome==='success'?Math.min(elapsed,limit):limit;}
