# Raster intake and workflow audit

## Findings and checks

| User scenario | Fault or risk found | Correction / evidence |
| --- | --- | --- |
| Set up a binary project; later need wetland, forest, snow or a Persian class | Fixed three-class default or an opaque comma-separated class field | Editable `water`, `non_water` rows and add/remove at creation. Browser exercised six classes including an append to the existing project. Invalid/duplicate names rejected in API tests. |
| Append a class after fitting | Query decoded class IDs against the mutable project list | Query uses the recorded run classes and exports their order in the batch parameters. API regression checks old predictions; classes with retained labels cannot be removed by project update. |
| Switch from a known raster to a same-count, differently ordered one | Query treated band count as schema identity | Model-scored queries refuse incompatible or unverified inputs. Model-free sampling can continue without fabricated scores; both branches tested. |
| Upload a multispectral TIFF with no band descriptions | No per-band confirmation | Browser reads header only and requires numbered names before upload. Browser exercised a four-band raster. |
| Import a dated optical/radar tree with one broken stack | One-file workflow and no recovery per acquisition | Browser imported two separate dates, recorded a Sentinel-1 UTC acquisition, rejected a third with a shifted transform, then retried only the failed date without duplication. API tests check order, pixel identity, NoData, duplicates and non-single-band validation. |
| Inspect bands rapidly; leave/reopen map | Inferred RGB by position, offered NDVI on radar, and a queued resize callback could hit a disposed map | Declared RGB/NIR identity, supported presets only, stale image guards, map remount per dataset and disconnected resize observer. Browser verified a rendered preview, selection of an imported radar scene, and recipe persistence/removal after reload. |
| Open import review on 390px Persian mobile | Risk of clipping in modal and long paths | Native modal focus + internal scroll and responsive layout using logical sizing. Chromium verified no horizontal overflow. |

Impeccable **Audit**, **Harden**, and **Adapt** playbooks were used as review guides. Local images are under `.screenshots/`, which is ignored. Verification used Chromium and synthetic GeoTIFFs, not a physical field device or production survey imagery.

## Provisional folder contract

```text
survey/
  2025-10-01/
    blue.tif
    green.tif
    red.tif
    nir.tif
    metadata.json
  2025-10-09/
    vv.tif
    vh.tif
    metadata.json
```

- Dates accept `YYYY-MM-DD`, `YYYY_MM_DD` or `YYYYMMDD`; files group by the nearest valid dated directory. TIFF extensions are case-insensitive. Common Sentinel-2 `B02`/`B03`/`B04`/`B08` filename tokens are recognized as well.
- Small JSON sidecars may put `datetime`, `acquisition_datetime`, `acquisition_date` or `date` and `platform` at the top level or in STAC-style `properties`. Date-only values yield midnight UTC. Conflicting dates/metadata are held back. The full acquisition time is stored when the import destination is **Dated scene**. Training rasters are a separate input type and use the date in the generated name, not a scene record.
- This is not an official SAFE/XML/JP2 importer. Precise parsing of the user's actual tree remains open until a representative sample is available.
- A single stack is submitted at a time, up to 32 single-band files and the server's configured per-request/raster size limits. No implicit reprojection, resolution harmonization, or application of scale/offset. Mixed native resolutions need upstream alignment. Retry is scoped to the current review session; re-opening a folder later is a new import.
- Derived map recipes are browser-local per raster. They preview `(A−B)/(A+B)`; a zero denominator or invalid input is transparent. They are neither model inputs nor exported scientific index products yet.

## Inspect and compare dates

On the map, click an image to read the native zero-based column/row and raw band values. Georeferenced views also report WGS84 longitude and latitude. A derived preview reports its operands and index value. NoData values and internal TIFF masks are marked as missing, not zero.

Select a dated scene, then use **Compare with another date** to select an acquisition on the same native grid. The divider keeps both sides at the same zoom and center. This is a visual swipe, not a change raster: each normal band preview uses its own contrast stretch. Use the pixel probe for numeric comparison.

In **Active Learning**, **Undo last label** withdraws the current review view's latest submission. It restores the prior retained version if there is one, or reopens the associated suggestion. The withdrawn version and timestamp remain in label history and the research-path JSON. Existing trained models remain historical snapshots; retrain to use the updated labels.
