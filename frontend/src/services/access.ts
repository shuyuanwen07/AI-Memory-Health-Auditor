export interface AccessStatus {
  mode:'local'|'protected';requires_sign_in:boolean;authenticated:boolean;
  expires_at:string|null;expires_in_seconds:number|null;csrf_token:string|null;
}
let csrfToken:string|null=null;
export function setWorkspaceCsrf(value:string|null){csrfToken=value;}
export function workspaceCsrf(){return csrfToken;}
export const SESSION_ENDED='mha-session-ended';
export const ACCESS_CHANGED='mha-access-changed';
export function clearPrivateWorkspaceDrafts(){
  for(const key of Object.keys(sessionStorage)) if(key.startsWith('mha-')) sessionStorage.removeItem(key);
}
