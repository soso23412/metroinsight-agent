import json

from fastapi.testclient import TestClient

from metro_agent.api.app import create_app


def test_api_complete_idempotent_replay_sse_and_report(tmp_path):
    with TestClient(create_app(tmp_path)) as client:
        assert client.get("/health").json()["live_enabled"] is False
        assert "循证而行" in client.get("/").text
        datasets = client.get("/datasets").json()
        assert datasets["datasets"][0]["synthetic"] is True
        body = {"question": "分析示例1号线服务反馈"}
        response = client.post("/runs", json=body, headers={"Idempotency-Key": "one"})
        assert response.status_code == 202
        run_id = response.json()["run_id"]
        state = client.get(f"/runs/{run_id}").json()
        assert state["status"] == "completed"
        assert "messages" not in state and "visible" not in state
        repeated = client.post("/runs", json=body, headers={"Idempotency-Key": "one"})
        assert repeated.json()["run_id"] == run_id
        assert (
            client.post(
                "/runs", json={"question": "不同问题"}, headers={"Idempotency-Key": "one"}
            ).status_code
            == 409
        )
        report = client.get(f"/reports/{run_id}").json()
        assert report["metrics"][0]["relevant_denominator"] == 5
        events = client.get(f"/runs/{run_id}/events", headers={"Last-Event-ID": "9"})
        assert "id: 10" in events.text and "id: 9\n" not in events.text
        assert (
            client.get(f"/runs/{run_id}/events", headers={"Last-Event-ID": "bad"}).status_code
            == 422
        )
        assert client.post(f"/runs/{run_id}/resume").json()["status"] == "completed"


def test_api_invalid_live_disabled_cross_origin_and_missing(tmp_path):
    with TestClient(create_app(tmp_path)) as client:
        assert client.post("/runs", json={"question": "x", "mode": "live"}).status_code == 403
        assert client.post("/runs", json={"question": ""}).status_code == 422
        assert (
            client.post("/runs", json={"question": "x", "dataset_id": "unknown"}).status_code == 404
        )
        assert client.get("/runs/missing").status_code == 404
        assert (
            client.post(
                "/runs", json={"question": "x"}, headers={"Origin": "https://evil.example"}
            ).status_code
            == 403
        )
        assert client.get("/health", headers={"Host": "evil.example"}).status_code == 403
        assert (
            client.post("/runs", content=json.dumps({"question": "x" * 22000})).status_code == 413
        )


def test_api_html_and_script_do_not_interpolate_untrusted_data(tmp_path):
    with TestClient(create_app(tmp_path)) as client:
        body = {"question": "<script>alert(1)</script> 分析示例1号线"}
        result = client.post("/runs", json=body).json()
        assert (
            client.get(f"/runs/{result['run_id']}").json()["report"]["question"] == body["question"]
        )
        js = client.get("/app.js").text
        assert "innerHTML" not in js and "textContent" in js
        assert "frame-ancestors 'none'" in client.get("/").headers["content-security-policy"]
