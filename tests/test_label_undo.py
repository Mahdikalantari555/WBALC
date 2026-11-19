"""Withdrawal preserves provenance but removes a version from current labels."""


def test_undo_restores_previous_or_reopens_query_without_erasing_versions(client, project, dataset):
    root = f'/projects/{project["id"]}'
    batch = client.post(f'{root}/query', json={'strategy': 'random', 'batch_size': 1}).json()
    item = client.get(f'{root}/queries/{batch["batch_id"]}').json()['items'][0]
    payload = {'dataset_id': dataset['id'], 'query_item_id': item['id'], 'query_batch_id': batch['batch_id'],
               'coordinate_space': 'pixel', 'geometry': {'type': 'Point', 'coordinates': [item['coords']['center_x'], item['coords']['center_y']]}}

    def submit(name):
        res = client.post(f'{root}/labels', json={**payload, 'class_name': name})
        assert res.status_code == 201, res.text
        return res.json()

    first, second = [submit(name) for name in project['classes'][:2]]
    def undo(label):
        return client.post(f'{root}/labels/{label["id"]}/undo')

    assert undo(first).status_code == 409
    assert undo(second).json()['restored_query_class'] == first['class_name']
    assert client.get(f'{root}/labels').json()[0]['id'] == first['id']
    assert undo(second).status_code == 409
    assert undo(first).json()['restored_class'] is None
    assert client.get(f'{root}/labels').json() == []
    history = client.get(f'{root}/history').json()
    assert [row['id'] for row in history] == [first['id'], second['id']]
    assert all(row['undone_at'] for row in history)
    detail = client.get(f'{root}/queries/{batch["batch_id"]}').json()
    assert detail['items'][0]['status'] == 'pending' and detail['samples_added'] == 0
    third = submit(first['class_name'])
    assert third['version'] == 3
    assert client.get(f'{root}/queries/{batch["batch_id"]}').json()['samples_added'] == 1
    exported = client.get(f'{root}/research-path').json()
    assert exported['sampling_rounds'][0]['samples_added'] == 1
    assert exported['label_versions'][0]['undone_at']
    other = client.post('/projects', json={'name': 'Other'}).json()['id']
    assert client.post(f'/projects/{other}/labels/{third["id"]}/undo').status_code == 404
