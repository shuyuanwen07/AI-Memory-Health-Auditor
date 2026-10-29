"""Reassess one previously saved synthetic demo through the running API.

This performs model calls and stores a separate new audit; it never overwrites
the original. It is a product integration check, not independent validation.
"""
import json
from pathlib import Path
import httpx


def main():
    source='RUNA3DF5BE780A549538D706F50E82327ED'
    base='http://127.0.0.1:8000/api/v1'
    client=httpx.Client(timeout=180)
    prepared=client.post(f'{base}/audits/{source}/reassessment',json={
        'evaluator_provider':'openrouter_taxonomy','evaluator_model':'openai/gpt-6-luna'})
    prepared.raise_for_status(); run=prepared.json(); run_id=run['run_id']
    if run['status']=='TESTS_EXECUTED':
        response=client.post(f'{base}/audits/{run_id}/evaluate');response.raise_for_status()
    elif run['status']!='COMPLETED':
        raise RuntimeError(f'New reassessment needs attention: {run_id}, status {run["status"]}')
    saved=client.get(f'{base}/audits/{run_id}');saved.raise_for_status()
    result=client.get(f'{base}/audits/{run_id}/results');result.raise_for_status()
    data=result.json(); current=saved.json()
    receipt={'format':'taxonomy-product-reassessment-check-v1','source_run_id':source,'run_id':run_id,
             'status':current['status'],'provider':current['evaluator_provider'],'model':current['evaluator_model'],
             'result_keys':sorted(data.keys()),'scope':'Synthetic product integration check, not independent validation.',
             'original_answers_reused':True}
    path=Path('/ac3-results/paired-authorized-retest-20261029-v1/product-reassessment-check.json')
    with path.open('x',encoding='utf8') as f:json.dump(receipt,f,indent=2);f.write('\n')
    print(json.dumps(receipt))


if __name__=='__main__':main()
