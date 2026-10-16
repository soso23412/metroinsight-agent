from __future__ import annotations

import json
from html import escape
from pathlib import Path

from metro_agent.agent.contracts import FinishArgs
from metro_agent.agent.journal import public_run
from metro_agent.storage.db import Store


def verify_report(args: FinishArgs, state: dict, store: Store) -> dict:
    if len(set(args.evidence_ids)) != len(args.evidence_ids):
        raise ValueError("duplicate_evidence")
    if args.status == "completed" and (not args.evidence_ids or not args.metric_result_ids):
        raise ValueError("completed_requires_metrics_and_evidence")
    evidence = []
    for key in args.evidence_ids:
        item = state["visible"].get(key)
        if not item:
            raise ValueError("citation_not_observed")
        original = store.get_content(
            state["task"]["dataset_id"], item["platform"], item["content_id"]
        )
        if (
            original is None
            or original.key != key
            or original.text_sha256 != item["text_sha256"]
            or original.text[item["quote_start"] : item["quote_end"]] != item["quote"]
        ):
            raise ValueError("citation_source_mismatch")
        evidence.append(item)
    metrics = []
    for key in dict.fromkeys(args.metric_result_ids):
        receipt = state["receipts"].get(key)
        if not receipt or not receipt.get("ok") or receipt["tool"] != "aggregate_feedback":
            raise ValueError("metric_not_observed")
        metrics.append({"result_id": key, **receipt["data"]})
    timelines = []
    for key in dict.fromkeys(args.timeline_result_ids):
        receipt = state["receipts"].get(key)
        if not receipt or not receipt.get("ok") or receipt["tool"] != "get_event_timeline":
            raise ValueError("timeline_not_observed")
        timelines.append({"result_id": key, **receipt["data"]})
    synthetic = bool(store.dataset_manifest(state["task"]["dataset_id"]).get("synthetic"))
    return {
        "schema_version": "agent-report-v1",
        "status": args.status,
        "run_id": state["run_id"],
        "dataset_id": state["task"]["dataset_id"],
        "annotator_version": state["task"]["annotator_version"],
        "mode": state["task"]["mode"],
        "synthetic": synthetic,
        "question": state["task"]["question"],
        "metrics": metrics,
        "evidence": evidence,
        "recommendations_unverified": args.recommendations,
        "timelines": timelines,
        "limitations": [
            "社交媒体为非概率样本，不能推断全体乘客满意率。",
            "统计仅覆盖所选版本成功标注的帖子，评论不计入分母；检索Top-k仅为例证。",
            "事件候选未经独立核实，帖子发布时间不等于事件发生时间。",
            "数字/引用存在性已校验；标注准确性和问题回答完整性仍需独立人工评估。",
        ]
        + (
            ["合成数据 + 离线脚本策略，仅验证工程合同，未调用大模型。"]
            if state["task"]["mode"] == "offline"
            else []
        ),
    }


def write_agent_report(state: dict, directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "run.json").write_text(
        json.dumps(public_run(state), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    if state["report"] is None:
        return
    report = state["report"]
    (directory / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    sections = []
    for metric in report["metrics"]:
        groups = "".join(
            f"<tr><td>{escape(g['label'])}</td><td>{g['count']}</td></tr>" for g in metric["groups"]
        )
        sections.append(
            f"<section><h2>{escape(metric['group_by'])}</h2><p>有效反馈分母 {metric['relevant_denominator']} · 已标注 {metric['annotated_total']}</p><table>{groups}</table><small>{escape(metric['result_id'])}</small></section>"
        )
    for timeline in report["timelines"]:
        items = "".join(
            f"<li>{escape(item['published_at'] or '发布时间缺失')} · {escape(item['content_id'])} · 未证实</li>"
            for item in timeline["items"]
        )
        sections.append(
            f"<section><h2>事件候选 · 帖子发布时间线</h2><ul>{items}</ul><small>{escape(timeline['time_basis'])}</small></section>"
        )
    quotes = "".join(
        f"<blockquote>{escape(e['quote'])}<footer>{escape(e['content_id'])} · {escape(e['published_at'] or '时间缺失')}<br>{escape(e['evidence_id'])}</footer></blockquote>"
        for e in report["evidence"]
    )
    limits = "".join(f"<li>{escape(s)}</li>" for s in report["limitations"])
    html = f"""<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>MetroInsight · 证据报告</title>
<style>body{{margin:0;background:#f4f1e8;color:#183e3c;font:17px/1.7 Georgia,'Microsoft YaHei',serif}}main{{max-width:1000px;margin:60px auto;padding:24px}}h1{{font-size:48px}}section,blockquote{{background:#fffdf7;padding:24px;border-left:4px solid #da713f;margin:20px 0}}table{{width:100%;text-align:left;border-collapse:collapse}}td{{border-bottom:1px solid #ddd;padding:10px}}footer,small{{font-size:12px;overflow-wrap:anywhere;color:#556f6b}}.tag{{background:#183e3c;color:#fff;padding:8px 16px}}</style>
<main><span class="tag">{escape(report["mode"])} · {"SYNTHETIC 合成样例" if report["synthetic"] else "授权导入数据"}</span><h1>城市的声音，有据可查。</h1><p>{escape(report["question"])}</p><p>任务状态：{escape(report["status"])}</p>{"".join(sections)}<h2>原文证据</h2>{quotes or "<p>无足够证据，无法支持所请求的结论。</p>"}<h2>解释边界</h2><ul>{limits}</ul><footer>Run {escape(state["run_id"])} · {escape(report["dataset_id"])}</footer></main></html>"""
    (directory / "report.html").write_text(html, encoding="utf-8")
