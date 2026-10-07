import importlib.util
import pathlib

import pytest

spec = importlib.util.spec_from_file_location("server", pathlib.Path(__file__).parents[1] / "mcp/cheap-llm/server.py")
server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server)


@pytest.fixture
def root(tmp_path, monkeypatch):
    monkeypatch.setenv("CHEAP_LLM_ROOT", str(tmp_path))
    (tmp_path / "a.txt").write_text("hello")
    (tmp_path / ".env").write_text("K=v")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "my_secrets.txt").write_text("x")
    (tmp_path / "bin").write_bytes(b"\xff\xfe")
    return tmp_path


def test_off_by_default(monkeypatch):
    monkeypatch.delenv("CHEAP_LLM_ROOT", raising=False)
    with pytest.raises(ValueError, match="off"):
        server._read_paths(["a.txt"])


def test_reads_file(root):
    assert server._read_paths(["a.txt"]) == "=== a.txt ===\nhello"


@pytest.mark.parametrize("bad", ["../x", "/etc/passwd", ".env", "sub/my_secrets.txt", "bin", "sub"])
def test_refused(root, bad):
    with pytest.raises(ValueError):
        server._read_paths([bad])


def test_symlink_escape(root, tmp_path_factory):
    outside = tmp_path_factory.mktemp("out") / "o.txt"
    outside.write_text("x")
    (root / "link").symlink_to(outside)
    with pytest.raises(ValueError, match="outside"):
        server._read_paths(["link"])


def test_size_cap(root, monkeypatch):
    monkeypatch.setattr(server, "MAX_BYTES", 3)
    with pytest.raises(ValueError, match="exceed"):
        server._read_paths(["a.txt"])
