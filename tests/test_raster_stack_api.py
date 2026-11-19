import io
import json

import numpy as np
import rasterio
from rasterio.transform import from_origin


def band(value, x=500000, count=1, *, width=64, height=64, resolution=10, scale=1.0, offset=0.0,
         nodata=0, data=None, mask_corner=True):
    stream = io.BytesIO()
    with rasterio.open(stream, 'w', driver='GTiff', width=width, height=height, count=count,
                       dtype='uint16', crs='EPSG:32631', transform=from_origin(x, 4650000, resolution, resolution), nodata=nodata) as dest:
        if data is None:
            values = np.full((count, height, width), value, dtype='uint16')
        else:
            values = np.asarray(data, dtype='uint16').reshape(count, height, width).copy()
        if mask_corner and nodata == 0:
            values[:, 0, 0] = 0
        dest.write(values)
        dest.scales = (scale,) * count
        dest.offsets = (offset,) * count
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


def test_stack_resamples_native_sentinel2_resolutions_to_finest_grid(client, project):
    root = f'/projects/{project["id"]}'
    gradient = np.tile(np.arange(32, dtype='uint16') + 100, (32, 1))
    categorical = np.tile(np.where(np.arange(32) % 2, 20, 10).astype('uint16'), (32, 1))
    result = client.post(
        f'{root}/raster-stack',
        data={'sensor': 'Sentinel-2', 'band_names': '["blue", "swir16", "scl"]', 'resampling': 'bilinear'},
        files=[
            ('files', ('blue.tif', band(10))),
            ('files', ('swir16.tif', band(0, width=32, height=32, resolution=20, scale=0.01, data=gradient))),
            ('files', ('scl.tif', band(0, width=32, height=32, resolution=20, nodata=None, data=categorical, mask_corner=False))),
        ],
    )
    assert result.status_code == 201, result.text
    dataset = result.json()
    raw = client.get(f'{root}/dataset/{dataset["id"]}/file')
    with rasterio.open(io.BytesIO(raw.content)) as src:
        assert (src.width, src.height, src.count) == (64, 64, 3)
        assert src.transform == from_origin(500000, 4650000, 10, 10)
        assert src.descriptions == ('blue', 'swir16', 'scl')
        assert 1.05 <= src.read(2)[20, 20] <= 1.2  # source scale 0.01 was applied
        assert set(np.unique(src.read(3))).issubset({10.0, 20.0})  # SCL uses nearest, not bilinear
        assert src.tags(2)['WBALC_RESAMPLED'] == 'true'
        assert src.tags(2)['WBALC_RESAMPLING'] == 'bilinear'
        assert src.tags(3)['WBALC_RESAMPLING'] == 'nearest'


def test_scl_description_variants_always_use_nearest_resampling():
    from rasterio.enums import Resampling

    from app.api.raster_stack import _resampling_for

    for name in ("SCL_20m", "scl60m", "scene_classification_layer"):
        assert _resampling_for(name, "bilinear") == Resampling.nearest


def test_stack_crops_pixel_aligned_shifted_bands_to_their_common_overlap(client, project):
    root = f'/projects/{project["id"]}'
    result = client.post(
        f'{root}/raster-stack',
        data={'sensor': 'Sentinel-1', 'band_names': '["vv", "vh"]'},
        files=[
            ('files', ('vv.tif', band(10))),
            ('files', ('vh.tif', band(40, x=500010))),
        ],
    )
    assert result.status_code == 201, result.text
    dataset = result.json()
    raw = client.get(f'{root}/dataset/{dataset["id"]}/file')
    with rasterio.open(io.BytesIO(raw.content)) as src:
        assert (src.width, src.height) == (63, 64)
        assert src.transform == from_origin(500010, 4650000, 10, 10)
        assert list(src.read()[:, 1, 1]) == [10, 40]
        # The output only represents the common footprint; native sources stay untouched.


def test_stack_crops_nested_resolution_inputs_to_their_common_overlap(client, project):
    root = f'/projects/{project["id"]}'
    result = client.post(
        f'{root}/raster-stack',
        data={'sensor': 'Sentinel-2', 'band_names': '["blue", "swir16"]'},
        files=[
            ('files', ('blue.tif', band(10))),
            ('files', ('swir16.tif', band(20, x=500020, width=32, height=32, resolution=20))),
        ],
    )
    assert result.status_code == 201, result.text
    raw = client.get(f'{root}/dataset/{result.json()["id"]}/file')
    with rasterio.open(io.BytesIO(raw.content)) as src:
        assert (src.width, src.height) == (62, 64)
        assert src.transform == from_origin(500020, 4650000, 10, 10)
        assert src.tags(2)['WBALC_RESAMPLED'] == 'true'
        assert src.tags(2)['WBALC_RESAMPLING'] == 'bilinear'


def test_stack_rejects_duplicate_half_pixel_nonoverlap_multiband_and_merged_inputs(client, project):
    root = f'/projects/{project["id"]}'
    cases = [
        (['vv','VV'], [('vv.tif', band(10)), ('vh.tif', band(40))], 'unique'),
        (['vv','vh'], [('vv.tif', band(10)), ('vh.tif', band(40, x=500005))], 'fractional source pixel'),
        (['vv','vh'], [('vv.tif', band(10)), ('vh.tif', band(40, x=501000))], 'do not overlap'),
        (['vv','vh'], [('vv.tif', band(10)), ('vh.tif', band(40, count=2))], 'one band'),
        (['vv','vh'], [('vv.tif', band(10)), ('merged.tif', band(40))], 'Merged/multiband'),
    ]
    for names, uploads, message in cases:
        result = client.post(f'{root}/raster-stack', data={'sensor': 'Sentinel-1', 'band_names': json.dumps(names)},
                             files=[('files', (filename, content)) for filename, content in uploads])
        assert result.status_code == 422 and message in result.text, result.text
    assert client.get(f'{root}/dataset').json() == []


def test_stack_rejects_coarse_grid_half_pixel_origin(client, project):
    root = f'/projects/{project["id"]}'
    result = client.post(
        f'{root}/raster-stack',
        data={'sensor': 'Sentinel-2', 'band_names': '["blue", "swir16"]'},
        files=[
            ('files', ('blue.tif', band(10))),
            ('files', ('swir16.tif', band(20, x=500010, width=32, height=32, resolution=20))),
        ],
    )
    assert result.status_code == 422
    assert 'fractional source pixel' in result.text
    assert client.get(f'{root}/dataset').json() == []


def test_stack_preserves_dated_scene_metadata_and_accepts_s2_orbit_fields(client, project):
    root = f'/projects/{project["id"]}'
    raw_metadata = {'datetime': '2025-03-13', 'properties': {'datetime': '2025-03-13T07:36:19.024000Z', 'sat:relative_orbit': 92}}
    result = client.post(
        f'{root}/raster-stack',
        data={
            'sensor': 'Sentinel-2', 'band_names': '["blue", "swir16"]', 'kind': 'scene',
            'acquisition_datetime': '2025-03-13T07:36:19.024000Z', 'platform': 'Sentinel-2B',
            'product_type': 'S2MSI2A', 'product_level': 'L2A', 'processing_baseline': '05.11',
            'orbit_direction': 'descending', 'relative_orbit': '92',
            'acquisition_metadata': json.dumps(raw_metadata),
            'product_metadata': json.dumps({'PRODUCT_ID': 'S2B_MSIL2A_20250313'}),
        },
        files=[
            ('files', ('blue.tif', band(10))),
            ('files', ('swir16.tif', band(20, width=32, height=32, resolution=20))),
        ],
    )
    assert result.status_code == 201, result.text
    scene = client.get(f'{root}/scenes').json()[0]
    assert scene['acquisition_datetime'] == '2025-03-13T07:36:19.024000Z'
    assert scene['band_names'] == ['blue', 'swir16'] and scene['platform'] == 'Sentinel-2B'
    assert scene['product_level'] == 'L2A' and scene['product_type'] == 'S2MSI2A'
    assert scene['orbit_direction'] == 'descending' and scene['relative_orbit'] == 92
    assert scene['product_metadata']['PRODUCT_ID'] == 'S2B_MSIL2A_20250313'
    alignment = scene['acquisition_metadata']['wbalc_stack']
    assert alignment['resampling_performed'] is True
    assert alignment['target_grid']['resolution'] == [10.0, 10.0]
    assert alignment['bands'][1]['source_resolution'] == [20.0, 20.0]

    file = client.get(f'{root}/scenes/{scene["id"]}/file', headers={'Range': 'bytes=0-15'})
    assert file.status_code == 206 and len(file.content) == 16
    other = client.post('/projects', json={'name':'No access'}).json()['id']
    assert client.get(f'/projects/{other}/scenes/{scene["id"]}/file').status_code == 404
