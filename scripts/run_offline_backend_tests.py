"""Run backend pytest with isolated defaults, a disposable DB and an external socket guard.

Examples:
    python scripts/run_offline_backend_tests.py
    python scripts/run_offline_backend_tests.py -- -q tests/test_target_identity_evidence.py
    python /scripts/run_offline_backend_tests.py --backend-root /app

This is a test harness, not a sandbox for hostile code. Child processes inherit
isolated defaults and no real provider keys but are not socket-instrumented.
"""
import argparse
import ipaddress
import json
import os
from pathlib import Path
import socket
import sys
import tempfile
from datetime import datetime, timezone


def main():
    parser=argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--backend-root',type=Path)
    parser.add_argument('--evidence-dir',type=Path)
    options,pytest_args=parser.parse_known_args()
    if pytest_args[:1]==['--']:pytest_args=pytest_args[1:]
    if not pytest_args:pytest_args=['-q','tests']
    candidates=([options.backend_root] if options.backend_root else
        ([Path('/app')] if Path(__file__).resolve().parent == Path('/scripts') else [])
        + [Path(__file__).resolve().parents[1]/'backend',Path('/app'),Path.cwd(),Path.cwd()/'backend'])
    backend=next((path.resolve() for path in candidates if (path/'app').is_dir() and (path/'tests').is_dir()),None)
    if backend is None:parser.error('Cannot locate backend app/tests; pass --backend-root explicitly.')
    evidence_dir=(options.evidence_dir or backend/'.engineering-smoke/offline-tests').resolve()
    evidence_dir.mkdir(parents=True,exist_ok=True)
    run=Path(tempfile.mkdtemp(prefix='isolated-suite-',dir=evidence_dir))
    os.chdir(backend)
    removed=[]
    for name in list(os.environ):
        if 'API_KEY' in name.upper() or 'API_TOKEN' in name.upper() or name in {'HF_TOKEN','HUGGING_FACE_HUB_TOKEN','GOOGLE_APPLICATION_CREDENTIALS'}:
            removed.append(name);os.environ.pop(name,None)
    os.environ.update(PIPELINE_PROVIDER='rule_based',EVALUATOR_PROVIDER='rule_based',
        DATABASE_URL=f'sqlite:///{run / "application-global.sqlite"}',AUTO_CREATE_SCHEMA='false')
    # Environment setup precedes every application import, including pytest collection.
    # Tests also import the repository's scripts package. Direct invocation
    # sets sys.path[0] to scripts/, not the repository root; resolve it before
    # chdir/collection instead of relying on the caller's PYTHONPATH.
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
    sys.path.insert(0,str(backend))
    import pytest

    attempts=[]
    originals={name:getattr(socket,name) for name in ('getaddrinfo','create_connection')}
    original_connect=socket.socket.connect
    original_connect_ex=socket.socket.connect_ex

    def local(host):
        if host is None:return True # server-side local address enumeration
        if isinstance(host,bytes):host=host.decode('ascii',errors='replace')
        if not isinstance(host,str):return False
        if host.lower().rstrip('.')=='localhost':return True
        try:return ipaddress.ip_address(host.split('%',1)[0]).is_loopback
        except ValueError:return False

    def check(host,port,operation):
        if local(host):return
        # Never record URLs, request bodies, credentials or exception contents.
        attempts.append({'operation':operation,'destination_kind':'external_or_unknown','port':port if isinstance(port,int) else None,
            'test':os.getenv('PYTEST_CURRENT_TEST','collection_or_session').split(' ')[0].split('[')[0][:400]})
        raise OSError('Offline full-suite guard blocked an external network destination.')

    def guarded_getaddrinfo(host,port,*args,**kwargs):
        check(host,port,'getaddrinfo');return originals['getaddrinfo'](host,port,*args,**kwargs)

    def guarded_create_connection(address,*args,**kwargs):
        check(address[0],address[1],'create_connection');return originals['create_connection'](address,*args,**kwargs)

    def guarded_connect(sock,address):
        if sock.family!=socket.AF_UNIX:check(address[0],address[1],'connect')
        return original_connect(sock,address)

    def guarded_connect_ex(sock,address):
        if sock.family!=socket.AF_UNIX:check(address[0],address[1],'connect_ex')
        return original_connect_ex(sock,address)

    class OfflineGuard:
        def pytest_configure(self,config):
            socket.getaddrinfo=guarded_getaddrinfo;socket.create_connection=guarded_create_connection
            socket.socket.connect=guarded_connect;socket.socket.connect_ex=guarded_connect_ex
        def pytest_sessionfinish(self,session,exitstatus):
            record={'created_at':datetime.now(timezone.utc).isoformat(),'pytest_exit_status':int(exitstatus),
                'external_network_block_attempts':len(attempts),'guard_attempts':attempts,
                'removed_credential_variable_names':sorted(removed),'pipeline_provider':'rule_based','evaluator_provider':'rule_based',
                'global_database':str(run/'application-global.sqlite'),'auto_create_schema':False,
                'isolation_boundary':'Python socket DNS/connect/create_connection guarded in this pytest process; loopback and Unix sockets allowed. Child processes inherit isolated provider/database/no-real-key environment; native libraries and child processes are not socket-instrumented by this plugin. Provider-specific tests may install synthetic credentials and mocks.'}
            (run/'isolation-evidence.json').write_text(json.dumps(record,indent=2)+'\n')
            print('\nISOLATION_EVIDENCE '+json.dumps({'path':str(run/'isolation-evidence.json'),'external_network_block_attempts':len(attempts),'pytest_exit_status':int(exitstatus)}),flush=True)

    print('ISOLATED_SUITE '+json.dumps({'directory':str(run),'provider_defaults':'rule_based','auto_create_schema':False,'removed_credential_variables':sorted(removed)}),flush=True)
    try:
        code=pytest.main(['-o',f'cache_dir={run / ".pytest_cache"}',*pytest_args],plugins=[OfflineGuard()])
    finally:
        socket.getaddrinfo=originals['getaddrinfo'];socket.create_connection=originals['create_connection']
        socket.socket.connect=original_connect;socket.socket.connect_ex=original_connect_ex
    return int(code)


if __name__ == "__main__":
    raise SystemExit(main())
