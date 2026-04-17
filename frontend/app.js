const API = "";  // same origin, nginx proxies /api/*

let currentInfo = null;
let currentFormat = "video";
let pollInterval = null;

// ── Helpers ───────────────────────────────────────────────────────────────────

function $(id) { return document.getElementById(id); }

function show(id) { $(id).classList.remove("hidden"); }
function hide(id) { $(id).classList.add("hidden"); }

function setLoading(loading) {
  const btn = $("fetch-btn");
  btn.querySelector(".btn-text").classList.toggle("hidden", loading);
  btn.querySelector(".btn-spinner").classList.toggle("hidden", !loading);
  btn.disabled = loading;
  $("url-input").disabled = loading;
}

function showError(msg) {
  const el = $("url-error");
  el.textContent = msg;
  el.classList.remove("hidden");
}

function clearError() { $("url-error").classList.add("hidden"); }

function formatDuration(secs) {
  if (!secs) return "";
  const h = Math.floor(secs / 3600);
  const m = Math.floor((secs % 3600) / 60);
  const s = secs % 60;
  if (h) return `${h}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
  return `${m}:${String(s).padStart(2, "0")}`;
}

function formatViews(n) {
  if (!n) return "";
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M views`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(0)}K views`;
  return `${n} views`;
}

function qualityLabel(q, format) {
  if (q === "best") return "Best available";
  if (format === "audio") return `${q} kbps`;
  return `${q}p`;
}

// ── Fetch Info ─────────────────────────────────────────────────────────────────

async function fetchInfo() {
  clearError();
  const url = $("url-input").value.trim();
  if (!url) { showError("Please enter a YouTube URL."); return; }

  setLoading(true);
  hide("info-card");
  hide("progress-card");
  hide("done-card");

  try {
    const res = await fetch(`${API}/api/info`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Failed to fetch info");

    currentInfo = data;
    renderInfo(data);
    show("info-card");
  } catch (err) {
    showError(err.message || "Something went wrong. Check the URL and try again.");
  } finally {
    setLoading(false);
  }
}

function renderInfo(info) {
  if (info.type === "playlist") {
    // Hide single-video fields
    $("thumbnail").src = "";
    hide("video-info");

    // Show playlist badge
    $("playlist-count").textContent = `Playlist · ${info.count} videos`;
    show("playlist-badge");

    // Render preview list
    const ul = $("playlist-preview");
    ul.innerHTML = "";
    info.entries.forEach((e, i) => {
      const li = document.createElement("li");
      li.innerHTML = `
        <span class="playlist-num">${i + 1}</span>
        <span class="playlist-title">${escHtml(e.title)}</span>
        <span class="playlist-dur">${formatDuration(e.duration)}</span>`;
      ul.appendChild(li);
    });
    if (info.count > 20) {
      const li = document.createElement("li");
      li.innerHTML = `<span class="playlist-num">…</span><span class="playlist-title" style="color:var(--text-muted)">and ${info.count - 20} more videos</span>`;
      ul.appendChild(li);
    }
    show("playlist-preview");
  } else {
    // Single video
    $("thumbnail").src = info.thumbnail || "";
    $("video-title").textContent = info.title || "Unknown title";
    $("video-uploader").textContent = info.uploader || "";
    const dur = formatDuration(info.duration);
    const views = formatViews(info.view_count);
    $("video-duration").textContent = [dur, views].filter(Boolean).join(" · ");
    show("video-info");
    hide("playlist-badge");
    hide("playlist-preview");
  }

  // Reset format to video
  setFormat("video", info);
}

function escHtml(str) {
  return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

// ── Format / Quality ───────────────────────────────────────────────────────────

function setFormat(fmt, info) {
  currentFormat = fmt;
  info = info || currentInfo;
  if (!info) return;

  $("btn-video").classList.toggle("active", fmt === "video");
  $("btn-audio").classList.toggle("active", fmt === "audio");

  const qualities = fmt === "video" ? info.video_qualities : info.audio_qualities;
  const select = $("quality-select");
  select.innerHTML = "";
  qualities.forEach(q => {
    const opt = document.createElement("option");
    opt.value = q;
    opt.textContent = qualityLabel(q, fmt);
    select.appendChild(opt);
  });
}

// ── Download ───────────────────────────────────────────────────────────────────

async function startDownload() {
  const url = $("url-input").value.trim();
  const quality = $("quality-select").value;

  $("download-btn").disabled = true;
  hide("info-card");
  show("progress-card");
  hide("done-card");

  try {
    const res = await fetch(`${API}/api/download`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url, format_type: currentFormat, quality }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Failed to start download");

    pollStatus(data.task_id);
  } catch (err) {
    show("info-card");
    hide("progress-card");
    $("download-btn").disabled = false;
    showError(err.message);
  }
}

function pollStatus(taskId) {
  clearInterval(pollInterval);

  pollInterval = setInterval(async () => {
    try {
      const res = await fetch(`${API}/api/status/${taskId}`);
      const data = await res.json();

      if (data.status === "downloading" || data.status === "pending") {
        const pct = data.progress || 0;
        $("progress-bar-fill").style.width = `${pct}%`;
        $("progress-pct").textContent = `${pct}%`;

        if (currentInfo?.type === "playlist" && data.total > 1) {
          $("progress-label").textContent = `Downloading playlist (${data.total} videos)…`;
        } else {
          $("progress-label").textContent = pct < 5 ? "Starting download…" : "Downloading…";
        }
      } else if (data.status === "complete") {
        clearInterval(pollInterval);
        $("progress-bar-fill").style.width = "100%";
        $("progress-pct").textContent = "100%";

        setTimeout(() => {
          hide("progress-card");
          $("download-link").href = `${API}/api/file/${taskId}`;
          show("done-card");
        }, 400);
      } else if (data.status === "error") {
        clearInterval(pollInterval);
        hide("progress-card");
        show("info-card");
        $("download-btn").disabled = false;
        showError(`Download failed: ${data.error || "Unknown error"}`);
      }
    } catch {
      // network hiccup, keep polling
    }
  }, 1000);
}

// ── Reset ──────────────────────────────────────────────────────────────────────

function resetAll() {
  clearInterval(pollInterval);
  currentInfo = null;
  currentFormat = "video";

  $("url-input").value = "";
  hide("info-card");
  hide("progress-card");
  hide("done-card");
  clearError();

  $("progress-bar-fill").style.width = "0%";
  $("progress-pct").textContent = "0%";
  $("download-btn").disabled = false;
}

// ── Enter key on URL input ─────────────────────────────────────────────────────

$("url-input").addEventListener("keydown", e => {
  if (e.key === "Enter") fetchInfo();
});
