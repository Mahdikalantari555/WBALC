import io
import json

import numpy as np
import rasterio
from rasterio.transform import from_origin


def band(value, x=500000, count=1):
    stream = io.BytesIO()
    with rasterio.open(stream, 'w', driver='GTiff', width=64, height=64, count=count,
                       dtype='uint16', crs='EPSG:32631', transform=from_origin(x, 4650000, 10, 10), nodata=0) as dest:
        data = np.full((count, 64, 64), value, dtype='uint16')
        data[:, 0, 0] = 0
        dest.write(data)
    return stream.getvalue()


def test_stack_preserves_names_pixels_and_mask(client, project):
    root = f'/projects/{project["id"]}'
    result = client.post(f'{root}/raster-stack', data={'sensor': 'Sentinel-1', 'band_names': '["vh", "vv"]'},
                         files=[('files', ('vh.tif', band(10))), ('files', ('vv.tif', band(40)))])
    assert result.status_code == 201, result.text
    dataset = result.json()
    assert dataset['band_schema']['band_names'] == ['vh', 'vv']
    raw = client.get(f'{root}/dataset/{dataset["id"]}/file')
    with rasterio.open(io.BytesIO(raw.content)) as src:
        assert src.descriptions == ('vh', 'vv')
        assert list(src.read()[:, 1, 1]) == [10, 40]
        assert src.read(masked=True).mask[:, 0, 0].all()


def test_stack_rejects_ambiguity_and_grid_mismatch_without_writes(client, project):
    root = f'/projects/{project["id"]}'
    for names, second, message in [(['vv','VV'], band(40), 'unique'), (['vv','vh'], band(40, x=500010), 'identical'),
                                   (['vv','vh'], band(40, count=2), 'one band')]:
        result = client.post(f'{root}/raster-stack', data={'sensor': 'Sentinel-1', 'band_names': json.dumps(names)},
                             files=[('files', ('vv.tif', band(10))), ('files', ('vh.tif', second))])
        assert result.status_code == 422 and message in result.text, result.text
    assert client.get(f'{root}/dataset').json() == []


def test_stack_preserves_dated_scene_metadata(client, project):
    root = f'/projects/{project["id"]}'
    result = client.post(f'{root}/raster-stack', data={'sensor':'Sentinel-1', 'band_names':'["vv","vh"]', 'kind':'scene',
                         'acquisition_datetime':'2025-12-31T21:14:00Z', 'platform':'Sentinel-1A'},
                         files=[('files', ('vv.tif', band(40))), ('files', ('vh.tif', band(10)))])
    assert result.status_code == 201, result.text
    scene = client.get(f'{root}/scenes').json()[0]
    assert scene['acquisition_datetime'] == '2025-12-31T21:14:00Z'
    assert scene['band_names'] == ['vv', 'vh'] and scene['platform'] == 'Sentinel-1A'

    file = client.get(f'{root}/scenes/{scene["id"]}/file', headers={'Range': 'bytes=0-15'})
    assert file.status_code == 206 and len(file.content) == 16
    other = client.post('/projects', json={'name':'No access'}).json()['id']
    assert client.get(f'/projects/{other}/scenes/{scene["id"]}/file').status_code == 404
