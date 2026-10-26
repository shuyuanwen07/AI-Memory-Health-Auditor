"""Actual HTTP boundary evidence and pure offline parameter reconstruction."""
import json
from pathlib import Path
from stability_configuration import role_settings, answer_validation_enabled


def required(protocol):
    return protocol.get('request_contract_required') is True


def expected_contract(protocol, role, *, instructions, prompt, schema_name=None, schema=None, provider_options=None):
    from app.target_ai.openrouter import (CHAT_COMPLETIONS_URL, request_options,
        build_openrouter_target_payload, build_openrouter_json_payload)
    from app.target_ai.request_contracts import build_openrouter_request_contract
    controls=role_settings(protocol,role)
    routing=request_options()['provider'] if provider_options is None else provider_options
    common=dict(model=protocol['model'],instructions=instructions,prompt=prompt,
                max_output_tokens=controls['output_token_limit'],reasoning_effort=controls['reasoning_effort'],provider_options=routing)
    if role=='target_answer':payload=build_openrouter_target_payload(**common,temperature=protocol.get('temperature',0))
    else:payload=build_openrouter_json_payload(**common,schema_name=schema_name,schema=schema)
    return build_openrouter_request_contract(url=CHAT_COMPLETIONS_URL,payload=payload,role=role)


def expected_roles(protocol, *, question, selected_record_count):
    from app.memory_agent.identity_applicability import identity_analysis_applicable
    roles={'target_answer',protocol.get('assessment_role','benchmark_pilot_assessment')}
    profile=protocol.get('target_memory_profile',{})
    if answer_validation_enabled(profile):roles.add('target_answer_validation')
    configuration='strong' if protocol['strategies']==['strong_rule_based'] else 'weak'
    if identity_analysis_applicable(question=question,selected_record_count=selected_record_count,
            configuration=configuration,identity_analysis=profile.get('identity_analysis','off')):
        roles.add('target_identity_evidence')
    return roles


def validate_contract(protocol, role, contract):
    settings=role_settings(protocol,role)
    if not isinstance(contract,dict) or contract.get('version')!='openrouter-request-contract-v1':raise ValueError('Missing versioned wire contract.')
    if contract.get('role')!=role or contract.get('model')!=protocol['model'] or contract.get('provider_name')!='openrouter':raise ValueError('Wire role/model differs from frozen protocol.')
    if contract.get('max_tokens')!={'present':True,'value':settings['output_token_limit']}:raise ValueError('Wire total output cap differs from protocol.')
    expected=({'present':True,'value':{'effort':settings['reasoning_effort']}} if settings['reasoning_effort'] is not None else {'present':False})
    if contract.get('reasoning')!=expected:raise ValueError('Wire reasoning presence/value differs from protocol.')
    routing=contract.get('provider',{}).get('value',{})
    if routing.get('require_parameters') is not True or routing.get('allow_fallbacks') is not False:raise ValueError('Wire parameter support/fallback policy differs.')


def validate_events(protocol, events, role, expected, execution=None):
    from app.target_ai.request_contracts import request_contract_sha256
    matching=[event for event in events if event.get('role')==role]
    if not matching:raise ValueError('No actual HTTP attempt receipt for requested role.')
    for index,event in enumerate(matching,1):
        contract=event.get('request_contract')
        validate_contract(protocol,role,contract)
        if contract!=expected or event.get('request_contract_sha256')!=request_contract_sha256(contract):raise ValueError('Actual wire payload differs from pure reconstruction.')
        if event.get('attempt_index')!=index or event.get('status') not in {'response','transport_error'}:raise ValueError('Invalid HTTP attempt sequence/status.')
        if event.get('observer_error_type'):raise ValueError('HTTP wire observer failed.')
    if execution is not None:
        if execution.get('request_attempts')!=len(matching):raise ValueError('HTTP attempt count differs from execution meter.')
        saved=execution.get('request_contract_attempts')
        if saved!=matching:raise ValueError('Meter and actual sidecar attempts differ.')
    return len(matching)


class WireObserver:
    def __init__(self,directory,protocol):
        self.path=Path(directory)/'actual-wire-attempt-receipts.json'
        self.protocol=protocol;self.expected={};self.events=[]
        self.required_roles={'target_answer',protocol.get('assessment_role','benchmark_pilot_assessment')}
        self.target_plan=None
        if self.path.exists():raise ValueError('Never overwrite actual wire evidence.')

    def set_target_plan(self,*,question,selected_record_count):
        self.required_roles=expected_roles(self.protocol,question=question,selected_record_count=selected_record_count)
        self.target_plan={'selected_record_count':selected_record_count,'auxiliary_required':'target_identity_evidence' in self.required_roles}
        if 'target_identity_evidence' in self.required_roles and not any(event.get('role')=='target_identity_evidence' for event in self.events):
            raise ValueError('Applicable auxiliary stage missing before final answer.')

    def prepare(self,role,**kwargs):
        value=expected_contract(self.protocol,role,**kwargs)
        validate_contract(self.protocol,role,value)
        self.expected[role]=value
        return value

    def __call__(self,event):
        role=event.get('role');contract=event.get('request_contract')
        validate_contract(self.protocol,role,contract)
        if self.expected.get(role)!=contract:raise ValueError('Actual HTTP payload differs before send.')
        if event.get('phase')=='after_send':
            self.events.append({key:value for key,value in event.items() if key!='phase'})
            data={'version':'http-wire-attempt-receipts-v1','provenance':'actual_http_transport_boundary',
                  'reconstructed':False,'attempts':self.events}
            self.path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')


def read_wire_events(directory,protocol):
    if not required(protocol):return []
    value=json.loads((Path(directory)/'actual-wire-attempt-receipts.json').read_text())
    if (value.get('version')!='http-wire-attempt-receipts-v1' or value.get('reconstructed') is not False
            or value.get('provenance')!='actual_http_transport_boundary'):raise ValueError('Invalid actual wire provenance.')
    return value['attempts']
