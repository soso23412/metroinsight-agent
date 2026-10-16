from __future__ import annotations

import json
from html import escape
from pathlib import Path

from metro_agent.domain.schemas import Analysis, Content
from metro_agent.storage.db import Store

LIMITATIONS = [
    "合成数据仅用于复现工程流程，不代表任何真实城市、乘客或事件。",
    "离线规则不是大模型，不提供模型准确率或真实业务效果证明。",
    "服务维度可重叠；事件候选不等于已证实事件。中性描述不自动等于负面。",
    "社交媒体反馈属于非概率样本，不能据此推断全体乘客满意率。",
]


def build_report(store: Store, dataset_id: str, annotator_version: str) -> dict:
    manifest = store.dataset_manifest(dataset_id)
    if manifest is None:
        raise ValueError("unknown_dataset")
    params = (dataset_id, annotator_version)
    successes = store.conn.execute(
        "SELECT count(*) FROM annotations WHERE dataset_id=? AND annotator_version=? "
        "AND status='success'",
        params,
    ).fetchone()[0]
    failures = store.conn.execute(
        "SELECT count(*) FROM annotations WHERE dataset_id=? AND annotator_version=? "
        "AND status='failed'",
        params,
    ).fetchone()[0]
    relevance = dict(
        store.conn.execute(
            "SELECT json_extract(payload,'$.relevance'),count(*) FROM annotations "
            "WHERE dataset_id=? AND annotator_version=? AND status='success' GROUP BY 1",
            params,
        ).fetchall()
    )
    sentiments = dict(
        store.conn.execute(
            "SELECT json_extract(payload,'$.sentiment'),count(*) FROM annotations "
            "WHERE dataset_id=? AND annotator_version=? AND status='success' "
            "AND json_extract(payload,'$.relevance')='relevant' GROUP BY 1",
            params,
        ).fetchall()
    )
    aspects = dict(
        store.conn.execute(
            "SELECT j.value,count(*) FROM annotations a,json_each(a.payload,'$.aspects') j "
            "WHERE a.dataset_id=? AND a.annotator_version=? AND a.status='success' GROUP BY j.value",
            params,
        ).fetchall()
    )
    events = store.conn.execute(
        "SELECT count(*) FROM annotations WHERE dataset_id=? AND annotator_version=? "
        "AND status='success' AND json_extract(payload,'$.event_candidate')=1",
        params,
    ).fetchone()[0]
    examples = []
    for row in store.conn.execute(
        "SELECT c.payload,a.payload FROM contents c JOIN annotations a USING "
        "(dataset_id,platform,content_id) WHERE c.dataset_id=? AND a.annotator_version=? "
        "AND a.status='success' ORDER BY c.platform,c.content_id LIMIT 12",
        params,
    ):
        content, analysis = (
            Content.model_validate_json(row[0]),
            Analysis.model_validate_json(row[1]),
        )
        analysis.verify_against(content)
        examples.append(
            {
                "content_key": content.key,
                "content_id": content.content_id,
                "text": content.text,
                "city": content.city,
                "line": content.line,
                "synthetic": content.synthetic,
                "analysis": analysis.model_dump(mode="json"),
            }
        )
    total = store.count_contents(dataset_id)
    return {
        "schema_version": "1",
        "dataset_id": dataset_id,
        "synthetic": bool(manifest.get("synthetic", False)),
        "annotator_version": annotator_version,
        "total_contents": total,
        "annotations_succeeded": successes,
        "annotations_failed": failures,
        "unprocessed": total - successes - failures,
        "relevant_denominator": relevance.get("relevant", 0),
        "relevance": relevance,
        "sentiments": sentiments,
        "aspects": aspects,
        "event_candidates": events,
        "examples": examples,
        "limitations": LIMITATIONS if manifest.get("synthetic") else LIMITATIONS[2:],
    }


def render_html(report: dict) -> str:
    labels = {
        "positive": "正面",
        "neutral": "中性",
        "negative": "负面",
        "mixed": "混合",
        "unknown": "未知",
    }
    denominator = report["relevant_denominator"]
    bars = []
    for label, n in report["aspects"].items():
        fraction = n / denominator if denominator else 0
        bars.append(
            f'<div class="bar"><span>{escape(label)}</span><div class="track">'
            f'<i style="width:{fraction * 100:.2f}%"></i></div><b>{n}</b></div>'
        )
    evidence = []
    for item in report["examples"]:
        analysis = item["analysis"]
        tags = " · ".join(analysis["aspects"]) or "无服务维度"
        sentiment = labels.get(analysis["sentiment"], analysis["sentiment"])
        evidence.append(
            f'<article><div class="ref">{escape(item["content_id"])} / '
            f"{escape(item['city'] or '未知城市')}</div><p>{escape(item['text'])}</p>"
            f"<small>{escape(tags)} · {escape(sentiment)}"
            f"{' · 未证实事件候选' if analysis['event_candidate'] else ''}</small></article>"
        )
    limitations = "".join(f"<li>{escape(text)}</li>" for text in report["limitations"])
    sentiments = " / ".join(f"{labels.get(k, k)} {v}" for k, v in report["sentiments"].items())
    mode = "合成样例 · 离线规则" if report["synthetic"] else "导入数据 · 请核对分析来源"
    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>MetroInsight / 服务反馈分析</title><style>
:root{{--ink:#142b36;--paper:#f4f1e9;--muted:#5e6e70;--line:#cbd1c8;--red:#c43b2e;--teal:#0f6c66}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--paper);color:var(--ink);font:16px/1.75 "Bahnschrift","Noto Sans CJK SC","Microsoft YaHei",sans-serif}}
main{{max-width:1060px;margin:auto;padding:48px 32px 60px}}header{{border-top:6px solid var(--ink);border-bottom:1px solid var(--line);padding:24px 0 32px}}
.kicker,.ref{{font:12px/1.6 "Consolas",monospace;letter-spacing:.08em;color:var(--muted)}}h1{{font-size:clamp(30px,5vw,52px);line-height:1.25;margin:12px 0 16px;letter-spacing:-.03em}}h1 em{{color:var(--teal);font-style:normal}}
.badge{{display:inline-block;color:var(--red);font-size:13px;border:1px solid currentColor;padding:3px 10px}}.intro{{max-width:650px;color:var(--muted);margin:16px 0 0}}
.numbers{{display:grid;grid-template-columns:repeat(4,1fr);border-bottom:1px solid var(--line);padding:24px 0;gap:20px}}.num{{font-size:38px;font-weight:700;line-height:1.2}}.num small{{display:block;font-size:12px;line-height:1.7;font-weight:400;color:var(--muted);margin-top:8px}}
.grid{{display:grid;grid-template-columns:1fr 1.15fr;gap:54px;padding-top:36px}}h2{{font-size:20px;margin:0 0 20px;border-left:4px solid var(--teal);padding-left:12px}}.bar{{display:grid;grid-template-columns:95px 1fr 25px;gap:12px;align-items:center;font-size:13px;margin:14px 0}}.track{{height:9px;background:#dce1d8}}.track i{{display:block;height:100%;background:var(--teal)}}.note{{font-size:13px;color:var(--muted)}}article{{border-top:1px solid var(--line);padding:15px 0}}article p{{margin:5px 0 8px;font-size:15px}}article small{{color:var(--muted);font-size:12px}}aside{{margin-top:32px;border-top:2px solid var(--ink);padding-top:18px}}li{{margin:5px 0;font-size:13px;color:var(--muted)}}footer{{margin-top:32px;font:11px/1.8 "Consolas",monospace;color:var(--muted);overflow-wrap:anywhere}}
@media(max-width:700px){{main{{padding:24px 20px}}.numbers{{grid-template-columns:repeat(2,1fr)}}.grid{{grid-template-columns:1fr;gap:32px}}}}
</style></head><body><main><header><div class="kicker">METROINSIGHT / SERVICE FEEDBACK / 001</div>
<h1>每项判断，<em>回到证据。</em></h1><span class="badge">{mode}</span>
<p class="intro">从结构化内容到服务维度与情绪，再回到原文核对。当前版本验证离线数据流程；尚未提供自主工具调用或真实模型效果结论。</p></header>
<section class="numbers"><div class="num">{report["total_contents"]}<small>内容总数</small></div>
<div class="num">{denominator}<small>有效服务反馈分母</small></div>
<div class="num">{report["event_candidates"]}<small>未证实事件候选</small></div>
<div class="num">{report["annotations_failed"]}<small>处理失败</small></div></section>
<div class="grid"><section><h2>服务维度</h2>{"".join(bars)}<p class="note">分母：{denominator}条有效服务反馈。单条可有多个维度，因此各维度数不能直接相加。</p>
<h2 style="margin-top:32px">情绪分布</h2><p class="note">{escape(sentiments)}</p></section>
<section><h2>原文核对</h2>{"".join(evidence)}</section></div>
<aside><h2>解读范围</h2><ul>{limitations}</ul></aside>
<footer>DATASET {escape(report["dataset_id"])}<br>ANNOTATOR {escape(report["annotator_version"])}<br>MetroInsight Agent · Reproducible workflow baseline</footer>
</main></body></html>"""


def write_report(report: dict, output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    (output / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (output / "report.html").write_text(render_html(report), encoding="utf-8")
