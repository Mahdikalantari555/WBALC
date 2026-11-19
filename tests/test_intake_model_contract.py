"""User workflow regressions: schema changes and older checkpoints."""


def test_added_class_does_not_rename_or_widen_old_predictions(client, project, labeled):
    root = f'/projects/{project["id"]}'
    trained = client.post(f'{root}/train', json={})
    assert trained.status_code == 201, trained.text
    expanded = client.post(f'{root}/classes', json={'name': ' شهری '})
    assert expanded.status_code == 200
    assert expanded.json()['classes'] == [*project['classes'], 'شهری']
    assert client.post(f'{root}/classes', json={'name': ' Water '}).status_code == 422
    assert client.put(root, json={'classes': ['land', 'urban']}).status_code == 409
    response = client.post(f'{root}/query', json={'strategy': 'uncertainty', 'exclude_labeled': False, 'batch_size': 4})
    assert response.status_code == 200, response.text
    payload = response.json()
    assert len(payload['samples']) == 4
    assert all(sample['prediction'] in project['classes'] for sample in payload['samples'])
    batch = client.get(f'{root}/queries/{payload["batch_id"]}').json()
    assert batch['parameters']['prediction_classes'] == project['classes']


def test_reordered_bands_reject_model_scores_but_allow_unscored_sampling(client, project, labeled, geotiff_bytes):
    root = f'/projects/{project["id"]}'
    assert client.post(f'{root}/train', json={}).status_code == 201
    changed = client.post(f'{root}/upload', files={'file': ('reordered.tif', geotiff_bytes, 'image/tiff')},
                          data={'band_names': 'red,green,blue,nir', 'sensor': 'sentinel-2'}).json()
    payload = {'dataset_id': changed['id'], 'batch_size': 3}
    assert client.post(f'{root}/query', json={**payload, 'strategy': 'uncertainty'}).status_code == 409
    cold = client.post(f'{root}/query', json={**payload, 'strategy': 'diversity'}).json()
    assert len(cold['samples']) == 3 and cold['training_run_id'] is None
    assert all(sample['prediction'] is None and sample['uncertainty'] is None for sample in cold['samples'])
