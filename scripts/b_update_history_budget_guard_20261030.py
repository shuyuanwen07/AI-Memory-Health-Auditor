"""Isolated output guard for a candidate UPDATE-history retrieval.

Not integrated in the product. This is a conservative post-selection check;
missing pairs remain evidence gaps, not a promise of an answerable question.
"""
from app.schemas import RelationshipType

def guard_selected_updates(selected, relations, requested_pairs):
    """Exclude a selected predecessor when its known current endpoint is absent.

    The caller supplies only pairs identified for the explicit history question.
    Preserve selected order. Never add or infer an item, exceed the budget, or
    suppress independent selection of current endpoints.
    """
    valid={(r.memory_id,r.target_memory_id) for r in relations if r.relationship_type==RelationshipType.UPDATE.value}
    pairs=set(requested_pairs)
    if not pairs <= valid:
        raise ValueError('Requested history pair must be a known UPDATE relationship')
    ids={item['record'].id for item in selected}
    unsafe=set()
    while True:
        available=ids-unsafe
        new={prior for current,prior in pairs if prior in available and current not in available}
        if not new:
            break
        unsafe.update(new)
    available=ids-unsafe
    missing=[(current,prior) for current,prior in pairs if not ({current,prior}<=available)]
    retained=[item for item in selected if item['record'].id not in unsafe]
    return retained, {'incomplete_update_history': bool(missing), 'missing_pairs':sorted(missing),
                      'excluded_orphan_prior_ids':sorted(unsafe & ids)}
