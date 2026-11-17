"""Focused research-note storage tests. No model or provider imports required."""
import pytest
from fastapi import HTTPException
from backend import course_store, research_store as store


def paper(n=0):
    return dict(provider='arxiv',external_id=f'2601.1234{n}',title=f'Synthetic Note Paper {n}',
                authors=['Synthetic Author'],abstract='Synthetic abstract for note tests.',year=2026,
                source_url=f'https://arxiv.org/abs/2601.1234{n}',doi=None,citation_count=0,
                published_at='2026-01-01T00:00:00Z',updated_at='2026-02-01T00:00:00Z')


@pytest.fixture
def research_db(tmp_path,monkeypatch):
    monkeypatch.setattr(course_store,'DATABASE_PATH',tmp_path/'private-notes.sqlite3')
    course_store.initialize_database();store.initialize()
    return store.create_topic('Private notes topic','alice')


def save_two_papers(topic):
    papers=[paper(0),paper(1)]
    store.record_search(topic['id'],'alice','notes',papers)
    return [store.save_paper(topic['id'],'alice','arxiv',item['external_id']) for item in papers]


def test_topic_list_exposes_saved_note_and_updated_time(research_db):
    first,second=save_two_papers(research_db)
    store.save_note(first['id'],'alice',text='Previously saved private note')
    listed={item['id']:item for item in store.list_papers(research_db['id'],'alice')}
    assert listed[first['id']]['note_text']=='Previously saved private note'
    assert listed[first['id']]['note_updated_at']
    assert listed[second['id']]['note_text']==''
    assert listed[second['id']]['note_updated_at'] is None
    detail=store.get_paper(first['id'],'alice')
    assert detail['note_text']=='Previously saved private note'
    assert detail['note_updated_at']


def test_notes_remain_associated_with_their_original_paper(research_db):
    first,second=save_two_papers(research_db)
    store.save_note(first['id'],'alice',text='Alpha notes')
    store.save_note(second['id'],'alice',text='Beta notes')
    store.save_note(first['id'],'alice',text='Alpha notes revised')
    assert store.get_paper(first['id'],'alice')['note_text']=='Alpha notes revised'
    assert store.get_paper(second['id'],'alice')['note_text']=='Beta notes'
    listed={item['id']:item['note_text'] for item in store.list_papers(research_db['id'],'alice')}
    assert listed=={first['id']:'Alpha notes revised',second['id']:'Beta notes'}


def test_saved_note_survives_a_fresh_read(research_db):
    first,_=save_two_papers(research_db)
    store.save_note(first['id'],'alice',text='Persistent note')
    assert store.get_paper(first['id'],'alice')['note_text']=='Persistent note'
    listed={item['id']:item for item in store.list_papers(research_db['id'],'alice')}
    assert listed[first['id']]['note_text']=='Persistent note'


def test_another_student_cannot_read_or_change_notes(research_db):
    first,_=save_two_papers(research_db)
    store.save_note(first['id'],'alice',text='Alice only')
    for operation in (lambda:store.get_paper(first['id'],'bob'),
                      lambda:store.list_papers(research_db['id'],'bob'),
                      lambda:store.save_note(first['id'],'bob',text='Overwrite')):
        with pytest.raises(HTTPException) as error:operation()
        assert error.value.status_code==404
    assert store.get_paper(first['id'],'alice')['note_text']=='Alice only'
