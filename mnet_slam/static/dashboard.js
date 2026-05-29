const state = {
  timer: null,
};

function $(id) {
  return document.getElementById(id);
}

function fmt(n, digits = 1) {
  return Number.isFinite(n) ? n.toFixed(digits) : "0";
}

async function loadSession() {
  const res = await fetch("/api/session");
  if (!res.ok) {
    throw new Error(await res.text());
  }
  return res.json();
}

function setMetrics(data) {
  const poses = data.trajectory || [];
  const ok = poses.filter((p) => p.tracking_ok).length;
  const meanInliers = poses.length
    ? poses.reduce((sum, p) => sum + (p.inliers || 0), 0) / poses.length
    : 0;
  $("sessionPath").textContent = data.session;
  $("framesCount").textContent = data.counts.frames;
  $("posesCount").textContent = data.counts.poses;
  $("edgesCount").textContent = data.counts.edges;
  $("loopsCount").textContent = data.edge_kinds.loop || 0;
  $("trackingOk").textContent = poses.length ? `${Math.round((ok / poses.length) * 100)}%` : "0%";
  $("meanInliers").textContent = fmt(meanInliers, 0);
  const kinds = Object.entries(data.edge_kinds).map(([k, v]) => `${k}: ${v}`).join("  ");
  $("edgeKinds").textContent = kinds || "No edges yet";
}

function clearCanvas(ctx, canvas) {
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.fillStyle = "#fbfcfe";
  ctx.fillRect(0, 0, canvas.width, canvas.height);
}

function drawGrid(ctx, canvas) {
  ctx.strokeStyle = "#e6ebf2";
  ctx.lineWidth = 1;
  for (let x = 40; x < canvas.width; x += 60) {
    ctx.beginPath();
    ctx.moveTo(x, 20);
    ctx.lineTo(x, canvas.height - 30);
    ctx.stroke();
  }
  for (let y = 20; y < canvas.height - 30; y += 60) {
    ctx.beginPath();
    ctx.moveTo(40, y);
    ctx.lineTo(canvas.width - 20, y);
    ctx.stroke();
  }
}

function drawTrajectory(poses) {
  const canvas = $("trajectoryCanvas");
  const ctx = canvas.getContext("2d");
  clearCanvas(ctx, canvas);
  drawGrid(ctx, canvas);
  if (!poses.length) return;
  const pts = poses.map((p) => ({ x: p.translation[0], z: p.translation[2], loop: p.loop_closed }));
  const xs = pts.map((p) => p.x);
  const zs = pts.map((p) => p.z);
  const minX = Math.min(...xs);
  const maxX = Math.max(...xs);
  const minZ = Math.min(...zs);
  const maxZ = Math.max(...zs);
  const pad = 50;
  const sx = (canvas.width - pad * 2) / Math.max(maxX - minX, 0.1);
  const sz = (canvas.height - pad * 2) / Math.max(maxZ - minZ, 0.1);
  const s = Math.min(sx, sz);
  const project = (p) => ({
    x: pad + (p.x - minX) * s,
    y: canvas.height - pad - (p.z - minZ) * s,
  });
  ctx.strokeStyle = "#0077b6";
  ctx.lineWidth = 2;
  ctx.beginPath();
  pts.forEach((p, i) => {
    const q = project(p);
    if (i === 0) ctx.moveTo(q.x, q.y);
    else ctx.lineTo(q.x, q.y);
  });
  ctx.stroke();
  pts.forEach((p, i) => {
    const q = project(p);
    ctx.fillStyle = i === 0 ? "#2a9d8f" : i === pts.length - 1 ? "#d97706" : p.loop ? "#c2410c" : "#17202a";
    ctx.beginPath();
    ctx.arc(q.x, q.y, p.loop ? 5 : 3, 0, Math.PI * 2);
    ctx.fill();
  });
}

function drawInliers(poses) {
  const canvas = $("inlierCanvas");
  const ctx = canvas.getContext("2d");
  clearCanvas(ctx, canvas);
  if (!poses.length) return;
  const values = poses.map((p) => p.inliers || 0);
  const maxV = Math.max(...values, 10);
  const pad = 28;
  const barW = Math.max(2, (canvas.width - pad * 2) / values.length);
  values.forEach((v, i) => {
    const h = (v / maxV) * (canvas.height - pad * 2);
    ctx.fillStyle = poses[i].tracking_ok ? "#2a9d8f" : "#c2410c";
    ctx.fillRect(pad + i * barW, canvas.height - pad - h, Math.max(1, barW - 1), h);
  });
}

function setRecent(rows) {
  $("recentRows").innerHTML = rows
    .slice()
    .reverse()
    .map(
      (row) => `<tr>
        <td>${row.frame_id ?? ""}</td>
        <td>${row.source_id ?? ""}</td>
        <td>${row.inliers}</td>
        <td>${fmt(row.latency_ms, 1)} ms</td>
        <td class="${row.tracking_ok ? "ok" : "lost"}">${row.tracking_ok ? "OK" : "LOST"}</td>
      </tr>`
    )
    .join("");
}

async function refresh() {
  try {
    const data = await loadSession();
    setMetrics(data);
    drawTrajectory(data.trajectory || []);
    drawInliers(data.trajectory || []);
    setRecent(data.recent || []);
  } catch (err) {
    $("sessionPath").textContent = `Dashboard error: ${err.message}`;
  }
}

$("refreshBtn").addEventListener("click", refresh);
$("autoRefresh").addEventListener("change", (event) => {
  if (state.timer) clearInterval(state.timer);
  state.timer = event.target.checked ? setInterval(refresh, 1500) : null;
});

refresh();
state.timer = setInterval(refresh, 1500);
