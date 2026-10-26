"""Exact source span catalog. No network, question, answers, retrieval or source mutation.

All offsets are Unicode codepoints. No normalization or truncation of source text.
The caller must preserve original selected_records narrative separately in the prompt.
"""
from dataclasses import dataclass
import hashlib
import json
import re

VERSION = 'identity-exact-span-catalog-v1'
MAX_RECORDS = 500
MAX_RECORD_CHARACTERS = 100000
MAX_CONTEXT_CHARACTERS = 100000
MAX_CANDIDATES_PER_RECORD = 128
MAX_CANDIDATES = 2048
MAX_CATALOG_BYTES = 524288
MAX_SPAN = 800


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(',', ':'), allow_nan=False).encode()).hexdigest()


@dataclass(frozen=True)
class Candidate:
    candidate_id: str
    record_index: int
    char_start: int
    char_end: int
    occurrence: int
    content_sha256: str
    quote: str


@dataclass(frozen=True)
class Catalog:
    version: str
    contents: tuple[str, ...]
    content_snapshot_sha256: str
    candidates: tuple[Candidate, ...]
    coverage_gaps: tuple[tuple[int, int, int], ...]
    catalog_sha256: str


def _trim_span(text, start, end):
    # Choose bounds in the original string; do not normalize internal bytes.
    while start < end and text[start].isspace(): start += 1
    while end > start and text[end - 1].isspace(): end -= 1
    return start, end


def _partition(text, pattern):
    start = 0
    for match in re.finditer(pattern, text):
        end = match.end()
        yield _trim_span(text, start, end)
        start = end
    yield _trim_span(text, start, len(text))


def _occurrence(text, quote, expected_start):
    start = -1
    for occurrence in range(501):
        start = text.find(quote, start + 1)
        if start == expected_start: return occurrence
        if start < 0 or start > expected_start: break
    raise ValueError('Occurrence cannot be represented by existing strict quote contract.')


def build_catalog(contents):
    if type(contents) is not list or any(type(t) is not str for t in contents):
        raise ValueError('Only selected decoded record contents are accepted.')
    if (len(contents) > MAX_RECORDS or any(len(t) > MAX_RECORD_CHARACTERS for t in contents)
            or sum(len(t) for t in contents) > MAX_CONTEXT_CHARACTERS):
        raise ValueError('Catalog source bound exceeded; no API permitted.')
    snapshot = digest(contents)
    rows = []; gaps = []
    for index, text in enumerate(contents, 1):
        spans = set()
        if text.strip() and len(text) <= MAX_SPAN: spans.add((0, len(text)))
        # Stable topic-independent natural sentence and punctuation clause spans.
        # Delimiter punctuation belongs to its preceding exact span.
        sentences = list(_partition(text, r'[.!?](?:[\"\u201d\u2019]*)?(?=\s|$)|\n+'))
        clauses = list(_partition(text, r'[,;:](?=\s|$)|[.!?](?:[\"\u201d\u2019]*)?(?=\s|$)|\n+'))
        for start, end in sentences + clauses:
            if start < end and end - start <= MAX_SPAN: spans.add((start, end))
        for start, end in clauses:
            if end - start > MAX_SPAN: gaps.append((index, start, end))
        if text.strip() and not spans:
            raise ValueError('Record has no representable natural span; no API permitted.')
        if len(spans) > MAX_CANDIDATES_PER_RECORD:
            raise ValueError('Per-record catalog bound exceeded; no pruning permitted.')
        for start, end in sorted(spans):
            quote = text[start:end]
            material = [VERSION, snapshot, index, start, end, hashlib.sha256(text.encode()).hexdigest()]
            rows.append(Candidate('C' + str(len(rows) + 1), index, start, end,
                _occurrence(text, quote, start), material[-1], quote))
    if len(rows) > MAX_CANDIDATES:
        raise ValueError('Catalog count bound exceeded; no pruning permitted.')
    material = {'version':VERSION, 'content_snapshot_sha256':snapshot,
        'candidates':[vars(row) for row in rows], 'coverage_gaps':gaps}
    if len(json.dumps(material, ensure_ascii=False).encode()) > MAX_CATALOG_BYTES:
        raise ValueError('Catalog serialized byte bound exceeded; no pruning permitted.')
    return Catalog(VERSION, tuple(contents), snapshot, tuple(rows), tuple(gaps), digest(material))


def prompt_payload(catalog):
    # Record narrative is retained in full, with no metadata added to candidate content.
    return {'catalog_version':catalog.version, 'catalog_sha256':catalog.catalog_sha256,
        'selected_records':[{'record_index':i,'content':t} for i,t in enumerate(catalog.contents,1)],
        'quote_candidates':[{'candidate_id':c.candidate_id,'record_index':c.record_index,
            'quote':c.quote} for c in catalog.candidates],
        'coverage_gaps':[list(x) for x in catalog.coverage_gaps]}


def selection_schema():
    from app.schemas.target_identity import IdentityCandidateSelectionDraft
    return IdentityCandidateSelectionDraft


def hydrate(selection, catalog, current_contents):
    """Return old strict draft plus binding receipt; caller MUST run original validator.

    No graph/quote pruning or cue deduplication here. Failed input produces no partial output.
    Empty context is a no-API skip decision for the caller, never a successful model analysis.
    """
    from app.schemas.target_identity import IdentityEvidenceDraft
    if not catalog.contents: raise ValueError('Empty context: skip without API.')
    rebuilt = build_catalog(current_contents)
    if rebuilt != catalog: raise ValueError('Stale/tampered catalog or current selected content.')
    parsed = selection_schema().model_validate(selection)
    candidates = {c.candidate_id:c for c in catalog.candidates}
    ids = [q.quote_id for q in parsed.quotes]; chosen = [q.candidate_id for q in parsed.quotes]
    if len(ids) != len(set(ids)) or len(chosen) != len(set(chosen)):
        raise ValueError('Duplicate quote ID/span selection.')
    hydrated = []; bindings = []
    for quote in parsed.quotes:
        if quote.candidate_id not in candidates: raise ValueError('Unknown candidate ID.')
        c = candidates[quote.candidate_id]; text = current_contents[c.record_index - 1]
        if text[c.char_start:c.char_end] != c.quote: raise ValueError('Source span changed.')
        hydrated.append({'quote_id':quote.quote_id,'record_index':c.record_index,'quote':c.quote,'occurrence':c.occurrence})
        bindings.append({'quote_id':quote.quote_id,**vars(c)})
    material = parsed.model_dump(mode='json');material['quotes'] = hydrated
    draft = IdentityEvidenceDraft.model_validate(material)
    receipt = {'version':'identity-candidate-selection-receipt-v1',
        'catalog_sha256':catalog.catalog_sha256,'content_snapshot_sha256':catalog.content_snapshot_sha256,
        'selection_sha256':digest(selection),'bindings':bindings}
    from app.schemas.target_identity import QuoteCandidateSelectionReceipt
    return draft, QuoteCandidateSelectionReceipt.model_validate(receipt).model_dump(mode='json')
