import { memoryReviewConcerns } from './memoryReviewConcerns';
import type { Memory, ConversationMessage } from '../types/domain';
const memory:Memory={memory_id:'M1',conversation_id:'C1',canonical_value:'The Rowan meeting must use Zoom.',source_message_ids:['S1'],status:'candidate',relationships:[]};
const source=(content:string,id='S1'):ConversationMessage=>({message_id:id,role:'user',content,timestamp:'2026-01-01T00:00:00Z'});
test.each(['Neither Laurel meeting requirement has been withdrawn.','Both Laurel requirements remain active.'])('flags a replacement link contradicting continuing requirements: %s',content=>{
  const continuing:Memory={...memory,canonical_value:content,relationships:[{type:'UPDATE',target_memory_id:'M0'}]};
  expect(memoryReviewConcerns(continuing,[continuing],[source(content)])[0].title).toContain('actually replaced');
  expect(continuing.relationships[0].type).toBe('UPDATE');
  expect(memoryReviewConcerns({...continuing,relationships:[]},[continuing],[source(content)])).toEqual([]);
  expect(memoryReviewConcerns(continuing,[continuing],[source('The earlier Laurel requirement has been withdrawn.')])).toEqual([]);
});
test.each(['For Rowan, only Zoom is allowed.','The Rowan meeting must use Zoom only.'])('surfaces a possibly weakened exclusive requirement: %s',content=>{
  const concerns=memoryReviewConcerns(memory,[memory],[source(content)]);
  expect(concerns).toHaveLength(1);expect(concerns[0].sources[0].content).toBe(content);
});
test('does not warn about a retained restriction, an unrelated source, or not-only wording',()=>{
  expect(memoryReviewConcerns({...memory,canonical_value:'Rowan must use Zoom only.'},[memory],[source('Only Zoom is allowed.')])).toEqual([]);
  expect(memoryReviewConcerns(memory,[memory],[source('Only Zoom is allowed.','UNRELATED')])).toEqual([]);
  expect(memoryReviewConcerns(memory,[memory],[source('Not only Zoom is allowed; Teams is also allowed.')])).toEqual([]);
});
test('flags replacing a general preference with a project requirement while preserving the proposed relationship',()=>{
  const preference={...memory,memory_id:'M0',canonical_value:'Preference for Go.',source_message_ids:['S0']};
  const project:Memory={...memory,canonical_value:'Rowan project requires Java.',source_message_ids:['S1'],relationships:[{type:'UPDATE',target_memory_id:'M0'}]};
  const messages=[source('I generally prefer Go for personal tools.','S0'),source('For the Rowan project, Java is required instead of Go.')];
  expect(memoryReviewConcerns(project,[preference,project],messages)[0].title).toContain('task-specific exception');
  expect(project.relationships[0].type).toBe('UPDATE');
  expect(memoryReviewConcerns({...project,relationships:[{type:'CONTEXTUAL_OVERRIDE',target_memory_id:'M0'}]},[preference,project],messages)).toEqual([]);
  expect(memoryReviewConcerns(project,[preference,project],[source('For the Rowan project, I generally prefer Go.','S0'),messages[1]])).toEqual([]);
});

test.each(['UPDATE','CONFLICT'] as const)('shows equivalent source rules behind a proposed %s without changing the decision',type=>{
  const previous:Memory={...memory,memory_id:'M0',source_message_ids:['S0']};
  const current:Memory={...memory,canonical_value:'Only Teams is permitted for the Clover review meeting.',relationships:[{type,target_memory_id:'M0'}]};
  const messages=[source('For the Clover review meeting, only Microsoft Teams is allowed.','S0'),source('Only Teams is permitted for the Clover review meeting.')];
  const concerns=memoryReviewConcerns(current,[previous,current],messages);
  expect(concerns[0].title).toContain('say the same thing');
  expect(concerns[0].sources.map(item=>item.content)).toEqual(messages.map(item=>item.content));
  expect(current.relationships[0].type).toBe(type);
  expect(memoryReviewConcerns(current,[previous,current],[messages[0],source('Only Zoom is permitted for the Clover review meeting.')])).toEqual([]);
  expect(memoryReviewConcerns(current,[previous,current],[messages[0],source('Only Teams is permitted for the Clover review meeting with recording disabled.')])).toEqual([]);
});
