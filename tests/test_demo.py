import json
import subprocess
import sys

from metro_agent.demo import run_demo
from metro_agent.reporting.render import render_html


def test_demo_works_without_network_or_credentials(tmp_path, monkeypatch):
    import socket

    def deny_network(*args, **kwargs):
        raise AssertionError("offline demo attempted a network call")

    monkeypatch.setattr(socket.socket, "connect", deny_network)
    monkeypatch.setattr(socket, "create_connection", deny_network)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("QWEN_API_KEY", raising=False)
    result = run_demo(tmp_path)
    assert result["model_calls"] == 0 and result["content_count"] == 12
    report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert report["synthetic"] is True
    assert report["relevant_denominator"] == 10
    assert report["sentiments"] == {"mixed": 1, "negative": 4, "neutral": 3, "positive": 2}
    assert report["event_candidates"] == 1
    assert report["aspects"]["拥挤客流"] == 3
    repeated = run_demo(tmp_path)
    assert repeated["processing"]["cached"] == 12
    assert repeated["processing"]["attempted"] == 0


def test_html_escapes_untrusted_content(tmp_path):
    run_demo(tmp_path)
    report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    report["examples"][0]["text"] = '<script>alert("bad")</script>'
    rendered = render_html(report)
    assert "<script>" not in rendered
    assert "&lt;script&gt;" in rendered
    assert "合成样例" in rendered


def test_cli_demo_works_from_foreign_working_directory(tmp_path):
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "metro_agent",
            "demo",
            "--offline",
            "--output",
            str(tmp_path / "out"),
        ],
        cwd=tmp_path,
        capture_output=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr.decode(errors="replace")
    assert json.loads(result.stdout)["model_calls"] == 0
    assert (tmp_path / "out" / "report.html").exists()
