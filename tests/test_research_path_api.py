"""Research exports are project-scoped, complete, and spreadsheet-safe."""
import csv
import io
import sqlite3


def test_empty_project_exports_and_invalid_id(client, project):
    path = f"/projects/{project['id']}/research-path"
    response = client.get(path)
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json()["sampling_rounds"] == []
    assert response.json()["training_runs"] == []
    assert list(csv.DictReader(io.StringIO(client.get(path, params={"format": "csv"}).text))) == []
    assert client.get(path, params={"format": "tsv"}).status_code == 422
    assert client.get("/projects/999999/research-path").status_code == 404


def test_all_history_including_empty_rounds_and_only_own_project(client, project, settings):
    other = client.post("/projects", json={"name": "Other"}).json()
    # More than the maximum history page size, without running the sampler 201 times.
    with sqlite3.connect(settings.storage_dir.parent / "test.db") as db:
        db.executemany("""
            INSERT INTO query_batches (project_id, strategy, strategy_version,
              batch_size_requested, batch_size_returned, parameters, notes, created_at)
            VALUES (?, 'random', 'v1', 10, 0, '{}', '[]', CURRENT_TIMESTAMP)
            """, [(project["id"],)] * 201 + [(other["id"],)])
    prefix = f"/projects/{project['id']}"
    assert len(client.get(f"{prefix}/queries?limit=200").json()) == 200
    rounds = client.get(f"{prefix}/research-path").json()["sampling_rounds"]
    assert len(rounds) == 201
    assert {entry["project_id"] for entry in rounds} == {project["id"]}
    assert [entry["id"] for entry in rounds] == sorted(entry["id"] for entry in rounds)
    rows = list(csv.DictReader(io.StringIO(client.get(f"{prefix}/research-path?format=csv").text)))
    assert len(rows) == 201
    assert all(row["record_type"] == "empty_batch" and row["batch_samples_added"] == "0" for row in rows)


def test_sample_ledger_escapes_formula_prefix_but_preserves_numbers():
    from app.api.research_path import csv_cell

    assert csv_cell("  =1+1") == "'  =1+1"
    assert csv_cell("\ttext") == "'\ttext"
    assert csv_cell(-12) == -12
    assert csv_cell({"center": [-12, 5], "crs": "EPSG:4326"}) == '{"center":[-12,5],"crs":"EPSG:4326"}'
