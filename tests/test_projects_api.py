"""project-management spec scenarios."""

from __future__ import annotations


class TestProjects:
    def test_create(self, client):
        resp = client.post(
            "/projects",
            json={"name": "Coastal", "classes": ["water", "land"], "description": "d", "status": "active"},
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["id"] > 0
        assert body["name"] == "Coastal"
        assert body["classes"] == ["water", "land"]
        assert body["description"] == "d"
        assert body["status"] == "active"
        assert "created_at" in body

    def test_create_invalid(self, client):
        assert client.post("/projects", json={"name": "", "classes": ["a", "b"]}).status_code == 422
        assert client.post("/projects", json={"name": "x", "classes": ["a"]}).status_code == 422
        assert client.post("/projects", json={"name": "x", "classes": ["a", "a"]}).status_code == 422

    def test_list(self, client, project):
        client.post("/projects", json={"name": "Second", "classes": ["a", "b"]})
        resp = client.get("/projects")
        assert resp.status_code == 200
        assert len(resp.json()) == 2

    def test_get_existing(self, client, project):
        resp = client.get(f"/projects/{project['id']}")
        assert resp.status_code == 200
        assert resp.json()["name"] == "Demo"

    def test_get_missing_404(self, client):
        assert client.get("/projects/9999").status_code == 404

    def test_update(self, client, project):
        resp = client.put(
            f"/projects/{project['id']}",
            json={"name": "Renamed", "classes": ["water", "vegetation", "urban"], "status": "paused"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["name"] == "Renamed"
        assert body["classes"] == ["water", "vegetation", "urban"]
        assert body["status"] == "paused"
        assert body["description"] == "test"  # untouched

    def test_update_missing_404(self, client):
        assert client.put("/projects/9999", json={"name": "x"}).status_code == 404

    def test_delete(self, client, project):
        assert client.delete(f"/projects/{project['id']}").status_code == 204
        assert client.get(f"/projects/{project['id']}").status_code == 404
