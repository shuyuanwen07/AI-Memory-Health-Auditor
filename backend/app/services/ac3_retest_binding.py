"""Read-only database binding for the paired AC3 retest format.

This does not stage or execute audits. Transaction locks and live dispatch
checks must be implemented separately before any use in formal experiments.
"""
from sqlalchemy import select
from app.models import ConversationModel, MemoryModel, MemoryRelationshipModel, MessageModel
from scripts.ac3_retest_reference_stage import compile_reference_stage


def verify_database_binding(db, frozen, source_raw, plan_raw, reviews, components, history_conversations):
    if db.new or db.dirty or db.deleted:
        raise ValueError('Use a clean read-only session')
    stage = compile_reference_stage(frozen, source_raw, plan_raw, reviews, components)
    histories = stage['histories']
    ids = [h['history_id'] for h in histories]
    if not isinstance(history_conversations, dict) or set(history_conversations) != set(ids):
        raise ValueError('Every reviewed history needs a conversation mapping')
    mapped = list(history_conversations.values())
    if any(not isinstance(x, str) or not x.strip() for x in mapped) or len(set(mapped)) != len(mapped):
        raise ValueError('Conversation mappings must be distinct and nonempty')
    with db.no_autoflush:
        for history in histories:
            cid=history_conversations[history['history_id']]
            conversation=db.get(ConversationModel,cid,populate_existing=True)
            if conversation is None or not conversation.authorised or conversation.source_origin != 'synthetic':
                raise ValueError('Expected an authorized synthetic conversation')
            messages=list(db.scalars(select(MessageModel).where(MessageModel.conversation_id==cid)
                         .order_by(MessageModel.sequence).execution_options(populate_existing=True)))
            expected=history['source_messages']
            if len(messages)!=len(expected): raise ValueError('Source message count differs')
            for index,(actual,item) in enumerate(zip(messages,expected)):
                if (actual.sequence!=index or item['order']!=index+1 or actual.source_message_id!=item['message_id']
                        or actual.role!=item['role'] or actual.content!=item['text']):
                    raise ValueError('Saved source message differs from the reviewed source')
            memories=list(db.scalars(select(MemoryModel).where(MemoryModel.conversation_id==cid)
                          .execution_options(populate_existing=True)))
            expected_facts=history['reviewed_facts']
            expected_by_id={fact['memory_id']:fact for fact in expected_facts}
            if len(memories)!=len(expected_by_id) or {m.id for m in memories}!=set(expected_by_id):
                raise ValueError('Saved memory identities differ from reviewed facts')
            for memory in memories:
                fact=expected_by_id[memory.id]
                if (memory.status!='confirmed' or memory.canonical_value!=fact['canonical_value']
                        or memory.source_message_ids != [fact['source_message_id']]):
                    raise ValueError('Saved memory differs from reviewed fact')
            actual_rel=list(db.scalars(select(MemoryRelationshipModel)
                .where(MemoryRelationshipModel.memory_id.in_(list(expected_by_id)))
                .execution_options(populate_existing=True)))
            def relationship_key(row):
                return (row['memory_id'],row['target_memory_id'],row['relationship_type'],tuple(row['evidence_message_ids']))
            actual_keys=[relationship_key({'memory_id':r.memory_id,'target_memory_id':r.target_memory_id,
                'relationship_type':r.relationship_type,'evidence_message_ids':r.evidence_message_ids}) for r in actual_rel]
            expected_keys=[relationship_key(r) for r in history['reviewed_relationships']]
            if sorted(actual_keys)!=sorted(expected_keys):
                raise ValueError('Saved relationships differ from reviewed relationships')
    return {'format':'ac3-paired-database-binding-check-v1','history_count':len(histories),
            'question_count':len(stage['questions']),'database_written':False,'model_called':False,
            'execution_supported':False,'limitation':'Read-only comparison; no concurrent locks, staging or dispatch.'}
