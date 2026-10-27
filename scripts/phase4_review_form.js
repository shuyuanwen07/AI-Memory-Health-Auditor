'use strict';
const payload=JSON.parse(document.getElementById('payload').textContent);
const M=payload.material;
let initial=structuredClone(payload.blank);
const storageKey='phase4-review-'+initial.material_sha256;
try {const saved=JSON.parse(localStorage.getItem(storageKey)||'null');if(saved?.material_sha256===initial.material_sha256)initial=saved;}catch{}
const element=(tag,text)=>{const e=document.createElement(tag);if(text!==undefined)e.textContent=text;return e;};
function selectField(parent,key,title,options,value,itemId){
 const label=element('label',title+' '),input=element('select');input.dataset.field=key;if(itemId)input.dataset.item=itemId;else input.dataset.profile='1';
 const empty=element('option','请选择');empty.value='';input.append(empty);
 for(const [v,t] of options){const option=element('option',t);option.value=v;input.append(option);}
 input.value=value===null||value===undefined?'':String(value);label.append(input);parent.append(label);
}
function checkboxGroup(parent,id,key,title,options,values){
 const box=element('details'),head=element('summary',title);box.append(head);
 for(const [value,text] of options){const label=element('label'),input=element('input');input.type='checkbox';input.value=value;input.dataset.item=id;input.dataset.field=key;input.dataset.multi='1';input.checked=Array.isArray(values)&&values.includes(value);label.append(input,document.createTextNode(text));box.append(label);}parent.append(box);
}
function textField(parent,id,key,title,value){const label=element('label',title),input=element('textarea');input.value=value||'';input.dataset.item=id;input.dataset.field=key;label.append(input);parent.append(label);}
const identity=document.getElementById('identity'),nameLabel=element('label','实际评审者姓名／化名'),name=element('input');name.type='text';name.id='reviewer';name.value=initial.reviewer_id;nameLabel.append(name);identity.append(nameLabel);
for(const [key,title] of [['has_seen_automated_results','是否已看过本批自动评分或AI逐条分析？'],['used_ai_assistance','本次判断是否使用AI辅助？']])selectField(identity,key,title,[['true','是'],['false','否']],initial[key]);
for(const [key,title] of [['completed_by_human','本人是真实评审者，已实际完成本表'],['completed_independently','本人独立判断，未与另一位评审者交流结论']]){const label=element('label'),input=element('input');input.type='checkbox';input.id=key;input.checked=initial[key]===true;label.append(input,document.createTextNode(title));identity.append(label);}
const forms=document.getElementById('forms');
for(const [history,messages] of Object.entries(M.histories)){
 const section=element('article'),head=element('h2','原始对话 '+history);section.append(head);for(const m of messages)section.append(element('p',m.message_id+': '+m.content));
 const note=element('label','来源中还有未列入参考单位的遗漏事实？如有请注明事实和消息ID；没有可留空。'),input=element('textarea');input.dataset.extra=history;input.value=initial.additional_missing_facts[history]||'';note.append(input);section.append(note);forms.append(section);
}
const validity=[['true','有效／应保留'],['false','无效／不应保留'],['uncertain','不确定']];
const dims=[['accuracy','Accuracy'],['freshness','Freshness'],['conflict_resolution','Conflict Resolution'],['appropriate_use','Appropriate Use'],['unclassified','无法唯一分类']];
const groups=[['candidate','候选记忆（27项）'],['reference','参考单位与抽取覆盖（24项）'],['relationship','来源关系对（9项）'],['response','实际回答（108条）'],['question','题目及参考有效性（48项）']];
for(const [kind,title] of groups){forms.append(element('h2',title));for(const [id,item] of Object.entries(M.items)){
 if(item.kind!==kind)continue;const section=element('article');section.dataset.card=id;section.append(element('h3',id+' / '+item.history));const row=initial.labels[id];
 const source=element('details');source.append(element('summary','展开原始对话'));for(const m of M.histories[item.history])source.append(element('p',m.message_id+': '+m.content));section.append(source);
 if(kind==='response'){
  section.append(element('p','问题：'+item.question),element('pre','实际回答：'+item.answer));
  selectField(section,'verdict','回答判断',[['pass','通过'],['fail','失败'],['uncertain','不确定／题目存在歧义']],row.verdict,id);
  selectField(section,'failure_dimension','失败时：实际错误类型（通过或不确定时留空）',dims,row.failure_dimension,id);
  selectField(section,'critical_error','是否符合严重错误定义？',[['yes','是'],['no','否'],['uncertain','不确定']],row.critical_error,id);
  section.append(element('small',M.critical_error_definition));
  checkboxGroup(section,id,'source_message_ids','选择支持判断的原始消息（至少一项）',M.histories[item.history].map(m=>[m.message_id,m.message_id+': '+m.content]),row.source_message_ids);
  if(item.study==='A'){
   section.append(element('p','按冻结定义逐项判断缺陷。遗漏／不知道不自动等于选错；如没有可对应的已知缺陷，请明确选择“无”。'));
   checkboxGroup(section,id,'defect_ids','冻结缺陷映射（必填；可选“无”）',[['__none__','无：没有对应的冻结缺陷'],...item.defects.map(d=>[d.defect_id,d.defect_id+': '+d.explanation])],Array.isArray(row.defect_ids)?(row.defect_ids.length?row.defect_ids:['__none__']):null);
  }
 }else if(kind==='question'){
  section.append(element('p','题目：'+item.question),element('p','待核实的参考行为：'+item.proposed_reference));selectField(section,'valid','检查清晰性、来源支持、时间范围、参考一致性与答案泄露',validity,row.valid,id);
 }else if(kind==='candidate'){
  section.append(element('p',item.text),element('small','原提议来源：'+item.proposed_source_ids.join(', ')));selectField(section,'valid','该候选记忆是否正确且应保留？',validity,row.valid,id);
 }else if(kind==='reference'){
  section.append(element('p','待审核的参考单位：'+item.text),element('small','来源：'+item.source_ids.join(', ')));selectField(section,'valid','此参考单位是否有完整来源支持？',validity,row.valid,id);selectField(section,'coverage','有效抽取是否完整覆盖此参考单位？',[['full','完整覆盖'],['partial','仅部分覆盖'],['none','未覆盖'],['uncertain','不确定']],row.coverage,id);
  checkboxGroup(section,id,'candidate_ids','选择提供覆盖的有效候选记忆（完整覆盖时必须选择）',item.candidate_ids.map(cid=>[cid,cid+': '+M.items[cid].text]),row.candidate_ids);
 }else{
  section.append(element('p','来源端：'+item.from_text),element('p','目标端：'+item.to_text));selectField(section,'relationship_type','仅依据原始对话判定关系',[['UPDATE','UPDATE'],['CONFLICT','CONFLICT'],['CONTEXTUAL_OVERRIDE','CONTEXTUAL_OVERRIDE'],['NONE','无此关系'],['uncertain','不确定']],row.relationship_type,id);
 }
 textField(section,id,'note','判断理由／歧义说明',row.note);forms.append(section);
}}
function gather(){
 const result=structuredClone(payload.blank);result.reviewer_id=name.value.trim();for(const key of ['completed_by_human','completed_independently'])result[key]=document.getElementById(key).checked;
 document.querySelectorAll('[data-profile]').forEach(input=>{result[input.dataset.field]=input.value===''?null:input.value==='true';});
 document.querySelectorAll('[data-extra]').forEach(input=>{result.additional_missing_facts[input.dataset.extra]=input.value;});
 document.querySelectorAll('[data-item]:not([data-multi])').forEach(input=>{let value=input.value;if(input.tagName==='SELECT')value=value===''?null:value==='true'?true:value==='false'?false:value;result.labels[input.dataset.item][input.dataset.field]=value;});
 for(const [id,item] of Object.entries(M.items)){
  if(item.kind==='response'){
   const selected=field=>Array.from(document.querySelectorAll('input[data-item="'+id+'"][data-field="'+field+'"]:checked')).map(x=>x.value);
   result.labels[id].source_message_ids=selected('source_message_ids');
   if(item.study==='A'){const ids=selected('defect_ids');if(ids.includes('__none__')&&ids.length>1)throw Error(id+'：不能同时选择“无”和具体缺陷');result.labels[id].defect_ids=ids.includes('__none__')?[]:ids.length?ids:null;}
  }else if(item.kind==='reference')result.labels[id].candidate_ids=Array.from(document.querySelectorAll('input[data-item="'+id+'"][data-field="candidate_ids"]:checked')).map(x=>x.value);
 }
 return result;
}
function save(download){try{const result=gather();let stored=true;try{localStorage.setItem(storageKey,JSON.stringify(result));}catch{stored=false;}if(download){const blob=new Blob([JSON.stringify(result,null,2)],{type:'application/json'}),url=URL.createObjectURL(blob),a=element('a');a.href=url;a.download='review-result.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}document.getElementById('status').textContent=download?'结果已导出；完整性和正式资格由分析脚本验证。':stored?'草稿已保存到本机浏览器。':'浏览器禁止本地草稿；请点击下载结果保存。';}catch(e){document.getElementById('status').textContent=e.message;}}
document.getElementById('save').onclick=()=>save(false);document.getElementById('export').onclick=()=>save(true);
