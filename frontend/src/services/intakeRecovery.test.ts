import { INTAKE_KEY, loadIntakeRecovery } from './intakeRecovery';
const valid={requestKey:'conversation-request-0001',text:'[User] I am based in Viseu.',messages:null,provider:'rule_based',model:null,conversationId:'C001'};
beforeEach(()=>sessionStorage.clear());
test('restores the frozen request and rejects corrupt browser checkpoints',()=>{
  sessionStorage.setItem(INTAKE_KEY,JSON.stringify(valid));expect(loadIntakeRecovery()).toEqual({...valid,sourceOrigin:'unknown'});
  for(const patch of [{requestKey:'bad'},{provider:'unsupported'},{model:''},{provider:'openrouter',model:null},{messages:[]},{messages:[{role:'user',content:''}]},{text:null},{conversationId:42},{sourceOrigin:'participant'}]){
    sessionStorage.setItem(INTAKE_KEY,JSON.stringify({...valid,...patch}));expect(loadIntakeRecovery()).toBeNull();
  }
  sessionStorage.setItem(INTAKE_KEY,'broken json');expect(loadIntakeRecovery()).toBeNull();
});

test('restores an explicitly selected source origin',()=>{
  sessionStorage.setItem(INTAKE_KEY,JSON.stringify({...valid,sourceOrigin:'synthetic'}));
  expect(loadIntakeRecovery()).toEqual({...valid,sourceOrigin:'synthetic'});
});


test('restores a saved local extraction with its source and model unchanged',()=>{
 const checkpoint={...valid,provider:'ollama',model:'qwen3:1.7b',sourceOrigin:'synthetic',messages:[{message_id:'SYN101',role:'user',content:'I live in Adelaide.',timestamp:'2026-10-01T10:00:00Z'}]};
 sessionStorage.setItem(INTAKE_KEY,JSON.stringify(checkpoint));
 expect(loadIntakeRecovery()).toEqual(checkpoint);
});
