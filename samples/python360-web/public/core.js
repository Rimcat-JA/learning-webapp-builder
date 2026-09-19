export const STORAGE_KEY='python360.graduate.v1';
export function normalizeInteger(value){
 const s=String(value).normalize('NFKC').trim().replace(/^[−‐–]/,'-');
 if(!/^[+-]?\d+$/.test(s)||s.length>100)return null;
 try{return BigInt(s).toString();}catch{return null;}
}
export function grade(q,value){
 if(q.type==='number'){const n=normalizeInteger(value);return n===null?{valid:false,error:'整数を1つ入力してください。例：2、0、-3'}:{valid:true,correct:n===normalizeInteger(q.answer),value:n};}
 if(!q.choices.some(c=>c.key===value))return {valid:false,error:'選択肢を1つ選んでください。'};
 return {valid:true,correct:value===q.answer,value};
}
export const emptyState=()=>({schema:1,answers:{},bookmarks:[],drafts:{},lastQuestion:'G001'});
export function validateState(raw,questions){
 if(!raw||raw.schema!==1||typeof raw.answers!=='object'||!raw.answers||!Array.isArray(raw.bookmarks))throw Error('この教材の進捗ファイルではありません。');
 const result=emptyState(),map=new Map(questions.map(q=>[q.id,q]));
 for(const [id,v]of Object.entries(raw.answers)){
  if(!map.has(id)||!v||!Number.isSafeInteger(v.attempts)||v.attempts<1||v.attempts>1e6||typeof v.firstCorrect!=='boolean'||typeof v.correct!=='boolean'||typeof v.value!=='string'||v.value.length>100||typeof v.firstValue!=='string'||v.firstValue.length>100||!Number.isFinite(Date.parse(v.at)))throw Error('進捗データに不正な値があります。');
  const current=grade(map.get(id),v.value),first=grade(map.get(id),v.firstValue);
  if(!current.valid||!first.valid||current.correct!==v.correct||first.correct!==v.firstCorrect)throw Error('採点結果が教材と一致しません。');
  result.answers[id]={value:v.value,correct:v.correct,firstValue:v.firstValue,firstCorrect:v.firstCorrect,attempts:v.attempts,at:v.at,hintUsed:!!v.hintUsed};
 }
 result.bookmarks=[...new Set(raw.bookmarks.filter(id=>map.has(id)))];
 for(const [id,value]of Object.entries(raw.drafts||{}))if(map.has(id)&&typeof value==='string'&&value.length<=100)result.drafts[id]=value;
 if(map.has(raw.lastQuestion))result.lastQuestion=raw.lastQuestion;
 return result;
}
export function recordAttempt(state,q,graded,hintUsed=false){
 const prev=state.answers[q.id];
 return {...state,answers:{...state.answers,[q.id]:{value:graded.value,correct:graded.correct,firstValue:prev?.firstValue??graded.value,firstCorrect:prev?.firstCorrect??graded.correct,attempts:(prev?.attempts||0)+1,at:new Date().toISOString(),hintUsed:!!(prev?.hintUsed||hintUsed)}},drafts:{...state.drafts,[q.id]:''},lastQuestion:q.id};
}
