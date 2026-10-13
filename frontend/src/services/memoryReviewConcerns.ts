import type { ConversationMessage, Memory } from '../types/domain';
export interface MemoryReviewConcern { title:string; detail:string; sources:ConversationMessage[] }
function exclusiveRuleKey(text:string):string|null {
  const matches=[...text.matchAll(/\bonly\s+(Zoom|(?:Microsoft\s+)?Teams|Webex|Google\s+Meet)\s+(is|will\s+be)\s+(?:allowed|permitted)\b/gi)];
  if(matches.length!==1)return null;
  const match=matches[0];const prefix=text.slice(0,match.index).split(/[.!?;\n]/).pop()??'';
  if(/\b(?:not|if|unless|whether|perhaps|maybe|suppose|imagine)\b/i.test(prefix))return null;
  const scope=(text.slice(0,match.index)+' '+text.slice(match.index!+match[0].length)).toLowerCase().replace(/[^\p{L}\p{N}_]+/gu,' ').trim();
  return JSON.stringify([match[1].replace(/^Microsoft\s+/i,'').toLowerCase(),scope,match[2].toLowerCase().replace(/\s+/g,' ')]);
}
/** Bounded source-wording checks, not a semantic verdict or automatic repair. */
export function memoryReviewConcerns(memory:Memory, memories:Memory[], messages:ConversationMessage[]):MemoryReviewConcern[] {
  const sources=messages.filter(message=>memory.source_message_ids.includes(message.message_id));
  const concerns:MemoryReviewConcern[]=[];
  const equivalentSources:ConversationMessage[]=[];
  for(const relation of memory.relationships){
    if(relation.type!=='UPDATE'&&relation.type!=='CONFLICT')continue;
    const previous=memories.find(item=>item.memory_id===relation.target_memory_id);
    if(!previous)continue;
    for(const current of sources)for(const prior of messages.filter(item=>previous.source_message_ids.includes(item.message_id))){
      const key=exclusiveRuleKey(current.content);
      if(key!==null&&key===exclusiveRuleKey(prior.content))equivalentSources.push(prior,current);
    }
  }
  if(equivalentSources.length)concerns.push({title:'Check whether these requirements say the same thing',detail:'The linked source statements appear to express the same exclusive platform requirement. An update or conflict may be unnecessary. Compare the full source wording before accepting.',sources:[...new Map(equivalentSources.map(item=>[item.message_id,item])).values()]});
  const exclusiveSources=sources.filter(source=>{
    const match=/\b(?:only\s+(Zoom|(?:Microsoft\s+)?Teams|Webex|Google\s+Meet)\b|(Zoom|(?:Microsoft\s+)?Teams|Webex|Google\s+Meet)\s+only\b)/i.exec(source.content);
    if(!match || /\bnot\s*$/i.test(source.content.slice(0,match.index)))return false;
    const platform=(match[1] ?? match[2]).replace(/^Microsoft\s+/i,'').toLowerCase();
    return memory.canonical_value.toLowerCase().includes(platform)
      && !/\b(?:only|solely|exclusively|exclusive)\b/i.test(memory.canonical_value);
  });
  if(exclusiveSources.length)concerns.push({title:'Check the “only” restriction',detail:'The source restricts the allowed meeting platform, but this memory may have weakened that restriction. Compare the full wording and edit it if needed.',sources:exclusiveSources});
  const projectSources=sources.filter(source=>/\b(?:project|assignment|task)\b/i.test(source.content)&&/\b(?:required|requires?|must)\b/i.test(source.content));
  const replacesPreference=memory.relationships.some(relation=>{
    if(relation.type!=='UPDATE')return false;
    const previous=memories.find(item=>item.memory_id===relation.target_memory_id);
    if(!previous)return false;
    return messages.some(source=>previous.source_message_ids.includes(source.message_id)
      && /\b(?:generally prefer|general preference|usual preference|personal tools)\b/i.test(source.content)
      && !/\b(?:project|assignment|task)\b/i.test(source.content));
  });
  if(projectSources.length&&replacesPreference)concerns.push({title:'Check whether this is a task-specific exception',detail:'This project requirement is linked as replacing a general preference. The preference may still apply elsewhere. Check whether the relationship should be a task-specific exception instead.',sources:projectSources});
  const unchangedSources=sources.filter(source=>/\b(?:neither\b[^.!?]{0,120}\b(?:has|have)\s+been\s+(?:withdrawn|revoked)|(?:both|all)\b[^.!?]{0,120}\b(?:remain|are still)\s+(?:active|in force))\b/i.test(source.content));
  if(unchangedSources.length&&memory.relationships.some(relation=>relation.type==='UPDATE'))concerns.push({title:'Check whether any requirement was actually replaced',detail:'The source says the requirements remain active, but this memory is linked as replacing earlier information. Check the related memories before accepting this change.',sources:unchangedSources});
  return concerns;
}
