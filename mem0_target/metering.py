"""Observe native SDK inference calls without saving prompts or responses."""
import threading
import time

VERSION = 'native-sdk-inference-meter-v1'


class InferenceMeter:
    def __init__(self):
        self.events = []
        self.lock = threading.Lock()
        self.coverage = {'llm': False, 'embedding': False}

    def checkpoint(self):
        with self.lock:
            return len(self.events)

    def observe(self, kind, method, *args, **kwargs):
        started = time.perf_counter()
        event = {'kind': kind, 'success': False}
        try:
            response = method(*args, **kwargs)
            event['success'] = True
            for field in ('prompt_eval_count', 'eval_count'):
                value = response.get(field) if hasattr(response, 'get') else getattr(response, field, None)
                if type(value) is int and value >= 0:
                    event[field] = value
            return response
        finally:
            event['latency_ms'] = round((time.perf_counter() - started) * 1000, 2)
            with self.lock:
                self.events.append(event)

    def receipt(self, checkpoint):
        with self.lock:
            events = list(self.events[checkpoint:])
        result = {'version': VERSION, 'coverage': dict(self.coverage), 'events': events,
                  'monetary_cost': None,
                  'notice': 'SDK chat/embed attempts only; excludes model setup, network retries below the SDK call, vector operations and hardware cost. Reported tokens may be unavailable. No dollar cost is inferred.'}
        for kind in ('llm', 'embedding'):
            rows = [e for e in events if e['kind'] == kind]
            result[kind + '_attempts'] = len(rows) if self.coverage[kind] else None
            result[kind + '_failures'] = sum(not e['success'] for e in rows) if self.coverage[kind] else None
        return result


class MeteredClient:
    def __init__(self, client, meter, kind, method):
        self.client, self.meter, self.kind, self.method = client, meter, kind, method

    def __getattr__(self, name):
        value = getattr(self.client, name)
        if name == self.method:
            return lambda *args, **kwargs: self.meter.observe(self.kind, value, *args, **kwargs)
        return value


def instrument(memory):
    meter = getattr(memory, '_audit_inference_meter', None)
    if meter is not None:
        return meter
    meter = InferenceMeter()
    for kind, owner_name, method in (('llm', 'llm', 'chat'), ('embedding', 'embedding_model', 'embed')):
        owner = getattr(memory, owner_name, None)
        client = getattr(owner, 'client', None)
        if client is not None and callable(getattr(client, method, None)):
            owner.client = MeteredClient(client, meter, kind, method)
            meter.coverage[kind] = True
    memory._audit_inference_meter = meter
    return meter
