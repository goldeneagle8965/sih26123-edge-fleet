const canvas = document.getElementById("grid");
const ctx = canvas.getContext("2d");
const COLORS = ["#e0a106", "#2f9e8a", "#c44b2b", "#6b8fd4"];
let last = null;
let paused = false;

async function getState() {
  const r = await fetch("/state");
  last = await r.json();
  draw(last);
  render(last);
}

async function post(body) {
  await fetch("/", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  await getState();
}

document.getElementById("btn-aisle").onclick = () => post({ action: "block_aisle" });
document.getElementById("btn-pause").onclick = async () => {
  paused = !paused;
  document.getElementById("btn-pause").textContent = paused ? "Resume" : "Pause";
  await post({ action: paused ? "pause" : "resume" });
};
document.getElementById("btn-reset").onclick = () => post({ action: "reset" });
document.getElementById("btn-ubpa").onclick = () => post({ action: "policy", policy: "ubpa" });
document.getElementById("btn-sw").onclick = () => post({ action: "policy", policy: "stop_wait" });

function pushRadio() {
  const drop = Number(document.getElementById("drop-slider").value) / 100;
  const delay = Number(document.getElementById("delay-slider").value);
  post({ action: "radio", drop_prob: drop, delay });
}
document.getElementById("drop-slider").onchange = pushRadio;
document.getElementById("delay-slider").onchange = pushRadio;

canvas.addEventListener("click", (ev) => {
  if (!last) return;
  const w = last.world.width, h = last.world.height;
  const cell = Math.min(canvas.width / w, canvas.height / h);
  const ox = (canvas.width - cell * w) / 2;
  const oy = (canvas.height - cell * h) / 2;
  const r = canvas.getBoundingClientRect();
  const x = Math.floor((ev.clientX - r.left) * (canvas.width / r.width) - ox) / cell;
  const y = Math.floor((ev.clientY - r.top) * (canvas.height / r.height) - oy) / cell;
  const ix = Math.floor(x), iy = Math.floor(y);
  if (ix >= 0 && iy >= 0 && ix < w && iy < h) post({ action: "toggle", x: ix, y: iy });
});

function draw(s) {
  const w = s.world.width, h = s.world.height;
  const cell = Math.min(canvas.width / w, canvas.height / h);
  const ox = (canvas.width - cell * w) / 2;
  const oy = (canvas.height - cell * h) / 2;
  ctx.fillStyle = "#1b1712";
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  const walls = new Set((s.world.walls || []).map((p) => p.join(",")));
  const blocked = new Set((s.world.blocked || []).map((p) => p.join(",")));
  const turnouts = new Set((s.world.turnouts || []).map((p) => p.join(",")));
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      const key = x + "," + y;
      if (walls.has(key)) ctx.fillStyle = "#5c4634";
      else if (blocked.has(key)) ctx.fillStyle = "#c44b2b";
      else if (turnouts.has(key)) ctx.fillStyle = "#d4c09a";
      else ctx.fillStyle = "#c9b394";
      ctx.fillRect(ox + x * cell + 1, oy + y * cell + 1, cell - 2, cell - 2);
    }
  }
  const depot = s.world.depot, charger = s.world.charger;
  ctx.fillStyle = "#2f9e8a";
  ctx.fillRect(ox + depot[0] * cell + 3, oy + depot[1] * cell + 3, cell - 6, cell - 6);
  ctx.fillStyle = "#6b8fd4";
  ctx.fillRect(ox + charger[0] * cell + 3, oy + charger[1] * cell + 3, cell - 6, cell - 6);
  (s.world.tasks || []).forEach((t) => {
    if (t.status === "DONE") return;
    ctx.fillStyle = "#1b1712";
    ctx.fillRect(ox + t.pick[0] * cell + cell * 0.35, oy + t.pick[1] * cell + cell * 0.35, cell * 0.3, cell * 0.3);
    ctx.strokeStyle = "#e0a106";
    ctx.strokeRect(ox + t.drop[0] * cell + 4, oy + t.drop[1] * cell + 4, cell - 8, cell - 8);
  });
  (s.robots || []).forEach((bot, i) => {
    ctx.strokeStyle = COLORS[i % COLORS.length];
    ctx.globalAlpha = 0.55;
    ctx.beginPath();
    (bot.path || []).forEach((p, idx) => {
      const px = ox + p[0] * cell + cell / 2;
      const py = oy + p[1] * cell + cell / 2;
      if (idx === 0) ctx.moveTo(px, py);
      else ctx.lineTo(px, py);
    });
    ctx.stroke();
    ctx.globalAlpha = 1;
    const x = bot.pos[0], y = bot.pos[1];
    ctx.fillStyle = COLORS[i % COLORS.length];
    ctx.beginPath();
    ctx.arc(ox + x * cell + cell / 2, oy + y * cell + cell / 2, cell * 0.32, 0, Math.PI * 2);
    ctx.fill();
    ctx.fillStyle = "#1b1712";
    ctx.font = `${Math.max(10, cell * 0.28)}px sans-serif`;
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText(bot.id, ox + x * cell + cell / 2, oy + y * cell + cell / 2);
  });
}

function render(s) {
  document.getElementById("tick").textContent = `t=${s.tick}`;
  document.getElementById("policy-label").textContent = s.policy === "ubpa" ? "UBPA" : "stop-and-wait";
  document.getElementById("btn-ubpa").classList.toggle("on", s.policy === "ubpa");
  document.getElementById("btn-sw").classList.toggle("on", s.policy === "stop_wait");
  const rs = s.radio_stats || {};
  const dropPct = Math.round((rs.drop_prob || 0) * 100);
  const delay = rs.delay == null ? 1 : rs.delay;
  const dropEl = document.getElementById("drop-slider");
  const delayEl = document.getElementById("delay-slider");
  if (document.activeElement !== dropEl) dropEl.value = String(dropPct);
  if (document.activeElement !== delayEl) delayEl.value = String(delay);
  document.getElementById("drop-label").textContent = dropPct + "%";
  document.getElementById("delay-label").textContent = delay + (delay === 1 ? " tick" : " ticks");
  document.getElementById("radio-stats").textContent =
    "delivered " + (rs.delivered || 0) + " · dropped " + (rs.dropped || 0);
  const box = document.getElementById("robots");
  box.innerHTML = (s.robots || []).map((b) => `
    <div class="robot">
      <strong>${b.id}</strong> · ${b.status} · task ${b.task || "—"} · UBPA ${b.ubpa}
      <div>battery ${b.battery.toFixed(1)}% · urgency ${b.urgency} · load ${b.workload}</div>
      <div class="bar"><i style="width:${Math.max(0, Math.min(100, b.battery))}%"></i></div>
    </div>`).join("");
  document.getElementById("radio").innerHTML = (s.radio || []).map((m) =>
    `<div>${m.tick} ${m.from_id} ${m.type || ""} ${m.task_id || ""} ${m.status || ""}</div>`
  ).join("");
  const lm = s.metrics || {};
  document.getElementById("live-metrics").innerHTML = metricRows({
    collisions: lm.collision_count,
    deadlocks: lm.deadlock_count,
    complete_tick: lm.all_tasks_complete_tick ?? "incomplete",
    mean_wait: fmt(lm.mean_wait_ticks),
    distance: fmt(lm.total_distance),
    comm_latency: fmt(lm.mean_comm_latency_ticks),
    step_ms: fmt(lm.mean_robot_step_ms),
    tasks: `${lm.tasks_done}/${lm.tasks_total}`,
  });
  const measured = s.measured;
  const el = document.getElementById("measured");
  if (!measured) {
    el.innerHTML = `<p class="missing">No results/metrics.json yet. Run <code>python scripts/run_experiments.py</code>.</p>`;
    return;
  }
  const experiments = measured.experiments || {};
  const ids = Object.keys(experiments);
  if (!ids.length) {
    el.innerHTML = `<p class="missing">metrics.json has no experiment summaries.</p>`;
    return;
  }
  el.innerHTML = ids.map((id) => measuredBlock(id, experiments[id])).join("");
}

function measuredBlock(id, exp) {
  const summary = (exp && exp.summary) || {};
  const b = summary.baseline || {};
  const u = summary.ubpa || {};
  const comparable = summary.comparable === true;
  const keys = [
    ["complete", "finished"],
    ["ticks", "ticks"],
    ["all_tasks_complete_tick", "complete_tick"],
    ["tasks_done", "tasks_done"],
    ["collision_count", "collisions"],
    ["deadlock_count", "deadlocks"],
    ["mean_wait_ticks", "mean_wait"],
    ["total_distance", "distance"],
  ];
  const rows = keys.map(([k, label]) => {
    return `<span>${label}</span><b>${fmtCell(b[k])} → ${fmtCell(u[k])}</b>`;
  }).join("");
  const flag = comparable ? "improvement % allowed" : "improvement n/a (baseline incomplete)";
  return `<div class="measured-exp"><h3>${id} · ${flag}</h3><div class="metrics">${rows}</div></div>`;
}

function fmtCell(v) {
  if (v == null || v === false) return v === false ? "no" : "incomplete";
  if (v === true) return "yes";
  if (typeof v === "number") return Number.isInteger(v) ? String(v) : Number(v).toFixed(3);
  return String(v);
}

function metricRows(obj) {
  return Object.entries(obj).map(([k, v]) => `<span>${k}</span><b>${v}</b>`).join("");
}
function fmt(v) {
  if (v == null || Number.isNaN(v)) return "—";
  return Number(v).toFixed(3);
}

setInterval(getState, 120);
getState();
