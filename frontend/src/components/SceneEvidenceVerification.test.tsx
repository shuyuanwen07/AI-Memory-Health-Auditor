import {render,screen,waitFor} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {test,expect,vi,beforeEach} from 'vitest';
import {SceneEvidenceVerification} from './SceneEvidenceVerification';
const {verify}=vi.hoisted(()=>({verify:vi.fn()}));vi.mock('../services/api',()=>({api:{verifySceneEvidence:verify}}));
beforeEach(()=>verify.mockReset());
const file=(content:unknown)=>new File([JSON.stringify(content)],'comparison.json',{type:'application/json'});
test('checks a selected file and clearly distinguishes a server match',async()=>{
 verify.mockResolvedValue({status:'matches_current_snapshot',matches_current_snapshot:true,message:'Matches saved data; not independent validation.'});
 const user=userEvent.setup();render(<SceneEvidenceVerification runId="private-plan"/>);
 await user.upload(screen.getByLabelText('Exported scene comparison JSON'),file({version:'fixture'}));
 await user.click(screen.getByRole('button',{name:'Verify exported comparison'}));
 expect(await screen.findByText('Matches current saved evidence')).toBeInTheDocument();
 expect(verify).toHaveBeenCalledWith('private-plan',{version:'fixture'});
 expect(screen.queryByText('private-plan')).not.toBeInTheDocument();
});
test('invalid replacement removes the previous result and prevents submission',async()=>{
 verify.mockResolvedValue({status:'saved_evidence_changed',matches_current_snapshot:false,message:'Saved evidence changed.'});
 const user=userEvent.setup();render(<SceneEvidenceVerification runId="plan"/>);
 await user.upload(screen.getByLabelText('Exported scene comparison JSON'),file({}));
 await user.click(screen.getByRole('button',{name:'Verify exported comparison'}));
 expect(await screen.findByText('Does not match current snapshot')).toBeInTheDocument();
 await user.upload(screen.getByLabelText('Exported scene comparison JSON'),new File(['broken-json'],'broken.json',{type:'application/json'}));
 expect(screen.getByRole('alert')).toHaveTextContent('not valid JSON');
 expect(screen.getByRole('button',{name:'Verify exported comparison'})).toBeDisabled();
 expect(screen.queryByText('Does not match current snapshot')).not.toBeInTheDocument();
});
test('a changed selected plan ignores the previous pending check',async()=>{
 let resolve!:(value:object)=>void;verify.mockReturnValue(new Promise(r=>resolve=r));
 const user=userEvent.setup();const {rerender}=render(<SceneEvidenceVerification runId="old-plan"/>);
 await user.upload(screen.getByLabelText('Exported scene comparison JSON'),file({}));
 await user.click(screen.getByRole('button',{name:'Verify exported comparison'}));
 rerender(<SceneEvidenceVerification runId="new-plan"/>);
 resolve({status:'matches_current_snapshot',matches_current_snapshot:true,message:'Old reply.'});
 await waitFor(()=>expect(screen.getByRole('button',{name:'Verify exported comparison'})).toBeEnabled());
 expect(screen.queryByText('Matches current saved evidence')).not.toBeInTheDocument();
});
test('missing plan and running execution prevent checking',async()=>{
 const user=userEvent.setup();const {rerender}=render(<SceneEvidenceVerification runId=""/>);
 await user.upload(screen.getByLabelText('Exported scene comparison JSON'),file({}));
 expect(screen.getByRole('button',{name:'Verify exported comparison'})).toBeDisabled();
 rerender(<SceneEvidenceVerification runId="plan" executionBusy/>);
 expect(screen.getByRole('button',{name:'Verify exported comparison'})).toBeDisabled();
 expect(verify).not.toHaveBeenCalled();
});
