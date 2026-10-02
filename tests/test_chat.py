from types import SimpleNamespace

import pytest
from google.genai import errors as genai_errors

import main


class FakeModels:
    def __init__(self, fail_with=None):
        self.calls = []
        self.fail_with = fail_with

    def generate_content(self, model, contents, config):
        self.calls.append({'model': model, 'contents': contents, 'max': config.max_output_tokens})
        if self.fail_with:
            raise self.fail_with
        return SimpleNamespace(text='Chicken Breast leads your revenue.')


@pytest.fixture
def chat(monkeypatch):
    fake = FakeModels()
    monkeypatch.setattr(main, 'gemini_client', SimpleNamespace(models=fake))
    main.app.config['TESTING'] = True
    with main.app.test_client() as c:
        c.post('/login', data={'username': 'demo', 'password': 'demo'})
        c.post('/load-demo-data', data={'demo_type': 'supermarket_data', 'date_filter': 'all'})
        yield c, fake


def ask(client, q='Top products?'):
    return client.post('/dashboard/chat/ask', json={'question': q}).get_json()


def test_uses_a_current_configurable_model_and_sends_the_data(chat):
    client, fake = chat
    assert ask(client)['answer'] == 'Chicken Breast leads your revenue.'
    call = fake.calls[0]
    assert call['model'] == main.GEMINI_MODEL != 'gemini-1.5-flash'
    assert 'Top products?' in call['contents'] and 'Chicken Breast' in call['contents']
    assert call['max'] == 1000


def test_questions_are_capped_per_session(chat, monkeypatch):
    client, fake = chat
    monkeypatch.setattr(main, 'CHAT_QUESTIONS_PER_SESSION', 2)
    ask(client), ask(client)
    third = ask(client)['answer']
    assert 'allows 2 AI questions per visit' in third
    assert len(fake.calls) == 2  # the capped question never reaches Google


def test_used_up_free_quota_gets_a_friendly_answer(chat):
    client, fake = chat
    fake.fail_with = genai_errors.ClientError(429, {'error': {'code': 429, 'message': 'quota', 'status': 'RESOURCE_EXHAUSTED'}})
    assert 'free AI quota is used up' in ask(client)['answer']


def test_chat_page_tells_people_where_their_data_goes(chat):
    client, _ = chat
    page = client.get('/dashboard/chat').get_data(as_text=True)
    assert 'sent to Google' in page
