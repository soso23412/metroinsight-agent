"use strict";
const $ = id => document.getElementById(id);
let datasets = [], active = null, report = null;
function node(tag, text, parent) { const e = document.createElement(tag); e.textContent = text; if(parent) parent.append(e); return e; }
async function api(url, options) {
  const response = await fetch(url, options);
  const body = await response.json();
  if (!response.ok) throw new Error(body.detail || `HTTP ${response.status}`);
  return body;
}
function showError(error) { $("error").hidden = false; $("error").textContent = `未完成：${error.message}`; }
function scope() {
  const d = datasets.find(x => x.dataset_id === $("dataset").value);
  if(!d) return;
  $("scope").textContent = `${d.synthetic ? "SYNTHETIC / 合成样例" : "PRIVATE / 本地授权数据"} · ${d.contents} 条帖子。评论不计入统计。`;
  $("version").replaceChildren();
  d.annotation_versions.forEach(v => { const e = node("option", v, $("version")); e.value = v; });
}
function render(state) {
  $("empty").hidden = true; $("result").hidden = false;
  $("status").textContent = state.status.toUpperCase();
  $("steps").textContent = state.steps; $("cost").textContent = state.reserved_cost_usd.toFixed(4);
  $("trace").replaceChildren();
  state.events.forEach(e => node("div", `${String(e.seq).padStart(2,"0")}  ${e.tool || e.stage} · ${e.status}`, $("trace")));
  $("runid").textContent = `Run / ${state.run_id}`;
  $("resume").hidden = !["paused", "needs_review", "running"].includes(state.status);
  if(!state.report) return;
  report = state.report;
  $("provenance").textContent = `${report.synthetic ? "SYNTHETIC 合成数据" : "本地授权数据"} / ${report.mode === "offline" ? "离线脚本 · 无模型调用" : "真实模型"}`;
  $("count").textContent = report.metrics[0]?.relevant_denominator ?? "—";
  $("metrics").replaceChildren();
  report.metrics.forEach(m => {
    node("p", `${m.group_by} · 有效分母 ${m.relevant_denominator} / 已标注 ${m.annotated_total}${m.overlapping ? " · 多标签可重叠" : ""}`, $("metrics"));
    const table = node("table", "", $("metrics"));
    m.groups.forEach(g => { const row = node("tr", "", table); node("td", g.label, row); node("td", String(g.count), row); });
  });
  report.timelines?.forEach(t => {
    node("h3", "事件候选时间线 · 以帖子发布时间排序", $("metrics"));
    t.items.forEach(e => node("p", `${e.published_at || "时间缺失"} · ${e.content_id} · 未经证实`, $("metrics")));
  });
  $("evidence").replaceChildren();
  report.evidence.forEach(e => { const q = node("blockquote", e.quote, $("evidence")); node("footer", `${e.content_id} · ${e.published_at || "发布时间缺失"}\n${e.evidence_id}`, q); });
  if(!report.evidence.length) node("p", "没有足够证据支持该范围的结论。", $("evidence"));
  $("limits").replaceChildren(); report.limitations.forEach(t => node("li", t, $("limits")));
  $("download").hidden = false;
}
async function poll(id) {
  try {
    const state = await api(`/runs/${id}`); render(state);
    if(["queued", "running"].includes(state.status) && active === id) setTimeout(() => poll(id), 1000);
    else $("submit").disabled = false;
  } catch(error) { showError(error); $("submit").disabled = false; }
}
$("submit").addEventListener("click", async () => {
  $("error").hidden = true; $("submit").disabled = true; report = null;
  $("result").hidden = true; $("empty").hidden = false; $("download").hidden = true;
  $("evidence").replaceChildren(); $("metrics").replaceChildren(); $("limits").replaceChildren(); $("count").textContent = "—";
  $("provenance").textContent = "任务运行中 / 报告尚未校验";
  try {
    const state = await api("/runs", {method:"POST", headers:{"Content-Type":"application/json", "Idempotency-Key":crypto.randomUUID()}, body:JSON.stringify({question:$("question").value, dataset_id:$("dataset").value, annotator_version:$("version").value, mode:$("mode").value})});
    active = state.run_id; localStorage.setItem("metro-last-run", active); render(state); poll(active);
  } catch(error) { showError(error); $("submit").disabled = false; }
});
$("resume").addEventListener("click", async () => {
  try { await api(`/runs/${active}/resume`, {method:"POST"}); poll(active); } catch(error) { showError(error); }
});
$("download").addEventListener("click", () => {
  const url = URL.createObjectURL(new Blob([JSON.stringify(report,null,2)], {type:"application/json"}));
  const a = document.createElement("a"); a.href = url; a.download = `metro-${report.run_id}.json`; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
});
document.querySelectorAll("[data-question]").forEach(b => b.addEventListener("click", () => { $("question").value = b.dataset.question; }));
$("dataset").addEventListener("change", scope);
(async () => {
  try {
    const data = await api("/datasets"); datasets = data.datasets;
    datasets.forEach(d => { const e = node("option", d.dataset_id, $("dataset")); e.value = d.dataset_id; });
    $("dataset").value = data.default_dataset; scope();
    if((await api("/health")).live_enabled) { const e = node("option", "真实模型 · 消耗已配置额度", $("mode")); e.value = "live"; }
    const previous = localStorage.getItem("metro-last-run"); if(previous) { active = previous; poll(previous); }
  } catch(error) { showError(error); }
})();
