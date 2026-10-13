import { INTAKE_KEY, loadIntakeRecovery } from './intakeRecovery';
const valid={requestKey:'conversation-request-0001',text:'[User] I am based in Viseu.',messages:null,provider:'rule_based',model:null,conversationId:'C001'};
beforeEach(()=>sessionStorage.clear());
test('restores the frozen request and rejects corrupt browser checkpoints',()=>{
  sessionStorage.setItem(INTAKE_KEY,JSON.stringify(valid));expect(loadIntakeRecovery()).toEqual({...valid,sourceOrigin:'unknown'});
  for(const patch of [{requestKey:'bad'},{provider:'ollama'},{model:''},{provider:'openrouter',model:null},{messages:[]},{messages:[{role:'user',content:''}]},{text:null},{conversationId:42},{sourceOrigin:'participant'}]){
    sessionStorage.setItem(INTAKE_KEY,JSON.stringify({...valid,...patch}));expect(loadIntakeRecovery()).toBeNull();
  }
  sessionStorage.setItem(INTAKE_KEY,'broken json');expect(loadIntakeRecovery()).toBeNull();
});

test('restores an explicitly selected source origin',()=>{
  sessionStorage.setItem(INTAKE_KEY,JSON.stringify({...valid,sourceOrigin:'synthetic'}));
  expect(loadIntakeRecovery()).toEqual({...valid,sourceOrigin:'synthetic'});
});
