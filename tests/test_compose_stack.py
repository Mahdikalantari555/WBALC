"""Guards for the container stack and the launcher scripts.

Docker is not reachable from every environment this repo is exercised in (CI
sandboxes, locked-down laptops), so `docker compose config` cannot be the only
check. These tests validate what can be validated without a daemon:

- the compose file parses and its services/dependencies/profiles are coherent,
- every `depends_on` target exists (a typo here means a UI that starts before
  the engine and shows an error page on first load),
- each service that needs one declares a healthcheck, and every UI waits for the
  engine to be *healthy* rather than merely started,
- referenced Dockerfiles exist,
- the launcher scripts are syntactically valid and fail loudly, with actionable
  text, when Docker is absent.

What is NOT covered: actually building or running the images. That needs a
daemon and is recorded as unverified in the PR rather than implied by green tests.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml", reason="pyyaml is needed to validate the compose file")

ROOT = Path(__file__).resolve().parent.parent
COMPOSE = ROOT / "docker-compose.yml"


@pytest.fixture(scope="module")
def compose() -> dict:
    assert COMPOSE.is_file(), "docker-compose.yml is missing"
    return yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def compose_text() -> str:
    return COMPOSE.read_text(encoding="utf-8")


# ------------------------------------------------------------------ structure
def test_the_expected_services_exist(compose):
    services = compose["services"]
    assert set(services) == {"api", "frontend", "db"}
    assert services["frontend"]["build"]["context"] == "./frontend"


def test_every_dependency_target_exists(compose):
    for name, service in compose["services"].items():
        for dependency in service.get("depends_on") or {}:
            assert dependency in compose["services"], f"{name} depends on missing {dependency}"


def test_uis_wait_for_a_healthy_engine(compose):
    """`service_started` would let the UI boot before /health answers."""
    depends = compose["services"]["frontend"]["depends_on"]
    assert depends["api"]["condition"] == "service_healthy"


def test_dockerfiles_referenced_by_the_build_contexts_exist(compose):
    for name, service in compose["services"].items():
        build = service.get("build")
        if not build:
            continue
        context = (ROOT / build["context"]).resolve()
        assert context.is_dir(), f"{name} builds from a missing context {context}"
        dockerfile = context / build.get("dockerfile", "Dockerfile")
        assert dockerfile.is_file(), f"{name} has no Dockerfile at {dockerfile}"


def test_api_has_a_healthcheck_that_proves_native_deps(compose, compose_text):
    health = compose["services"]["api"]["healthcheck"]
    assert health, "the api service must declare a healthcheck"
    probe = " ".join(health["test"]) if isinstance(health["test"], list) else health["test"]
    assert "/health" in probe
    # A missing libgomp.so.1 only shows up on the first LightGBM fit; importing
    # the native deps here turns that into a failed container instead.
    assert "lightgbm" in probe


def test_data_lives_in_named_volumes(compose):
    volumes = compose["services"]["api"]["volumes"]
    assert any("rsal-data" in str(volume) for volume in volumes), (
        "uploads/checkpoints must not be container-local"
    )
    assert set(compose["volumes"]) == {"rsal-data", "rsal-pg"}


def test_optional_services_are_behind_profiles(compose):
    assert compose["services"]["db"].get("profiles") == ["postgres"]
    # The default `up` must not require an optional profile.
    for name in ("api", "frontend"):
        assert not compose["services"][name].get("profiles"), f"{name} should not be optional"


def test_database_url_is_not_defaulted_to_the_optional_service(compose_text):
    """A default of db:5432 would break `up` without the postgres profile."""
    assert 'DATABASE_URL: "${DATABASE_URL:-}"' in compose_text
    assert "db:5432" not in compose_text.split("name: wbalc")[1].split("services:")[0]


def test_ports_are_configurable(compose):
    api_ports = compose["services"]["api"]["ports"]
    assert any("API_PORT" in str(port) for port in api_ports), "publish ports via env, not hard-coded"


# ------------------------------------------------------------------- launchers
@pytest.mark.parametrize("script", ["scripts/dev.sh", "scripts/up.sh"])
def test_launcher_scripts_are_executable_and_parse(script):
    path = ROOT / script
    assert path.is_file(), f"{script} is missing"
    assert path.stat().st_mode & 0o111, f"{script} is not executable"
    result = subprocess.run(["bash", "-n", str(path)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("script", ["scripts/dev.sh", "scripts/up.sh"])
def test_scripts_document_themselves(script):
    text = (ROOT / script).read_text(encoding="utf-8")
    assert "--help" in text or "-h" in text
    assert "usage" in text.lower()


def test_dev_script_explains_a_missing_docker_daemon():
    """The most common failure: docker installed but not running."""
    text = (ROOT / "scripts" / "dev.sh").read_text(encoding="utf-8")
    assert "daemon is not reachable" in text
    assert "docker compose" in text


def test_dev_script_requires_database_url_for_postgres():
    text = (ROOT / "scripts" / "dev.sh").read_text(encoding="utf-8")
    assert "DATABASE_URL" in text
    assert "sqlite" in text.lower()


def test_up_script_records_pids_and_logs():
    text = (ROOT / "scripts" / "up.sh").read_text(encoding="utf-8")
    assert ".run" in text and ".pid" in text
    assert "logs" in text


@pytest.mark.skipif(shutil.which("docker") is not None, reason="docker is installed here")
def test_dev_script_fails_clearly_without_docker():
    result = subprocess.run(
        ["bash", str(ROOT / "scripts" / "dev.sh"), "up"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode != 0, "it must not report success when it cannot start anything"
    assert "docker" in (result.stderr + result.stdout).lower()
