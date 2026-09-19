import assert from 'node:assert/strict';
import fs from 'node:fs';
import {grade,normalizeInteger,recordAttempt,emptyState,validateState} from '../public/core.js';
const data=JSON.parse(fs.readFileSync(new URL('../public/data.json',import.meta.url)));
assert.equal(data.questions.length,360);assert.equal(data.chapters.length,36);
let state=emptyState();
for(const q of data.questions){
 assert.ok(q.body&&q.explanation&&q.hint);assert.equal(q.type==='choice'?q.choices.length:0,q.type==='choice'?4:0);
 assert.equal(grade(q,q.answer).correct,true,q.id);
 assert.equal(grade(q,'').valid,false,q.id+' empty input');
 const wrong=q.type==='number'?String(BigInt(q.answer)+1n):q.choices.find(c=>c.key!==q.answer).key;
 assert.equal(grade(q,wrong).correct,false,q.id+' wrong answer');
 state=recordAttempt(state,q,grade(q,wrong));
 state=recordAttempt(state,q,grade(q,q.answer));
 assert.equal(state.answers[q.id].firstCorrect,false);
 assert.equal(state.answers[q.id].correct,true);assert.equal(state.answers[q.id].attempts,2);
}
for(const [input,expected]of [['２','2'],['  +００２  ','2'],['−３','-3'],['-0','0'],['1.5',null],['2e0',null],['0x2',null],['2+0',null],['2点',null],['',null],['  ',null],['Infinity',null]])assert.equal(normalizeInteger(input),expected,input);
assert.equal(Object.keys(validateState(state,data.questions).answers).length,360);
assert.throws(()=>validateState({...state,schema:2},data.questions));
assert.throws(()=>validateState({...state,answers:{G001:{...state.answers.G001,correct:false}}},data.questions));
assert.throws(()=>validateState({...state,answers:{G999:{...state.answers.G001}}},data.questions));
assert.throws(()=>validateState({...state,answers:{G001:{...state.answers.G001,at:'invalid'}}},data.questions));
for(const c of data.chapters){assert.equal(c.questionIds.length,10);assert.ok(c.intro);}
assert.equal(data.docs.length,5);
console.log('PASS: all 360 answer keys, wrong/empty input, retry with first-answer preservation, integer normalization, progress validation, 36 chapters and 5 resources.');
