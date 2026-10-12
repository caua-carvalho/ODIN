"""Daily briefing API tests.

Covers the frozen ``GET /api/briefing`` contract pieces in isolation so the
suite never touches the network or the real database:

- WMO weather-code mapping and Open-Meteo response parsing (httpx mocked);
- the Open-Meteo in-memory cache;
- git collection against a throwaway repo (branch/changes/commit/ahead/behind)
  and the "not a repository" -> None case;
- workspace scanning (recent files + TODO/FIXME/XXX counting);
- the boot-once ``app_state`` flow (should_show true -> ack -> false);
- section-level resilience (a failing collector degrades, never raises).
"""
import subprocess
import sys
from pathlib import Path

import httpx
import pytest

# Make sure we can import app modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.api.routes import briefing
from app.agent.providers.base import LLMChunk
from app.database.models import Base


@pytest.fixture(autouse=True)
def _clear_weather_cache():
    briefing._reset_weather_cache()
    yield
    briefing._reset_weather_cache()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
async def _make_session(tmp_path):
    """Create a temp SQLite DB with all tables and return (engine, factory)."""
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'test.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    return engine, factory


def _init_repo(path: Path) -> None:
    subprocess.run(["git", "init", "-b", "main", str(path)], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(path), "config", "user.email", "test@example.com"], check=True)
    subprocess.run(["git", "-C", str(path), "config", "user.name", "Test"], check=True)


def _commit(path: Path, message: str) -> None:
    subprocess.run(["git", "-C", str(path), "add", "-A"], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(path), "commit", "-m", message],
        check=True,
        capture_output=True,
    )


class _FakeResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


class _FakeAsyncClient:
    def __init__(self, payload=None, captured=None, error=None, **kwargs) -> None:
        self._payload = payload
        self._captured = captured if captured is not None else {}
        self._error = error

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False

    async def get(self, url):
        self._captured["url"] = url
        if self._error is not None:
            raise self._error
        return _FakeResponse(self._payload)


SAMPLE_WEATHER = {
    "current": {
        "temperature_2m": 22.5,
        "apparent_temperature": 24.0,
        "weather_code": 2,
    },
    "daily": {
        "temperature_2m_max": [28.0],
        "temperature_2m_min": [17.0],
        "precipitation_probability_max": [40],
    },
}


# ---------------------------------------------------------------------------
# Weather
# ---------------------------------------------------------------------------
class TestWeatherCodeMapping:
    @pytest.mark.parametrize(
        "code,expected",
        [
            (0, "Céu limpo"),
            (2, "Parcialmente nublado"),
            (61, "Chuva leve"),
            (95, "Trovoada"),
            (1234, "Condições desconhecidas"),
        ],
    )
    def test_describe(self, code, expected):
        assert briefing.describe_weather_code(code) == expected


class TestParseWeatherPayload:
    def test_parses_full_payload(self):
        weather = briefing.parse_weather_payload(SAMPLE_WEATHER, "São José dos Campos")
        assert weather is not None
        assert weather.city == "São José dos Campos"
        assert weather.temperature == 22.5
        assert weather.apparent == 24.0
        assert weather.code == 2
        assert weather.description == "Parcialmente nublado"
        assert weather.temp_max == 28.0
        assert weather.temp_min == 17.0
        assert weather.precipitation_probability == 40

    def test_missing_current_returns_none(self):
        assert briefing.parse_weather_payload({}, "X") is None

    def test_handles_missing_daily_arrays(self):
        payload = {"current": {"weather_code": 3, "temperature_2m": 10.0}}
        weather = briefing.parse_weather_payload(payload, "X")
        assert weather is not None
        assert weather.code == 3
        assert weather.temp_max == 0.0
        assert weather.precipitation_probability == 0


class TestFetchWeather:
    async def test_parses_and_caches(self, monkeypatch):
        captured = {}
        monkeypatch.setattr(
            briefing.httpx,
            "AsyncClient",
            lambda **kw: _FakeAsyncClient(SAMPLE_WEATHER, captured, **kw),
        )

        weather = await briefing._fetch_weather()
        assert weather is not None
        assert weather.temperature == 22.5
        # The request targeted Open-Meteo with the configured coordinates.
        assert "api.open-meteo.com" in captured["url"]
        assert "latitude=" in captured["url"]
        assert "current=temperature_2m" in captured["url"]

        # A second call within the TTL must hit the cache, not the network.
        def _boom(**kw):
            raise AssertionError("weather cache miss")

        monkeypatch.setattr(briefing.httpx, "AsyncClient", _boom)
        assert await briefing._fetch_weather() is weather

    async def test_http_error_is_contained_by_safe(self, monkeypatch):
        monkeypatch.setattr(
            briefing.httpx,
            "AsyncClient",
            lambda **kw: _FakeAsyncClient(error=httpx.ConnectError("boom"), **kw),
        )
        # _fetch_weather raises; the section wrapper turns it into null.
        assert await briefing._safe(briefing._fetch_weather(), None) is None


# ---------------------------------------------------------------------------
# Git
# ---------------------------------------------------------------------------
class TestGitCollection:
    def test_repo_snapshot(self, tmp_path):
        repo = tmp_path / "myrepo"
        repo.mkdir()
        _init_repo(repo)
        (repo / "a.txt").write_text("hello")
        _commit(repo, "initial commit")

        info = briefing.collect_git_repo(str(repo))
        assert info is not None
        assert info.name == "myrepo"
        assert info.path == str(repo)
        assert info.branch == "main"
        assert info.changes == 0
        assert "initial commit" in info.last_commit
        assert "·" in info.last_commit
        assert (info.ahead, info.behind) == (0, 0)  # no upstream

    def test_counts_uncommitted_changes(self, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_repo(repo)
        (repo / "a.txt").write_text("hello")
        _commit(repo, "initial")
        (repo / "b.txt").write_text("untracked")

        info = briefing.collect_git_repo(str(repo))
        assert info is not None
        assert info.changes == 1

    def test_ahead_behind_with_upstream(self, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_repo(repo)
        (repo / "a.txt").write_text("a")
        _commit(repo, "base")
        subprocess.run(["git", "-C", str(repo), "checkout", "-b", "feature"], check=True, capture_output=True)
        (repo / "b.txt").write_text("b")
        _commit(repo, "feature work")
        subprocess.run(
            ["git", "-C", str(repo), "branch", "--set-upstream-to=main"],
            check=True,
            capture_output=True,
        )

        info = briefing.collect_git_repo(str(repo))
        assert info is not None
        assert info.branch == "feature"
        assert info.ahead == 1
        assert info.behind == 0

    def test_not_a_repo_is_none(self, tmp_path):
        plain = tmp_path / "plain"
        plain.mkdir()
        assert briefing.collect_git_repo(str(plain)) is None
        assert briefing.collect_git_repo(str(tmp_path / "missing")) is None


# ---------------------------------------------------------------------------
# Workspace files
# ---------------------------------------------------------------------------
class TestWorkspaceScan:
    def test_recent_files_and_todo_count(self, tmp_path):
        ws = tmp_path / "ws"
        ws.mkdir()
        (ws / "recent.py").write_text("# TODO: fix this\nprint(1)\n")
        (ws / "note.md").write_text("FIXME and TODO\n")

        result = briefing.scan_workspace(str(ws))
        assert result.todo_count == 3
        paths = {f.path for f in result.recent}
        assert "recent.py" in paths
        assert "note.md" in paths
        for item in result.recent:
            assert item.age_seconds >= 0

    def test_skips_noisy_directories(self, tmp_path):
        ws = tmp_path / "ws"
        ws.mkdir()
        (ws / "node_modules").mkdir()
        (ws / "node_modules" / "x.py").write_text("TODO TODO TODO")
        (ws / ".git").mkdir()
        (ws / ".git" / "y.py").write_text("TODO")
        (ws / "visible.py").write_text("TODO")

        result = briefing.scan_workspace(str(ws))
        assert result.todo_count == 1
        assert all("node_modules" not in f.path for f in result.recent)
        assert all(".git" not in f.path for f in result.recent)

    def test_recent_is_limited_to_five(self, tmp_path):
        ws = tmp_path / "ws"
        ws.mkdir()
        for i in range(7):
            (ws / f"file{i}.txt").write_text("x")
        result = briefing.scan_workspace(str(ws))
        assert len(result.recent) == 5

    def test_missing_workspace_is_empty(self, tmp_path):
        result = briefing.scan_workspace(str(tmp_path / "nope"))
        assert result.recent == []
        assert result.todo_count == 0


# ---------------------------------------------------------------------------
# Boot-once state
# ---------------------------------------------------------------------------
class TestBootOnce:
    def test_should_show_logic(self):
        assert briefing.should_show_briefing(None, 100.0) is True
        assert briefing.should_show_briefing("", 100.0) is True
        assert briefing.should_show_briefing("100.0", 100.0) is False
        assert briefing.should_show_briefing("100.0", 200.0) is True
        assert briefing.should_show_briefing("garbage", 100.0) is True

    async def test_state_roundtrip_flips_should_show(self, tmp_path, monkeypatch):
        monkeypatch.setattr(briefing.psutil, "boot_time", lambda: 1234.0)
        engine, Session = await _make_session(tmp_path)
        try:
            async with Session() as db:
                last = await briefing.get_state(db, briefing.STATE_LAST_BRIEFING_BOOT)
                assert briefing.should_show_briefing(last, briefing.psutil.boot_time()) is True
                await briefing.set_state(
                    db, briefing.STATE_LAST_BRIEFING_BOOT, str(briefing.psutil.boot_time())
                )

            async with Session() as db:
                last = await briefing.get_state(db, briefing.STATE_LAST_BRIEFING_BOOT)
                assert last == "1234.0"
                assert briefing.should_show_briefing(last, briefing.psutil.boot_time()) is False
                # A later boot re-arms the briefing.
                assert briefing.should_show_briefing(last, 9999.0) is True
        finally:
            await engine.dispose()

    async def test_ack_endpoint_marks_current_boot(self, tmp_path, monkeypatch):
        monkeypatch.setattr(briefing.psutil, "boot_time", lambda: 555.0)
        engine, Session = await _make_session(tmp_path)
        try:
            async with Session() as db:
                response = await briefing.acknowledge_briefing(db=db)
                assert response.acknowledged is True
                assert response.boot_time == 555.0
                last = await briefing.get_state(db, briefing.STATE_LAST_BRIEFING_BOOT)
                assert last == "555.0"
        finally:
            await engine.dispose()


# ---------------------------------------------------------------------------
# Collection orchestration
# ---------------------------------------------------------------------------
class TestCollectResilience:
    async def test_failing_section_degrades_to_default(self, tmp_path, monkeypatch):
        engine, Session = await _make_session(tmp_path)
        try:
            async def _boom_weather():
                raise RuntimeError("weather down")

            async def _git_one_null():
                return [None]

            monkeypatch.setattr(briefing, "_fetch_weather", _boom_weather)
            monkeypatch.setattr(briefing, "_collect_git", _git_one_null)
            monkeypatch.setattr(
                briefing,
                "scan_workspace",
                lambda ws: briefing.BriefingFiles(recent=[], todo_count=0),
            )
            monkeypatch.setattr(briefing, "collect_system", briefing._empty_system)
            monkeypatch.setattr(briefing, "collect_runtime", briefing._empty_runtime)
            monkeypatch.setattr(briefing.psutil, "boot_time", lambda: 42.0)

            async with Session() as db:
                result = await briefing._collect(db)

            assert result.weather is None
            assert result.git == [None]
            assert result.should_show is True
            assert result.boot_time == 42.0
            assert result.generated_at.endswith("Z")
            assert result.system.load_avg == [0.0, 0.0, 0.0]
            assert result.permissions.pending == 0
            assert result.conversations == []
        finally:
            await engine.dispose()

    async def test_collect_reads_permissions_and_conversations(self, tmp_path, monkeypatch):
        from datetime import datetime, UTC

        from app.database.models import Conversation, PermissionRequest

        engine, Session = await _make_session(tmp_path)
        try:
            async def _no_weather():
                return None

            async def _no_git():
                return []

            monkeypatch.setattr(briefing, "_fetch_weather", _no_weather)
            monkeypatch.setattr(briefing, "_collect_git", _no_git)
            monkeypatch.setattr(
                briefing,
                "scan_workspace",
                lambda ws: briefing.BriefingFiles(recent=[], todo_count=0),
            )
            monkeypatch.setattr(briefing, "collect_system", briefing._empty_system)
            monkeypatch.setattr(briefing, "collect_runtime", briefing._empty_runtime)
            monkeypatch.setattr(briefing.psutil, "boot_time", lambda: 7.0)

            async with Session() as db:
                db.add(
                    PermissionRequest(
                        id="p1",
                        conversation_id="c1",
                        tool="write_file",
                        operation="WRITE",
                        target="/etc/hosts",
                        risk_level="high",
                        status="pending",
                    )
                )
                db.add(
                    PermissionRequest(
                        id="p2",
                        conversation_id="c1",
                        tool="execute_command",
                        operation="EXECUTE",
                        target="sudo reboot",
                        risk_level="critical",
                        status="pending",
                    )
                )
                db.add(
                    PermissionRequest(
                        id="p3",
                        conversation_id="c1",
                        tool="read_file",
                        operation="READ",
                        target="/tmp/x",
                        risk_level="low",
                        status="approved",
                    )
                )
                db.add(
                    Conversation(
                        id="c1",
                        title="Primeira",
                        created_at=datetime.now(UTC),
                        updated_at=datetime.now(UTC),
                    )
                )
                await db.commit()

            async with Session() as db:
                result = await briefing._collect(db)

            assert result.permissions.pending == 2
            assert result.permissions.high_risk == 2
            assert len(result.conversations) == 1
            assert result.conversations[0].id == "c1"
            assert result.conversations[0].title == "Primeira"
        finally:
            await engine.dispose()


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
class TestSummary:
    async def test_generate_summary_concatenates_text_chunks(self, monkeypatch):
        import app.main

        class _Provider:
            async def generate(self, messages, tools, system):
                assert tools == []
                assert messages and messages[0].content
                yield LLMChunk(type="text", content="Bom dia, ")
                yield LLMChunk(type="text", content="Cauã!")
                yield LLMChunk(type="done")

        class _Agent:
            provider = _Provider()

        monkeypatch.setattr(app.main, "odin_agent", _Agent())

        briefing_data = briefing.BriefingResponse(
            should_show=True,
            boot_time=1.0,
            generated_at="2026-10-11T08:00:00Z",
            weather=None,
            git=[],
            files=briefing.BriefingFiles(recent=[], todo_count=0),
            system=briefing._empty_system(),
            runtime=briefing._empty_runtime(),
            permissions=briefing.BriefingPermissions(pending=0, high_risk=0),
            conversations=[],
        )
        assert await briefing._generate_summary(briefing_data) == "Bom dia, Cauã!"

    async def test_generate_summary_without_agent_is_none(self, monkeypatch):
        import app.main

        monkeypatch.setattr(app.main, "odin_agent", None)
        briefing_data = briefing.BriefingResponse(
            should_show=True,
            boot_time=1.0,
            generated_at="2026-10-11T08:00:00Z",
            weather=None,
            git=[],
            files=briefing.BriefingFiles(recent=[], todo_count=0),
            system=briefing._empty_system(),
            runtime=briefing._empty_runtime(),
            permissions=briefing.BriefingPermissions(pending=0, high_risk=0),
            conversations=[],
        )
        assert await briefing._generate_summary(briefing_data) is None
