const API = "";
let token = localStorage.getItem("af_token") || "";
let biData = [];
let biVisuals = [];
let sessionStartedAt = Date.now();
let me = { user: "admin", role: "admin" };

const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];

function toast(msg, err = false) {
  const t = $("#toast");
  t.textContent = msg;
  t.className = "toast show" + (err ? " err" : "");
  setTimeout(() => t.classList.remove("show"), 3200);
}

async function api(path, opts = {}) {
  const headers = { "Content-Type": "application/json", ...(opts.headers || {}) };
  if (token) headers.Authorization = `Bearer ${token}`;
  const res = await fetch(API + path, { ...opts, headers });
  let data = null;
  try { data = await res.json(); } catch { data = null; }
  if (res.status === 401) {
    logout(false);
    throw new Error("نشست منقضی شد");
  }
  if (!res.ok) {
    let msg = res.statusText;
    if (data) {
      if (typeof data.detail === "string") msg = data.detail;
      else if (Array.isArray(data.detail)) msg = data.detail.map((x) => x.msg || JSON.stringify(x)).join(" | ");
      else if (data.message) msg = data.message;
      else if (data.detail) msg = JSON.stringify(data.detail);
    }
    throw new Error(msg);
  }
  return data;
}

function logout(redirect = true) {
  token = "";
  localStorage.removeItem("af_token");
  if (redirect) {
    $("#appView").classList.add("hidden");
    $("#loginView").classList.remove("hidden");
  }
}

async function doLogin() {
  try {
    const data = await api("/api/login", {
      method: "POST",
      body: JSON.stringify({
        username: $("#loginUser").value.trim(),
        password: $("#loginPass").value,
      }),
    });
    token = data.token;
    localStorage.setItem("af_token", token);
    $("#loginView").classList.add("hidden");
    $("#appView").classList.remove("hidden");
    sessionStartedAt = Date.now();
    me = { user: data.user || data.username || $("#loginUser").value.trim() || "admin", role: data.role || "admin" };
    showWelcomeSplash();
  } catch (e) {
    toast(e.message, true);
  }
}

function showPage(name) {
  $$(".page").forEach((p) => p.classList.add("hidden"));
  const page = $(`#page-${name}`);
  if (page) page.classList.remove("hidden");
  $$("#nav button[data-page]").forEach((b) => b.classList.toggle("active", b.dataset.page === name));
  const activeBtn = $(`#nav button[data-page="${name}"]`);
  if (activeBtn) {
    const group = activeBtn.closest(".nav-group");
    if (group) group.classList.remove("collapsed");
  }
  const loaders = {
    dashboard: loadDashboard,
    create: loadCreate,
    monitor: loadMonitor,
    ports: loadPorts,
    db: loadDb,
    keys: loadKeys,
    analytics: loadAnalytics,
    apimgmt: loadApiMgmt,
    archive: loadApiMgmt,
    testapi: loadTestApi,
    logs: loadLogsPage,
    alarms: loadAlarms,
    users: loadUsers,
    bale: loadBale,
  };
  if (loaders[name]) {
    try {
      const r = loaders[name]();
      if (r && typeof r.then === "function") r.catch((e) => toast(e.message || String(e), true));
    } catch (e) {
      toast(e.message || String(e), true);
    }
  }
}

/* Dashboard */
async function loadDashboard() {
  try {
    const s = await api("/api/summary");
    $("#dashStats").innerHTML = [
      ["کل سرویس‌ها", s.total_services],
      ["فعال", s.active],
      ["متوقف", s.stopped],
      ["درخواست‌ها", s.requests],
    ]
      .map(
        ([l, v]) =>
          `<div class="stat"><div class="lbl">${l}</div><div class="val">${v}</div></div>`
      )
      .join("");
    const list = await api("/api/services");
    $("#dashServices").innerHTML =
      list
        .slice(0, 8)
        .map(
          (x) => `
      <div class="service-card">
        <div class="top">
          <div>
            <div class="name">${x.name}</div>
            <div class="url">${x.url || "—"}</div>
          </div>
          <span class="badge ${x.active ? "badge-on" : "badge-off"}">${x.active ? "آنلاین" : "خاموش"}</span>
        </div>
      </div>`
        )
        .join("") || `<p class="muted">سرویسی نیست</p>`;
  } catch (e) {
    toast(e.message, true);
  }
}


/* Create */
let allTablesCache = [];
let joinState = [];

async function loadCreate() {
  try {
    const dbs = await api("/api/db-configs");
    const names = Object.keys(dbs || {});
    const sel = $("#crDb");
    if (!names.length) {
      sel.innerHTML = "";
      $("#crTable").innerHTML = "";
      $("#crFields").innerHTML = "";
      toast("ابتدا از تب «اتصال دیتابیس» یک منبع اضافه کنید", true);
      return;
    }
    sel.innerHTML = names.map((k) => `<option value="${k}">${k}</option>`).join("");
    await onDbChange();
    updatePreview();
  } catch (e) {
    toast("بارگذاری دیتابیس‌ها: " + e.message, true);
  }
}

async function onDbChange() {
  const label = $("#crDb").value;
  if (!label) return;
  try {
    const res = await api(`/api/db/meta?label=${encodeURIComponent(label)}`);
    allTablesCache = res.tables || [];
    if (!allTablesCache.length) {
      $("#crTable").innerHTML = "";
      $("#crFields").innerHTML = "";
      toast("هیچ جدولی در این دیتابیس پیدا نشد", true);
      return;
    }
    $("#crTable").innerHTML = allTablesCache.map((t) => `<option value="${t}">${t}</option>`).join("");
    renderJoinBoxes();
    await refreshFieldOptions();
  } catch (e) {
    toast("خواندن جداول: " + e.message, true);
    $("#crTable").innerHTML = "";
    $("#crFields").innerHTML = "";
  }
}

async function onTableChange() {
  try {
    renderJoinBoxes();
    await refreshFieldOptions();
  } catch (e) {
    toast(e.message, true);
  }
}

function renderJoinBoxes() {
  const n = Number($("#crJoinCount").value || 0);
  const main = $("#crTable").value;
  const box = $("#joinBoxes");
  box.innerHTML = "";
  joinState = joinState.slice(0, n);
  const used = new Set([main, ...joinState.map((j) => j.table).filter(Boolean)]);
  for (let i = 0; i < n; i++) {
    if (!joinState[i]) joinState[i] = { table: "", type: "INNER JOIN", left_col: "", right_col: "" };
    const available = allTablesCache.filter((t) => t === joinState[i].table || !used.has(t) || t === joinState[i].table);
    const div = document.createElement("div");
    div.className = "panel";
    div.style.background = "var(--panel2)";
    div.innerHTML = `
      <h3 style="font-size:.9rem">Join #${i + 1}</h3>
      <div class="grid-2">
        <label class="field"><span>جدول</span>
          <select data-ji="${i}" data-k="table">${available.map((t) => `<option value="${t}" ${joinState[i].table===t?"selected":""}>${t}</option>`).join("")}</select>
        </label>
        <label class="field"><span>نوع</span>
          <select data-ji="${i}" data-k="type">
            <option value="INNER JOIN" ${joinState[i].type==="INNER JOIN"?"selected":""}>INNER JOIN</option>
            <option value="LEFT JOIN" ${joinState[i].type==="LEFT JOIN"?"selected":""}>LEFT JOIN</option>
          </select>
        </label>
        <label class="field"><span>کلید جدول اصلی (${main})</span>
          <select data-ji="${i}" data-k="left_col" id="joinLeft_${i}"></select>
        </label>
        <label class="field"><span>کلید جدول Join</span>
          <select data-ji="${i}" data-k="right_col" id="joinRight_${i}"></select>
        </label>
      </div>`;
    box.appendChild(div);
    if (!joinState[i].table && available.length) joinState[i].table = available[0];
    used.add(joinState[i].table);
    fillJoinCols(i);
  }
  box.onchange = async (e) => {
    const el = e.target.closest("[data-ji]");
    if (!el) return;
    const i = Number(el.dataset.ji);
    const k = el.dataset.k;
    joinState[i][k] = el.value;
    if (k === "table") {
      renderJoinBoxes();
      await refreshFieldOptions();
    } else if (k === "left_col" || k === "right_col") {
      // ok
    }
  };
}

async function fillJoinCols(i) {
  const label = $("#crDb").value;
  const main = $("#crTable").value;
  const jt = joinState[i]?.table;
  if (!label || !main) return;
  try {
    const mainCols = (await api(`/api/db/meta?label=${encodeURIComponent(label)}&table=${encodeURIComponent(main)}`)).columns || [];
    const left = $(`#joinLeft_${i}`);
    if (left) {
      left.innerHTML = mainCols.map((c) => `<option value="${c}" ${joinState[i].left_col===c?"selected":""}>${c}</option>`).join("");
      if (!joinState[i].left_col && mainCols[0]) joinState[i].left_col = mainCols[0];
    }
    if (jt) {
      const joinCols = (await api(`/api/db/meta?label=${encodeURIComponent(label)}&table=${encodeURIComponent(jt)}`)).columns || [];
      const right = $(`#joinRight_${i}`);
      if (right) {
        right.innerHTML = joinCols.map((c) => `<option value="${c}" ${joinState[i].right_col===c?"selected":""}>${c}</option>`).join("");
        if (!joinState[i].right_col && joinCols[0]) joinState[i].right_col = joinCols[0];
      }
    }
  } catch (e) {
    toast(e.message, true);
  }
}

async function refreshFieldOptions() {
  const label = $("#crDb").value;
  const main = $("#crTable").value;
  if (!label || !main) return;
  const tables = [main, ...joinState.map((j) => j.table).filter(Boolean)];
  const opts = [];
  const errors = [];
  for (const tb of tables) {
    try {
      const res = await api(`/api/db/meta?label=${encodeURIComponent(label)}&table=${encodeURIComponent(tb)}`);
      (res.columns || []).forEach((c) => opts.push(`${tb}.${c}`));
    } catch (e) {
      errors.push(`${tb}: ${e.message}`);
    }
  }
  if (!opts.length) {
    $("#crFields").innerHTML = "";
    toast(errors.join(" | ") || "ستونی پیدا نشد", true);
    return;
  }
  $("#crFields").innerHTML = opts.map((o) => `<option value="${o}" selected>${o}</option>`).join("");
  $("#crFilter").innerHTML = [`<option>بدون فیلتر</option>`, ...opts.map((o) => `<option>${o}</option>`)].join("");
  $("#crTime").innerHTML = [`<option>غیرفعال</option>`, ...opts.map((o) => `<option>${o}</option>`)].join("");
  updatePreview();
}

function updatePreview() {
  const route = ($("#crRoute")?.value || "/api/data").trim();
  const parts = [];
  const ff = $("#crFilter")?.value;
  if (ff && ff !== "بدون فیلتر") {
    const p = ff.includes(".") ? ff.replace(".", "_") : ff;
    parts.push(`${p}=VALUE`);
  }
  if ($("#crTime")?.value && $("#crTime").value !== "غیرفعال") {
    parts.push("start=YYYY-MM-DD&end=YYYY-MM-DD");
  }
  parts.push(`limit=${$("#crLimit")?.value || 100}`);
  const q = parts.join("&");
  const el = $("#crPreview");
  if (el) el.textContent = `GET http://HOST:PORT${route}${q ? "?" + q : ""}`;
}

async function createService() {
  const fields = [...$("#crFields").selectedOptions].map((o) => o.value);
  // sync join cols from DOM
  $$("#joinBoxes [data-ji]").forEach((el) => {
    const i = Number(el.dataset.ji);
    joinState[i][el.dataset.k] = el.value;
  });
  const joins = joinState
    .filter((j) => j.table)
    .map((j) => ({
      table: j.table,
      type: j.type || "INNER JOIN",
      left_col: j.left_col,
      right_col: j.right_col,
    }));
  try {
    const res = await api("/api/services/create", {
      method: "POST",
      body: JSON.stringify({
        db_label: $("#crDb").value,
        main_table: $("#crTable").value,
        joins,
        fields,
        filter_field: $("#crFilter").value,
        time_field: $("#crTime").value,
        use_pagination: true,
        default_limit: Number($("#crLimit").value) || 100,
        default_offset: 0,
        require_auth: $("#crAuth").checked,
        name: $("#crName").value.trim(),
        route: $("#crRoute").value.trim() || "/api/data",
      }),
    });
    toast(res.message || "ساخته شد · پورت " + res.port);
    showPage("monitor");
  } catch (e) {
    toast(e.message, true);
  }
}

async function createManual() {
  try {
    const res = await api("/api/services/create-manual", {
      method: "POST",
      body: JSON.stringify({
        name: $("#manName").value.trim(),
        route_example: $("#manRoute").value.trim(),
        code: $("#manCode").value,
      }),
    });
    toast(res.message || "سرویس دستی ساخته شد");
    showPage("monitor");
  } catch (e) {
    toast(e.message, true);
  }
}

function switchCreateTab(mode) {
  const wiz = mode === "wizard";
  $("#wizardBox").classList.toggle("hidden", !wiz);
  $("#manualBox").classList.toggle("hidden", wiz);
  $("#tabWizard").className = "btn " + (wiz ? "btn-primary" : "btn-ghost");
  $("#tabManual").className = "btn " + (!wiz ? "btn-primary" : "btn-ghost");
}

/* Monitor */
async function loadMonitor() {
  try {
    const list = await api("/api/services");
    if (!list.length) {
      $("#monitorList").innerHTML = `<div class="panel"><p class="muted">سرویسی ثبت نشده</p></div>`;
      return;
    }
    $("#monitorList").innerHTML = `
      <div class="panel" style="overflow:auto">
        <h3><span class="dot"></span> Services status</h3>
        <table class="svc-table">
          <thead><tr><th>name</th><th>status</th><th>port</th><th>actions</th></tr></thead>
          <tbody>
            ${list.map((x) => `
              <tr>
                <td><b>${x.name}</b></td>
                <td><span class="badge ${x.active ? "badge-on" : "badge-off"}">${x.active ? "online" : "stopped"}</span></td>
                <td class="mono">${x.port || "—"}</td>
                <td class="row-actions">
                  <button class="btn btn-primary btn-sm" data-act="start" data-name="${x.name}">فعال</button>
                  <button class="btn btn-ghost btn-sm" data-act="stop" data-name="${x.name}">غیرفعال</button>
                </td>
              </tr>`).join("")}
          </tbody>
        </table>
      </div>`;
  } catch (e) {
    toast(e.message, true);
  }
}

$("#monitorList")?.addEventListener("click", async (e) => {
  const btn = e.target.closest("button[data-act]");
  if (!btn) return;
  const name = btn.dataset.name;
  const act = btn.dataset.act;
  try {
    if (act === "start") {
      await api(`/api/services/${encodeURIComponent(name)}/start`, { method: "POST" });
      toast("اجرا شد");
      loadMonitor();
    } else if (act === "stop") {
      await api(`/api/services/${encodeURIComponent(name)}/stop`, { method: "POST" });
      toast("متوقف شد");
      loadMonitor();
    }
  } catch (err) {
    toast(err.message, true);
  }
});

/* Ports */
async function loadPorts() {
  try {
    const [data, services] = await Promise.all([api("/api/ports"), api("/api/services")]);
    const host = document.getElementById("page-ports");
    if (host && !document.getElementById("portChangePanel")) {
      const panel = document.createElement("div");
      panel.className = "panel";
      panel.id = "portChangePanel";
      panel.innerHTML = `
        <h3><span class="dot"></span> تغییر پورت سرویس</h3>
        <div class="grid-3">
          <label class="field"><span>سرویس</span>
            <select id="pcSvc"></select>
          </label>
          <label class="field"><span>پورت جدید</span><input id="pcPort" type="number" placeholder="8502" /></label>
          <label class="field"><span>رمز تغییر پورت</span><input id="pcPass" type="password" /></label>
        </div>
        <button class="btn btn-primary" id="pcApply" style="margin-top:10px">اعمال پورت</button>`;
      host.appendChild(panel);
      document.getElementById("pcApply").onclick = async () => {
        try {
          await api(`/api/services/${encodeURIComponent($("#pcSvc").value)}/port`, {
            method: "POST",
            body: JSON.stringify({ port: Number($("#pcPort").value), password: $("#pcPass").value }),
          });
          toast("پورت تغییر کرد");
          loadPorts();
        } catch (e) { toast(e.message, true); }
      };
    }
    const sel = document.getElementById("pcSvc");
    if (sel) {
      sel.innerHTML = services.map((s) => `<option value="${s.name}">${s.name} · ${s.port || "—"}</option>`).join("");
    }
    const body = document.getElementById("portsBody");
    if (body) {
      body.innerHTML = (data.rows || []).map((r) => {
        const busy = r.service || r.pid;
        return `<tr class="${busy ? "port-row-busy" : "port-row-free"}">
          <td class="mono"><span class="port-pill ${busy ? "busy" : "free"}">${r.port}</span></td>
          <td>${r.status || "—"}</td>
          <td class="mono">${r.pid || "—"}</td>
          <td>${r.process || "—"}</td>
          <td>${r.service || "—"}</td>
        </tr>`;
      }).join("") || `<tr><td colspan="5" class="muted">خالی</td></tr>`;
    }
    const free = document.getElementById("freePorts");
    if (free) {
      free.innerHTML = (data.free || []).map((p) => `<span class="chip num chip-free">${p}</span>`).join("") || "—";
    }
  } catch (e) {
    toast(e.message, true);
  }
}

/* DB */
async function loadDb() {
  try {
    const dbs = await api("/api/db-configs");
    $("#dbList").innerHTML =
      Object.entries(dbs)
        .map(
          ([name, info]) => `
      <div class="service-card">
        <div class="top">
          <div>
            <div class="name">${name}</div>
            <div class="url">${info.db_type || "mysql"} · ${info.host}:${info.port} · ${info.database} · ${info.user}</div>
          </div>
          <button class="btn btn-danger btn-sm" data-deldb="${name}">حذف</button>
        </div>
      </div>`
        )
        .join("") || `<p class="muted">موردی نیست</p>`;
  } catch (e) {
    toast(e.message, true);
  }
}

$("#dbList")?.addEventListener("click", async (e) => {
  const b = e.target.closest("[data-deldb]");
  if (!b) return;
  try {
    await api(`/api/db-configs/${encodeURIComponent(b.dataset.deldb)}`, { method: "DELETE" });
    toast("حذف شد");
    loadDb();
  } catch (err) {
    toast(err.message, true);
  }
});

$("#dbType")?.addEventListener("change", () => {
  const pg = $("#dbType").value === "postgres";
  $("#dbPort").value = pg ? 5432 : 3306;
  $("#dbUser").value = pg ? "postgres" : "root";
});

async function saveDb() {
  try {
    await api("/api/db-configs", {
      method: "POST",
      body: JSON.stringify({
        label: $("#dbLabel").value.trim(),
        db_type: $("#dbType").value,
        host: $("#dbHost").value.trim(),
        port: Number($("#dbPort").value),
        user: $("#dbUser").value.trim(),
        password: $("#dbPass").value,
        database: $("#dbName").value.trim(),
      }),
    });
    toast("ذخیره و تست موفق");
    loadDb();
  } catch (e) {
    toast(e.message, true);
  }
}

/* Keys */
async function loadKeys() {
  try {
    const keys = await api("/api/keys");
    let html = "";
    for (const [svc, map] of Object.entries(keys)) {
      html += `<div class="service-card"><div class="name">${svc}</div>`;
      for (const [kn, kv] of Object.entries(map)) {
        html += `<div class="url" style="margin-top:6px">${kn}: <span class="mono">${kv}</span>
          <button class="btn btn-danger btn-sm" data-delsvc="${svc}" data-delkey="${kn}">حذف</button></div>`;
      }
      html += `</div>`;
    }
    $("#keyList").innerHTML = html || `<p class="muted">کلیدی نیست</p>`;
  } catch (e) {
    toast(e.message, true);
  }
}

$("#keyList")?.addEventListener("click", async (e) => {
  const b = e.target.closest("[data-delkey]");
  if (!b) return;
  try {
    await api(
      `/api/keys/${encodeURIComponent(b.dataset.delsvc)}/${encodeURIComponent(b.dataset.delkey)}`,
      { method: "DELETE" }
    );
    loadKeys();
  } catch (err) {
    toast(err.message, true);
  }
});

async function addKey() {
  try {
    const res = await api("/api/keys", {
      method: "POST",
      body: JSON.stringify({
        service: $("#keySvc").value.trim(),
        key_name: $("#keyName").value.trim(),
      }),
    });
    toast("کلید: " + res.key);
    loadKeys();
  } catch (e) {
    toast(e.message, true);
  }
}

/* Analytics */
async function loadAnalytics() {
  try {
    const [summary, rows] = await Promise.all([
      api("/api/analytics/summary").catch(() => ({ totals: {}, by_service: [], by_status: [], timeline: [] })),
      api("/api/analytics").catch(() => []),
    ]);
    const page = document.getElementById("page-analytics");
    if (!page) return;
    let charts = document.getElementById("analyticsCharts");
    if (!charts) {
      charts = document.createElement("div");
      charts.id = "analyticsCharts";
      const hero = page.querySelector(".hero");
      if (hero) hero.after(charts);
      else page.prepend(charts);
    }
    const t = summary.totals || {};
    let bys = summary.by_service || [];
    let st = summary.by_status || [];
    let tl = summary.timeline || [];
    // demo fallback so charts always render
    if (!bys.length) bys = [{ service: "demo-api", count: 12, ok: 11, fail: 1, avg_ms: 42 }];
    if (!st.length) st = [{ status: 200, count: 11 }, { status: 500, count: 1 }];
    if (!tl.length) {
      const now = new Date();
      tl = Array.from({ length: 8 }, (_, i) => {
        const d = new Date(now.getTime() - (7 - i) * 3600000);
        return { hour: d.toISOString().slice(0, 13), count: 3 + (i % 4), avg_ms: 30 + i * 5 };
      });
    }
    charts.innerHTML = `
      <div class="stats">
        <div class="stat accent-blue"><div class="lbl">Requests</div><div class="val">${t.requests ?? bys.reduce((s,x)=>s+x.count,0)}</div></div>
        <div class="stat accent-green"><div class="lbl">Success</div><div class="val">${t.success ?? "—"}</div></div>
        <div class="stat accent-red"><div class="lbl">Failed</div><div class="val">${t.fail ?? "—"}</div></div>
        <div class="stat accent-purple"><div class="lbl">Avg latency</div><div class="val">${t.avg_ms ?? "—"}</div></div>
      </div>
      <div class="grid-2" style="margin-top:12px">
        <div class="panel"><h3><span class="dot"></span> By service</h3><div id="chartSvc" style="height:280px;width:100%"></div></div>
        <div class="panel"><h3><span class="dot"></span> Status codes</h3><div id="chartStatus" style="height:280px;width:100%"></div></div>
      </div>
      <div class="panel" style="margin-top:12px"><h3><span class="dot"></span> Timeline</h3><div id="chartTime" style="height:280px;width:100%"></div></div>
      <div class="panel" style="margin-top:12px"><h3><span class="dot"></span> Per-service</h3>
        <div class="table-wrap"><table class="svc-table"><thead><tr>
          <th>Service</th><th>Count</th><th>OK</th><th>Fail</th><th>Avg ms</th>
        </tr></thead><tbody>
          ${bys.map((r) => `<tr><td>${r.service}</td><td>${r.count}</td><td style="color:#6ee7b7">${r.ok??"—"}</td><td style="color:#fca5a5">${r.fail??"—"}</td><td class="mono">${r.avg_ms??"—"}</td></tr>`).join("")}
        </tbody></table></div>
      </div>`;

    const paint = () => {
      if (!window.Plotly) {
        document.getElementById("chartSvc").innerHTML = `<p class="muted">Plotly لود نشد — CDN را چک کنید</p>`;
        return;
      }
      const dark = {
        paper_bgcolor: "rgba(0,0,0,0)", plot_bgcolor: "rgba(0,0,0,0)",
        font: { color: "#cbd5e1", family: "Estedad, Tahoma, sans-serif" },
        margin: { t: 24, b: 48, l: 48, r: 16 },
      };
      Plotly.newPlot("chartSvc", [{
        type: "bar", x: bys.map((x) => x.service), y: bys.map((x) => x.count),
        marker: { color: bys.map((_, i) => ["#818cf8","#38bdf8","#34d399","#fbbf24","#f472b6"][i % 5]) },
      }], { ...dark, height: 280 }, { displayModeBar: false, responsive: true });
      Plotly.newPlot("chartStatus", [{
        type: "pie", labels: st.map((x) => String(x.status)), values: st.map((x) => x.count),
        marker: { colors: ["#34d399","#fbbf24","#f87171","#818cf8","#38bdf8"] },
        textinfo: "label+percent",
      }], { ...dark, height: 280, showlegend: true }, { displayModeBar: false, responsive: true });
      Plotly.newPlot("chartTime", [
        { type: "scatter", mode: "lines+markers", x: tl.map((x) => x.hour), y: tl.map((x) => x.count), line: { color: "#a78bfa", width: 3 }, name: "requests" },
        { type: "scatter", mode: "lines", x: tl.map((x) => x.hour), y: tl.map((x) => x.avg_ms), yaxis: "y2", line: { color: "#fbbf24", width: 2, dash: "dot" }, name: "avg ms" },
      ], { ...dark, height: 280, yaxis2: { overlaying: "y", side: "right", showgrid: false }, legend: { orientation: "h" } },
      { displayModeBar: false, responsive: true });
      setTimeout(() => {
        ["chartSvc","chartStatus","chartTime"].forEach((id) => {
          try { Plotly.Plots.resize(id); } catch {}
        });
      }, 120);
    };
    // wait for layout visible
    setTimeout(paint, 50);

    const tbody = document.getElementById("analyticsBody");
    if (tbody && Array.isArray(rows)) {
      tbody.innerHTML = rows.slice(0, 100).map((r) => `<tr>
        <td class="mono">${r.ts || r.time || ""}</td><td>${r.service || ""}</td>
        <td class="mono">${r.endpoint || r.path || ""}</td><td>${r.status || ""}</td>
        <td>${r.duration_ms || r.ms || ""}</td><td>${r.size || ""}</td>
      </tr>`).join("") || `<tr><td colspan="6" class="muted">خالی</td></tr>`;
    }
  } catch (e) {
    toast(e.message, true);
  }
}


/* BI */
async function loadBi() {
  try {
    const list = await api("/api/services");
    $("#biSvc").innerHTML = list
      .map((x) => `<option value="${x.url || ""}" data-name="${x.name}">${x.name}</option>`)
      .join("");
  } catch (e) {
    toast(e.message, true);
  }
}

let biPick = "x"; // next chip click assigns X then Y

async function biLoad() {
  const url = $("#biSvc").value;
  if (!url) return toast("URL سرویس خالی است — در مانیتورینگ آدرس سرویس را چک کنید", true);
  try {
    const res = await api(`/api/proxy-fetch?url=${encodeURIComponent(url)}&api_key=${encodeURIComponent($("#biKey").value)}`);
    let data = res.data;
    if (typeof data === "string") {
      try { data = JSON.parse(data); } catch (_) {}
    }
    if (data && typeof data === "object" && !Array.isArray(data) && data.error) {
      return toast(String(data.error), true);
    }
    biData = Array.isArray(data) ? data : data && typeof data === "object" ? [data] : [];
    if (!biData.length) return toast("داده‌ای نیامد", true);
    const cols = Object.keys(biData[0] || {});
    const meta = $("#biMeta");
    if (meta) meta.textContent = `${biData.length.toLocaleString("fa-IR")} ردیف · ${cols.length} فیلد`;
    $("#biFields").innerHTML = cols.map((c) => `<span class="chip" data-col="${c}">${c}</span>`).join("");
    $("#biX").innerHTML = cols.map((c) => `<option value="${c}">${c}</option>`).join("");
    $("#biY").innerHTML = cols.map((c) => `<option value="${c}">${c}</option>`).join("");
    if (cols[0]) $("#biX").value = cols[0];
    if (cols[1]) $("#biY").value = cols[1];
    else if (cols[0]) $("#biY").value = cols[0];
    biPick = "x";
    toast(`${biData.length} ردیف بارگذاری شد`);
  } catch (e) {
    toast(e.message, true);
  }
}

function biFieldClick(e) {
  const chip = e.target.closest(".chip[data-col]");
  if (!chip) return;
  const col = chip.dataset.col;
  if (biPick === "x") {
    $("#biX").value = col;
    biPick = "y";
  } else {
    $("#biY").value = col;
    biPick = "x";
  }
  $$("#biFields .chip").forEach((c) => {
    c.classList.toggle("active-x", c.dataset.col === $("#biX").value);
    c.classList.toggle("active-y", c.dataset.col === $("#biY").value);
  });
}

function biAdd() {
  if (!biData.length) return toast("اول داده را بارگذاری کنید", true);
  const type = $("#biType").value;
  const x = $("#biX").value;
  const y = $("#biY").value;
  const title = $("#biTitle").value || type;
  const id = "v_" + Math.random().toString(36).slice(2, 8);
  biVisuals.push({ id, type, x, y, title });
  renderBi();
}

function renderBi() {
  const box = $("#biCanvas");
  box.innerHTML = "";
  if (!biVisuals.length) {
    box.innerHTML = `<p class="muted" style="padding:24px;text-align:center">هنوز ویژوالی اضافه نشده</p>`;
    return;
  }
  biVisuals.forEach((v) => {
    const div = document.createElement("div");
    div.className = "bi-chart-card";
    div.innerHTML = `<div style="display:flex;justify-content:space-between;margin-bottom:8px;align-items:center">
      <strong>${v.title}</strong>
      <button class="btn btn-danger btn-sm" data-rm="${v.id}">حذف</button></div>
      <div id="${v.id}" style="height:300px;width:100%"></div>`;
    box.appendChild(div);
    const xs = biData.map((r) => r[v.x]);
    const ys = biData.map((r) => r[v.y]);
    let trace = {};
    if (v.type === "bar") trace = { type: "bar", x: xs, y: ys, marker: { color: "#8b5cf6" } };
    else if (v.type === "line") trace = { type: "scatter", mode: "lines+markers", x: xs, y: ys, line: { color: "#a78bfa" } };
    else if (v.type === "scatter") trace = { type: "scatter", mode: "markers", x: xs, y: ys, marker: { color: "#e0b84a" } };
    else if (v.type === "pie") trace = { type: "pie", labels: xs, values: ys, hole: 0.35 };
    if (!window.Plotly) {
      div.querySelector("#"+v.id)?.insertAdjacentHTML("beforeend", "<p class=muted>Plotly در دسترس نیست</p>");
      return;
    }
    const layout = {
      margin: { t: 20, r: 10, b: 40, l: 40 },
      paper_bgcolor: "rgba(0,0,0,0)",
      plot_bgcolor: "rgba(0,0,0,0)",
      font: { color: "#c7d2e5", family: "Estedad, Tahoma, sans-serif" },
      height: 300,
    };
    Plotly.newPlot(v.id, [trace], layout, { displayModeBar: false, responsive: true }).then(() => {
      try { Plotly.Plots.resize(v.id); } catch {}
    });
  });
  box.onclick = (e) => {
    const b = e.target.closest("[data-rm]");
    if (!b) return;
    biVisuals = biVisuals.filter((v) => v.id !== b.dataset.rm);
    renderBi();
  };
}


/* Archive */
async function loadApiMgmt() {
  const listEl = document.getElementById("apiMgmtList");
  const sel = document.getElementById("arSvc");
  if (!listEl) return;
  try {
    const list = await api("/api/services");
    if (sel) {
      sel.innerHTML = list.map((x) => `<option value="${x.name}" data-url="${x.url || ""}">${x.name}</option>`).join("") || `<option value="">—</option>`;
    }
    if (!list.length) {
      listEl.innerHTML = `<div class="panel"><p class="muted">هنوز وب‌سرویسی ساخته نشده</p></div>`;
      return;
    }
    listEl.innerHTML = list.map((x) => `
      <article class="api-card ${x.active ? "running" : "stopped"}">
        <div class="api-card-top">
          <div class="api-card-icon">⚡</div>
          <div>
            <div class="api-card-name">${x.name}</div>
            <div class="api-card-route mono">${x.url || "—"}</div>
          </div>
        </div>
        <div class="api-card-meta">
          <span class="badge ${x.active ? "badge-on" : "badge-off"}">${x.active ? "● Running" : "○ Stopped"}</span>
          <span class="chip">Port: ${x.port || "—"}</span>
        </div>
        <div class="api-card-actions">
          <button class="btn btn-ghost btn-sm" data-am-edit="${x.name}">✏️ Edit</button>
          <button class="btn btn-danger btn-sm" data-am-del="${x.name}">🗑 Delete</button>
        </div>
      </article>`).join("");

    listEl.querySelectorAll("[data-am-edit]").forEach((b) => {
      b.onclick = async () => {
        if (sel) sel.value = b.dataset.amEdit;
        document.getElementById("apiEditorPanel")?.scrollIntoView({ behavior: "smooth" });
        await arLoadCode();
      };
    });
    listEl.querySelectorAll("[data-am-del]").forEach((b) => {
      b.onclick = () => confirmDeleteApi(b.dataset.amDel);
    });
    if (sel && !sel.dataset.wired) {
      sel.dataset.wired = "1";
      sel.addEventListener("change", () => arLoadCode());
    }
  } catch (e) {
    listEl.innerHTML = `<p class="muted">${e.message}</p>`;
  }
}

function confirmDeleteApi(name) {
  const modal = document.getElementById("confirmModal");
  if (!modal) {
    if (confirm(`Delete "${name}"?`)) doDeleteApi(name);
    return;
  }
  document.getElementById("confirmTitle").textContent = `Delete "${name}"?`;
  document.getElementById("confirmMsg").textContent = "This action cannot be undone. سرویس و فایل مربوطه حذف می‌شود.";
  modal.classList.remove("hidden");
  modal.style.display = "grid";
  const ok = document.getElementById("confirmOk");
  ok.onclick = async () => {
    modal.classList.add("hidden");
    modal.style.display = "none";
    await doDeleteApi(name);
  };
  modal.querySelectorAll("[data-confirm-cancel]").forEach((el) => {
    el.onclick = () => { modal.classList.add("hidden"); modal.style.display = "none"; };
  });
}

async function doDeleteApi(name) {
  try {
    await api(`/api/services/${encodeURIComponent(name)}`, { method: "DELETE" });
    toast("حذف شد");
    loadApiMgmt();
    if (typeof loadMonitor === "function") loadMonitor();
  } catch (e) {
    toast(e.message, true);
  }
}

async function arLoadCode() {
  const name = document.getElementById("arSvc")?.value;
  if (!name) return;
  try {
    const res = await api(`/api/services/${encodeURIComponent(name)}/code`);
    const codeEl = document.getElementById("arCode");
    if (codeEl) codeEl.value = res.code || "";
    const opt = document.getElementById("arSvc")?.selectedOptions?.[0];
    const ep = document.getElementById("arEndpoint");
    if (ep) ep.value = opt?.dataset?.url || res.url || "";
  } catch (e) {
    toast(e.message, true);
  }
}

async function arSaveCode() {
  const name = document.getElementById("arSvc")?.value;
  if (!name) return toast("سرویس انتخاب نشده", true);
  try {
    await api(`/api/services/${encodeURIComponent(name)}/code`, {
      method: "PUT",
      body: JSON.stringify({ code: document.getElementById("arCode").value }),
    });
    toast("ذخیره و ری‌استارت شد");
    loadApiMgmt();
  } catch (e) {
    toast(e.message, true);
  }
}


/* Events */
$("#loginBtn").onclick = doLogin;
$("#loginPass").addEventListener("keydown", (e) => e.key === "Enter" && doLogin());
$("#logoutBtn").onclick = () => logout(true);

/* ===== Welcome / FAB / Help / About ===== */
function formatUptime(ms) {
  const s = Math.max(0, Math.floor(ms / 1000));
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60;
  if (h) return `${h}h ${m}m ${sec}s`;
  if (m) return `${m}m ${sec}s`;
  return `${sec}s`;
}

function showWelcomeSplash() {
  const ov = document.getElementById("welcomeOverlay");
  if (!ov) { showPage("dashboard"); return; }
  ov.classList.remove("hidden");
  ov.style.display = "grid";
  const fill = document.getElementById("welcomeBarFill");
  const st = document.getElementById("welcomeStatusText");
  const toastEl = document.getElementById("welcomeToast");
  const msgs = ["Initializing modules…", "Loading service registry…", "Warming analytics…", "Ready."];
  let p = 0;
  if (fill) fill.style.width = "0%";
  if (toastEl) { toastEl.classList.add("show"); setTimeout(() => toastEl.classList.remove("show"), 2500); }
  const timer = setInterval(() => {
    p += 5;
    if (fill) fill.style.width = Math.min(100, p) + "%";
    if (st) st.textContent = msgs[Math.min(msgs.length - 1, Math.floor(p / 28))];
    if (p >= 100) clearInterval(timer);
  }, 40);
  const enter = () => { ov.classList.add("hidden"); clearInterval(timer); showPage("dashboard"); };
  document.getElementById("welcomeEnter")?.addEventListener("click", enter, { once: true });
  document.querySelectorAll(".welcome-pill").forEach((b) => {
    b.onclick = () => { ov.classList.add("hidden"); clearInterval(timer); showPage(b.dataset.go || "dashboard"); };
  });
}

const AF_HELP = [
  { title: "۱) اتصال دیتابیس", body: "از Creating → Connect to Database کانکشن Postgres/SQL را ثبت کنید.", icon: "🗄️", color: "#38bdf8" },
  { title: "۲) ساخت API", body: "Create API با ویزارد Join یا کد دستی؛ پورت و کلید را مدیریت کنید.", icon: "🧩", color: "#a78bfa" },
  { title: "۳) مانیتورینگ", body: "لیست شبیه PM2، لاگ‌ها و آلارم واقعی HTTP 5xx را ببینید.", icon: "📡", color: "#34d399" },
];
let afHelpIndex = 0;
function renderAfHelp() {
  if (afHelpIndex < 0) afHelpIndex = 0;
  if (afHelpIndex >= AF_HELP.length) afHelpIndex = AF_HELP.length - 1;
  const s = AF_HELP[afHelpIndex];
  const box = document.getElementById("helpSteps");
  if (!box) return;
  box.innerHTML = `<div class="help-step-card" style="--accent:${s.color}"><div class="help-step-icon">${s.icon}</div><h3>${s.title}</h3><p>${s.body}</p><div class="help-step-num">${afHelpIndex + 1} / ${AF_HELP.length}</div></div>`;
  const dots = document.getElementById("helpDots");
  if (dots) {
    dots.innerHTML = AF_HELP.map((_, i) => `<button type="button" class="help-dot${i === afHelpIndex ? " on" : ""}" onclick="window.__afHelpGo(${i})"></button>`).join("");
  }
  const next = document.getElementById("helpNext");
  if (next) next.textContent = afHelpIndex >= AF_HELP.length - 1 ? "پایان" : "بعدی";
}
window.__afHelpPrev = function (ev) { if (ev) ev.stopPropagation(); afHelpIndex = Math.max(0, afHelpIndex - 1); renderAfHelp(); };
window.__afHelpNext = function (ev) {
  if (ev) ev.stopPropagation();
  if (afHelpIndex >= AF_HELP.length - 1) { closeAfHelp(); return; }
  afHelpIndex++; renderAfHelp();
};
window.__afHelpGo = function (i) { afHelpIndex = +i; renderAfHelp(); };

function openAfHelp() {
  afHelpIndex = 0;
  const m = document.getElementById("helpModal");
  if (!m) return;
  m.classList.remove("hidden");
  m.style.display = "grid";
  renderAfHelp();
}
function closeAfHelp() {
  const m = document.getElementById("helpModal");
  if (!m) return;
  m.classList.add("hidden");
  m.style.display = "none";
}
function openAfAbout() {
  document.getElementById("userPopover")?.classList.add("hidden");
  const m = document.getElementById("aboutModal");
  if (!m) return;
  m.classList.remove("hidden");
  m.style.display = "grid";
}
function closeAfAbout() {
  const m = document.getElementById("aboutModal");
  if (!m) return;
  m.classList.add("hidden");
  m.style.display = "none";
}
function toggleAfUser(ev) {
  if (ev) { ev.preventDefault(); ev.stopPropagation(); }
  const pop = document.getElementById("userPopover");
  if (!pop) return;
  if (pop.classList.contains("hidden")) {
    document.getElementById("userPopName").textContent = me?.user || "admin";
    document.getElementById("userPopRole").textContent = me?.role || "admin";
    document.getElementById("userPopUptime").textContent = formatUptime(Date.now() - sessionStartedAt);
    pop.classList.remove("hidden");
  } else pop.classList.add("hidden");
}
window.__afToggleFab = function () {
  const stack = document.getElementById("fabStack");
  if (!stack) return;
  stack.classList.toggle("is-closed");
  const items = document.getElementById("fabItems");
  if (items) {
    const closed = stack.classList.contains("is-closed");
    items.style.maxHeight = closed ? "0px" : "260px";
    items.style.opacity = closed ? "0" : "1";
    items.style.pointerEvents = closed ? "none" : "auto";
  }
};
window.__afOpenHelp = function () { try { openAfHelp(); } catch (e) { console.error(e); } };
window.__afCloseHelp = function () { try { closeAfHelp(); } catch (e) { console.error(e); } };
window.__afOpenAbout = function () { try { openAfAbout(); } catch (e) { console.error(e); } };
window.__afCloseAbout = function () { try { closeAfAbout(); } catch (e) { console.error(e); } };
window.__afToggleUser = function (ev) { try { toggleAfUser(ev); } catch (e) { console.error(e); } };

async function loadTestApi() {
  const el = document.getElementById("testApiPanel");
  if (!el) return;
  try {
    const list = await api("/api/services");
    if (!list.length) {
      el.innerHTML = `<div class="panel"><p class="muted">سرویسی نیست — اول یک API بسازید</p></div>`;
      return;
    }
    el.innerHTML = `<div class="api-card-grid">${list.map((x) => `
      <article class="api-card ${x.active ? "running" : "stopped"}">
        <div class="api-card-top">
          <div class="api-card-icon">🧪</div>
          <div>
            <div class="api-card-name">${x.name}</div>
            <div class="api-card-route mono">${x.url || "—"}</div>
          </div>
        </div>
        <div class="api-card-meta">
          <span class="badge ${x.active ? "badge-on" : "badge-off"}">${x.active ? "Running" : "Stopped"}</span>
          <span class="chip">Port ${x.port || "—"}</span>
        </div>

      </article>`).join("")}</div>`;
  } catch (e) {
    el.innerHTML = `<p class="muted">${e.message}</p>`;
  }
}

let _tmPayload = null;
let _tmView = "json";
let _tmUrl = "";
let _tmName = "";

function openTestModal(name, url) {
  _tmName = name;
  _tmUrl = url;
  _tmPayload = null;
  _tmView = "json";
  const modal = document.getElementById("testModal");
  if (!modal) return toast("مودال تست پیدا نشد", true);
  document.getElementById("tmTitle").textContent = name;
  document.getElementById("tmUrl").textContent = url || "URL ثبت نشده";
  document.getElementById("tmMeta").textContent = "آماده برای ارسال";
  document.getElementById("tmOut").innerHTML = `<p class="muted" style="text-align:center;padding:24px">روی Send Request بزنید</p>`;
  modal.classList.remove("hidden");
  modal.style.display = "grid";
  document.querySelectorAll(".tm-view").forEach((b) => b.classList.toggle("on", b.dataset.view === "json"));
}

function closeTestModal() {
  const modal = document.getElementById("testModal");
  if (!modal) return;
  modal.classList.add("hidden");
  modal.style.display = "none";
}

function prettyJsonHtml(obj) {
  const json = typeof obj === "string" ? obj : JSON.stringify(obj, null, 2);
  return json
    .replace(/&/g, "&amp;").replace(/</g, "&lt;")
    .replace(/("(\\u[a-zA-Z0-9]{4}|\\[^u]|[^\\"])*"(\s*:)?|\b(true|false|null)\b|-?\d+(?:\.\d*)?(?:[eE][+\-]?\d+)?)/g, (match) => {
      let cls = "jn";
      if (/^"/.test(match)) cls = /:$/.test(match) ? "jk" : "js";
      else if (/true|false/.test(match)) cls = "jb";
      else if (/null/.test(match)) cls = "jnull";
      return `<span class="${cls}">${match}</span>`;
    });
}

function renderTestOut() {
  const out = document.getElementById("tmOut");
  if (!out) return;
  if (_tmPayload == null) {
    out.innerHTML = `<p class="muted" style="text-align:center;padding:24px">داده‌ای نیست</p>`;
    return;
  }
  if (_tmView === "table") {
    let rows = [];
    const p = _tmPayload;
    if (Array.isArray(p)) rows = p;
    else if (p && typeof p === "object") {
      if (Array.isArray(p.data)) rows = p.data;
      else if (Array.isArray(p.rows)) rows = p.rows;
      else if (Array.isArray(p.results)) rows = p.results;
      else rows = [p];
    }
    if (!rows.length || typeof rows[0] !== "object") {
      out.innerHTML = `<pre class="json-view">${prettyJsonHtml(_tmPayload)}</pre>`;
      return;
    }
    const cols = Object.keys(rows[0]);
    out.innerHTML = `<div class="table-wrap tm-table"><table class="svc-table"><thead><tr>${cols.map((c)=>`<th>${c}</th>`).join("")}</tr></thead>
      <tbody>${rows.slice(0,300).map((r)=>`<tr>${cols.map((c)=>`<td>${r[c]==null?"":String(r[c])}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`;
  } else {
    out.innerHTML = `<pre class="json-view">${prettyJsonHtml(_tmPayload)}</pre>`;
  }
}

async function sendTestRequest() {
  if (!_tmUrl) return toast("URL خالی است", true);
  const meta = document.getElementById("tmMeta");
  const t0 = performance.now();
  meta.textContent = "در حال ارسال…";
  try {
    let payload = null, status = 0;
    try {
      const proxied = await api("/api/proxy-fetch?url=" + encodeURIComponent(_tmUrl));
      payload = proxied.data !== undefined ? proxied.data : proxied;
      status = proxied.status || 200;
    } catch {
      const r = await fetch(_tmUrl);
      status = r.status;
      const ct = r.headers.get("content-type") || "";
      payload = ct.includes("json") ? await r.json() : await r.text();
    }
    const ms = Math.round(performance.now() - t0);
    _tmPayload = payload;
    meta.innerHTML = `Status <b class="${status < 400 ? "ok" : "bad"}">${status}</b> · <b>${ms} ms</b>`;
    renderTestOut();
  } catch (e) {
    meta.textContent = "خطا";
    document.getElementById("tmOut").innerHTML = `<p style="color:#fca5a5">${e.message}</p>`;
  }
}


function renderAsTable(payload, status) {
  const head = `<div class="test-status">HTTP <b>${status || "—"}</b></div>`;
  let rows = [];
  if (payload && typeof payload === "object") {
    if (Array.isArray(payload)) rows = payload;
    else if (Array.isArray(payload.data)) rows = payload.data;
    else if (Array.isArray(payload.rows)) rows = payload.rows;
    else if (Array.isArray(payload.results)) rows = payload.results;
    else rows = [payload];
  } else {
    return head + `<pre class="log-pretty">${String(payload ?? "—")}</pre>`;
  }
  if (!rows.length) return head + `<p class="muted">داده خالی</p>`;
  const cols = Object.keys(rows[0] || {});
  return head + `<div class="table-wrap"><table class="svc-table"><thead><tr>${cols.map((c) => `<th>${c}</th>`).join("")}</tr></thead>
    <tbody>${rows.slice(0, 200).map((r) => `<tr>${cols.map((c) => `<td>${r[c] == null ? "" : String(r[c])}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`;
}

async function loadLogsPage() {
  const el = document.getElementById("logsPanel");
  if (!el) return;
  try {
    const list = await api("/api/services");
    if (!list.length) {
      el.innerHTML = `<p class="muted">سرویسی نیست</p>`;
      return;
    }
    el.innerHTML = list.map((x) => `
      <div class="log-acc" data-name="${x.name}">
        <button type="button" class="log-acc-head">
          <span class="log-acc-title">${x.name}</span>
          <span class="badge ${x.active ? "badge-on" : "badge-off"}">${x.active ? "online" : "stopped"}</span>
          <span class="log-acc-chev">▾</span>
        </button>
        <div class="log-acc-body hidden"><pre class="log-pretty">بارگذاری…</pre></div>
      </div>`).join("");
    el.querySelectorAll(".log-acc").forEach((acc) => {
      const head = acc.querySelector(".log-acc-head");
      const body = acc.querySelector(".log-acc-body");
      const pre = body.querySelector("pre");
      head.onclick = async () => {
        const wasOpen = !body.classList.contains("hidden");
        el.querySelectorAll(".log-acc-body").forEach((b) => b.classList.add("hidden"));
        el.querySelectorAll(".log-acc").forEach((a) => a.classList.remove("open"));
        if (wasOpen) return;
        body.classList.remove("hidden");
        acc.classList.add("open");
        try {
          const res = await api(`/api/services/${encodeURIComponent(acc.dataset.name)}/logs`);
          const text = res.logs || "—";
          pre.innerHTML = text.split("\n").map((ln) => {
            const esc = ln.replace(/&/g, "&amp;").replace(/</g, "&lt;");
            if (/HTTP\/\d\.\d["\s]+5\d\d|status[=:\s]+5\d\d|5\d\d\s+(Internal|Bad|Error)/i.test(ln))
              return `<span class="log-line-err">${esc}</span>`;
            if (/\b200\b|\bOK\b/i.test(ln)) return `<span class="log-line-ok">${esc}</span>`;
            return esc;
          }).join("\n");
        } catch (e) {
          pre.textContent = e.message;
        }
      };
    });
  } catch (e) {
    el.innerHTML = `<p class="muted">${e.message}</p>`;
  }
}

async function loadAlarms() {
  const el = document.getElementById("alarmsPanel");
  if (!el) return;
  el.innerHTML = `<p class="muted">در حال اسکن لاگ‌ها برای HTTP 5xx واقعی…</p>`;

  function extractTime(line) {
    // ISO / common log timestamps
    let m = line.match(/(\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?(?:Z|[+-]\d{2}:?\d{2})?)/);
    if (m) return m[1].replace("T", " ");
    m = line.match(/\[(\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}[^\]]*)\]/);
    if (m) return m[1];
    // werkzeug / apache style: [31/Aug/2026 12:30:45]
    m = line.match(/\[(\d{1,2}\/[A-Za-z]{3}\/\d{4}[ :]\d{2}:\d{2}:\d{2}[^\]]*)\]/);
    if (m) return m[1];
    // HH:MM:SS only
    m = line.match(/\b(\d{2}:\d{2}:\d{2})\b/);
    if (m) return m[1];
    return "—";
  }

  try {
    const list = await api("/api/services");
    const alarms = [];
    const re = /\b(?:HTTP\/\d\.\d["\s]+)(5\d\d)\b|\bstatus[=:\s"]+(5\d\d)\b|\b(5\d\d)\s+(?:Internal Server Error|Bad Gateway|Service Unavailable|Gateway Timeout)\b/gi;
    for (const svc of list) {
      try {
        const res = await api(`/api/services/${encodeURIComponent(svc.name)}/logs`);
        const logs = res.logs || "";
        for (const ln of logs.split("\n")) {
          re.lastIndex = 0;
          const m = re.exec(ln);
          if (m) {
            const code = m[1] || m[2] || m[3];
            alarms.push({
              service: svc.name,
              code,
              time: extractTime(ln),
              line: ln.trim().slice(0, 280),
            });
          }
        }
      } catch {}
    }
    if (!alarms.length) {
      el.innerHTML = `<div class="panel" style="border-color:rgba(52,211,153,.3)"><p style="color:#6ee7b7;font-weight:800;margin:0">✓ هیچ HTTP 5xx واقعی در لاگ‌ها پیدا نشد</p></div>`;
      return;
    }
    el.innerHTML = alarms.map((a) => `
      <div class="alarm-card">
        <div style="display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap;align-items:center">
          <b>${a.service}</b>
          <span class="code">HTTP ${a.code}</span>
        </div>
        <div class="alarm-time">🕒 ${a.time}</div>
        <div class="muted mono" style="margin-top:8px;font-size:.78rem">${a.line.replace(/</g, "&lt;")}</div>
      </div>`).join("");
  } catch (e) { el.innerHTML = `<p class="muted">${e.message}</p>`; }
}


async function loadUsers() {
  const el = document.getElementById("usersPanel");
  if (!el) return;
  try {
    const data = await api("/api/users");
    const users = data.users || [];
    el.innerHTML = `
      <div class="panel">
        <h3><span class="dot"></span> کاربران</h3>
        <div class="table-wrap"><table class="svc-table">
          <thead><tr><th>User</th><th>Role</th><th>Permissions</th><th></th></tr></thead>
          <tbody>${users.map((u) => `<tr>
            <td><b>${u.username}</b></td>
            <td><span class="chip">${u.role}</span></td>
            <td class="mono">${(u.permissions || []).join(", ") || "—"}</td>
            <td><button class="btn btn-danger btn-sm" data-deluser="${u.username}">حذف</button></td>
          </tr>`).join("")}</tbody>
        </table></div>
      </div>
      <div class="panel" style="margin-top:12px">
        <h3><span class="dot"></span> کاربر جدید</h3>
        <div class="grid-2">
          <label class="field"><span>Username</span><input id="nuUser" /></label>
          <label class="field"><span>Password</span><input id="nuPass" type="password" /></label>
          <label class="field"><span>Role</span>
            <select id="nuRole">
              <option value="admin">admin</option>
              <option value="editor">editor</option>
              <option value="viewer" selected>viewer</option>
            </select>
          </label>
          <label class="field"><span>Permissions</span>
            <select id="nuPerm" multiple size="4">
              <option value="*">* all</option>
              <option value="create">create</option>
              <option value="monitor">monitor</option>
              <option value="ports">ports</option>
              <option value="bi">bi</option>
            </select>
          </label>
        </div>
        <button class="btn btn-primary" id="nuAdd">ایجاد کاربر</button>
      </div>`;
    document.getElementById("nuAdd").onclick = async () => {
      const perms = [...document.getElementById("nuPerm").selectedOptions].map((o) => o.value);
      try {
        await api("/api/users", {
          method: "POST",
          body: JSON.stringify({
            username: $("#nuUser").value.trim(),
            password: $("#nuPass").value,
            role: $("#nuRole").value,
            permissions: perms.length ? perms : ["viewer"],
          }),
        });
        toast("کاربر ساخته شد");
        loadUsers();
      } catch (e) { toast(e.message, true); }
    };
    el.querySelectorAll("[data-deluser]").forEach((b) => {
      b.onclick = async () => {
        if (!confirm("حذف؟")) return;
        try {
          await api(`/api/users/${encodeURIComponent(b.dataset.deluser)}`, { method: "DELETE" });
          loadUsers();
        } catch (e) { toast(e.message, true); }
      };
    });
  } catch (e) {
    el.innerHTML = `<p class="muted">${e.message}</p>`;
  }
}


async function loadBale() {
  try {
    const cfg = await api("/api/bale/config");
    const en = document.getElementById("baleEnabled");
    const tok = document.getElementById("baleToken");
    const chat = document.getElementById("baleChat");
    const na = document.getElementById("baleNotifyAlarms");
    const nd = document.getElementById("baleNotifyDown");
    const st = document.getElementById("baleStatus");
    if (en) en.checked = !!cfg.enabled;
    if (chat) chat.value = cfg.default_chat_id || "";
    if (na) na.checked = cfg.notify_alarms !== false;
    if (nd) nd.checked = cfg.notify_service_down !== false;
    if (tok) tok.placeholder = cfg.token_set ? (cfg.token_masked || "توکن ذخیره شده") : "توکن ربات";
    if (st) st.textContent = cfg.token_set ? ("توکن: " + (cfg.token_masked || "ست شده") + (cfg.enabled ? " · فعال" : " · غیرفعال")) : "هنوز توکنی ذخیره نشده";
    const pol = document.getElementById("balePolling");
    if (pol) pol.checked = cfg.polling !== false;
    const wh = document.getElementById("baleWebhookUrl");
    if (wh) wh.textContent = location.origin + "/api/bale/webhook";
    try {
      const ps = await api("/api/bale/polling/status");
      const info = document.getElementById("balePollInfo");
      if (info) info.textContent = ps.running ? ("گوش‌دادن فعال است (offset=" + (ps.offset || 0) + ") — الان /help را در بله بزنید") : "گوش‌دادن خاموش است — «شروع گوش‌دادن» را بزنید";
    } catch {}
  } catch (e) {
    toast(e.message, true);
  }
}

async function baleSave() {
  try {
    await api("/api/bale/config", {
      method: "POST",
      body: JSON.stringify({
        enabled: !!document.getElementById("baleEnabled")?.checked,
        token: document.getElementById("baleToken")?.value || "",
        default_chat_id: document.getElementById("baleChat")?.value || "",
        notify_alarms: !!document.getElementById("baleNotifyAlarms")?.checked,
        notify_service_down: !!document.getElementById("baleNotifyDown")?.checked,
        allowed_chat_ids: [],
        polling: !!document.getElementById("balePolling")?.checked,
        panel_url: "",
      }),
    });
    toast("ذخیره شد");
    const tok = document.getElementById("baleToken");
    if (tok) tok.value = "";
    if (document.getElementById("baleEnabled")?.checked && document.getElementById("balePolling")?.checked) {
      try { await api("/api/bale/polling/start", { method: "POST", body: "{}" }); } catch {}
    }
    loadBale();
  } catch (e) { toast(e.message, true); }
}

async function baleVerify() {
  try {
    const res = await api("/api/bale/verify", { method: "POST", body: "{}" });
    const bot = res.bot || {};
    toast("ربات: @" + (bot.username || bot.first_name || "ok"));
    document.getElementById("baleStatus").textContent = "✓ متصل: " + JSON.stringify(bot);
  } catch (e) { toast(e.message, true); }
}

async function baleTestMsg() {
  try {
    await api("/api/bale/test", {
      method: "POST",
      body: JSON.stringify({
        chat_id: document.getElementById("baleChat")?.value || "",
        text: "سلام از API Factory 🚀\\nاتصال ربات بله برقرار است.",
      }),
    });
    toast("پیام تست ارسال شد");
  } catch (e) { toast(e.message, true); }
}

async function balePushAlarms() {
  try {
    const res = await api("/api/bale/notify-alarms", { method: "POST", body: "{}" });
    toast(res.message || (res.ok ? ("ارسال شد · " + (res.count || 0) + " مورد") : "ارسال نشد"));
  } catch (e) { toast(e.message, true); }
}

function wireAfShell() {
  document.querySelectorAll("#nav button[data-page]").forEach((b) => {
    b.addEventListener("click", () => showPage(b.dataset.page));
  });
  document.querySelectorAll("#nav .nav-sec-toggle").forEach((sec) => {
    sec.addEventListener("click", () => sec.closest(".nav-group")?.classList.toggle("collapsed"));
  });
  document.getElementById("fabToggle")?.addEventListener("click", (e) => {
    e.preventDefault(); e.stopPropagation();
    window.__afToggleFab();
  }, true);
  document.getElementById("helpFab")?.addEventListener("click", (e) => { e.stopPropagation(); openAfHelp(); }, true);
  document.getElementById("userFab")?.addEventListener("click", (e) => { e.stopPropagation(); toggleAfUser(e); }, true);
  document.getElementById("aboutFab")?.addEventListener("click", (e) => { e.stopPropagation(); openAfAbout(); }, true);
  document.querySelectorAll("[data-help-close]").forEach((el) => {
    el.onclick = (e) => { e.preventDefault(); e.stopPropagation(); closeAfHelp(); };
  });
  document.querySelectorAll("[data-about-close]").forEach((el) => {
    el.onclick = (e) => { e.preventDefault(); e.stopPropagation(); closeAfAbout(); };
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") { closeAfAbout(); closeAfHelp(); }
  });
  document.addEventListener("click", (e) => {
    const pop = document.getElementById("userPopover");
    if (!pop || pop.classList.contains("hidden")) return;
    if (e.target.closest("#userFab") || e.target.closest("#userPopover")) return;
    pop.classList.add("hidden");
  });
}


wireAfShell();
document.getElementById("baleSave")?.addEventListener("click", baleSave);
document.getElementById("baleVerify")?.addEventListener("click", baleVerify);
document.getElementById("baleTest")?.addEventListener("click", baleTestMsg);
document.getElementById("balePushAlarms")?.addEventListener("click", balePushAlarms);
document.getElementById("balePollStart")?.addEventListener("click", async () => {
  try {
    const r = await api("/api/bale/polling/start", { method: "POST", body: "{}" });
    toast(r.message || "polling started");
    loadBale();
  } catch (e) { toast(e.message, true); }
});
document.getElementById("balePollStop")?.addEventListener("click", async () => {
  try {
    const r = await api("/api/bale/polling/stop", { method: "POST", body: "{}" });
    toast(r.message || "stopped");
    loadBale();
  } catch (e) { toast(e.message, true); }
});


document.getElementById("tmSend")?.addEventListener("click", sendTestRequest);
document.querySelectorAll("[data-test-close]").forEach((el) => el.addEventListener("click", closeTestModal));
document.querySelectorAll(".tm-view").forEach((b) => {
  b.addEventListener("click", () => {
    _tmView = b.dataset.view;
    document.querySelectorAll(".tm-view").forEach((x) => x.classList.toggle("on", x === b));
    renderTestOut();
  });
});
document.getElementById("arSave")?.addEventListener("click", arSaveCode);
document.getElementById("arLoad")?.addEventListener("click", arLoadCode);

$("#crDb")?.addEventListener("change", onDbChange);
$("#crTable")?.addEventListener("change", onTableChange);
$("#crJoinCount")?.addEventListener("change", async () => { renderJoinBoxes(); await refreshFieldOptions(); });
$("#crRoute")?.addEventListener("input", updatePreview);
$("#crFilter")?.addEventListener("change", updatePreview);
$("#crTime")?.addEventListener("change", updatePreview);
$("#crLimit")?.addEventListener("input", updatePreview);
$("#crSubmit")?.addEventListener("click", createService);
$("#tabWizard")?.addEventListener("click", () => switchCreateTab("wizard"));
$("#tabManual")?.addEventListener("click", () => switchCreateTab("manual"));
$("#manSubmit")?.addEventListener("click", createManual);
$("#dbSave")?.addEventListener("click", saveDb);
$("#keyAdd")?.addEventListener("click", addKey);
$("#biLoad")?.addEventListener("click", biLoad);
$("#biAdd")?.addEventListener("click", biAdd);
$("#biFields")?.addEventListener("click", biFieldClick);
$("#biClear")?.addEventListener("click", () => { biVisuals = []; renderBi(); });

(async function init() {
  if (!token) return;
  try {
    await api("/api/me");
    $("#loginView").classList.add("hidden");
    $("#appView").classList.remove("hidden");
    me = { user: (await api("/api/me").catch(() => ({}))).user || "admin", role: "admin" };
    showWelcomeSplash();
  } catch {
    logout(true);
  }
})();
