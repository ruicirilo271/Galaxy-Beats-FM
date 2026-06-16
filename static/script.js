/* 🌌 Galaxy Beats FM — Frontend Super Deus v10
   Corrige: metadata manual, erro de variável d no tick, player resiliente,
   equalizer com fallback visual quando CORS bloqueia WebAudio.
*/

const $ = (q) => document.querySelector(q);

const player = $("#player");
const eqCanvas = $("#eq");
const ctx = eqCanvas ? eqCanvas.getContext("2d") : null;
const titleNow = $("#titleNow");
const timeNow = $("#timeNow");
const logoNow = $("#logoNow");
const songNow = $("#songNow");
const coverArt = $("#coverArt");
const schedList = $("#schedList");
const lyricsBox = $("#lyricsBox");
const artistBio = $("#artistBio");
const histList = $("#histList");
const ytFrame = $("#ytFrame");
const ytStatus = $("#ytStatus");
const soundUnlockBtn = $("#soundUnlock");
const soundToast = $("#soundToast");
const autoBtn = $("#autoBtn");
const sourceBadge = $("#sourceBadge");
const stationBadge = $("#stationBadge");
const nextShow = $("#nextShow");
const statusDot = $("#statusDot");

const DEFAULT_COVER = "/static/default_cover.png";

const LOGOS = {
  MOTARD: "https://cdn.onlineradiobox.com/img/l/1/45671.v8.png",
  RENASCENCA: "https://cdn.onlineradiobox.com/img/l/1/19431.v4.png",
  CIDADEFM: "https://cdn.onlineradiobox.com/img/l/1/71601.v15.png",
  RADIOCIDADE: "https://cdn.onlineradiobox.com/img/l/3/93733.v4.png",
  RECORD: "https://cdn.onlineradiobox.com/img/l/9/19399.v8.png",
  ANTENA1: "https://cdn.onlineradiobox.com/img/l/5/45585.v5.png",
};

let STATE = {
  lastUrl: "",
  lastMetaTitle: "",
  forceId: null,
  audioCtx: null,
  analyser: null,
  src: null,
  hls: null,
  analyserBlocked: false,
  startedOnce: false,
  fakePhase: 0,
};

function setClock() {
  const el = $("#clock");
  if (!el) return;
  el.textContent = new Date().toLocaleTimeString("pt-PT", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}
setClock();
setInterval(setClock, 1000);

async function fetchJSON(url) {
  try {
    const r = await fetch(url, { cache: "no-store" });
    if (!r.ok) throw new Error("HTTP " + r.status);
    return await r.json();
  } catch (e) {
    console.warn("fetch erro", url, e);
    return null;
  }
}

function escapeHTML(str = "") {
  return String(str)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}


function buildYouTubeEmbedUrl(url = "") {
  if (!url) return "";
  const sep = url.includes("?") ? "&" : "?";
  return `${url}${sep}rel=0&modestbranding=1&playsinline=1&origin=${encodeURIComponent(window.location.origin)}`;
}

function fmtHour(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleTimeString("pt-PT", { hour: "2-digit", minute: "2-digit" });
}

function splitSongArtist(joined) {
  if (!joined || joined === "—") return { song: "", artist: "" };
  for (const sep of [" – ", " — ", " - "]) {
    if (joined.includes(sep)) {
      const [left, right] = joined.split(sep, 2);
      // Backend envia: música – artista
      return { song: (left || "").trim(), artist: (right || "").trim() };
    }
  }
  return { song: joined.trim(), artist: "" };
}

function setStatus(text, live = false) {
  if (sourceBadge) sourceBadge.textContent = text;
  if (statusDot) statusDot.classList.toggle("is-live", live);
}

function showUnlockUI() {
  if (soundUnlockBtn) soundUnlockBtn.style.display = "inline-flex";
  if (soundToast) {
    soundToast.style.display = "block";
    window.clearTimeout(soundToast._timer);
    soundToast._timer = window.setTimeout(() => (soundToast.style.display = "none"), 3600);
  }
}

function hideUnlockUI() {
  if (soundUnlockBtn) soundUnlockBtn.style.display = "none";
  if (soundToast) soundToast.style.display = "none";
}

function renderSchedule(schedule = [], activeId = "") {
  if (!schedList) return;
  schedList.innerHTML = "";
  schedule.forEach((i) => {
    const logo = LOGOS[i.id] || "";
    const item = document.createElement("li");
    item.className = "sched-card" + (i.id === activeId ? " active" : "");
    item.innerHTML = `
      <div class="sched-hour">${escapeHTML(i.hora)}</div>
      <div class="sched-main">
        <strong>${escapeHTML(i.programa)}</strong>
        <span>${escapeHTML(i.dj)}</span>
        <small>${escapeHTML(i.descricao)}</small>
      </div>
      <div class="sched-radio">
        ${logo ? `<img src="${logo}" alt="${escapeHTML(i.titulo)}">` : ""}
        <span>${escapeHTML(i.titulo)}</span>
      </div>`;
    schedList.appendChild(item);
  });
}

function updateNowUI(d) {
  const a = d.agora || {};
  if (titleNow) titleNow.textContent = a.titulo || "Rádio Atual";
  if (timeNow) timeNow.textContent = `${fmtHour(a.inicio)} – ${fmtHour(a.fim)}`;
  if (logoNow) logoNow.src = a.logo || DEFAULT_COVER;
  if (stationBadge) stationBadge.textContent = a.programa ? `${a.programa} · ${a.dj || ""}` : "Ao vivo";
  if (nextShow && d.proximo) nextShow.textContent = `Próximo: ${d.proximo.programa} · ${fmtHour(d.proximo.quando)}`;

  renderSchedule(d.schedule || [], a.id);

  document.querySelectorAll(".stations-grid .btn").forEach((btn) => btn.classList.remove("active"));
  const active = document.querySelector(`.stations-grid .btn[data-id="${a.id}"]`);
  if (active) active.classList.add("active");
  if (autoBtn) autoBtn.classList.toggle("active", !STATE.forceId);
}

function swapStream(url) {
  if (!player || !url || url === STATE.lastUrl) return;

  try {
    setStatus("A ligar stream...", false);
    STATE.lastUrl = url;

    if (STATE.hls) {
      try { STATE.hls.destroy(); } catch {}
      STATE.hls = null;
    }

    player.pause();
    player.removeAttribute("src");
    player.load();

    const isHls = window.Hls && Hls.isSupported() && /\.m3u8(\?|$)/i.test(url);
    if (isHls) {
      const hls = new Hls({ enableWorker: true, lowLatencyMode: true, backBufferLength: 30 });
      hls.loadSource(url);
      hls.attachMedia(player);
      hls.on(Hls.Events.MANIFEST_PARSED, () => safePlay());
      hls.on(Hls.Events.ERROR, (_, data) => {
        console.warn("[HLS ERRO]", data.details, data.reason || "");
        if (data.fatal) setTimeout(() => swapStream(url), 2200);
      });
      STATE.hls = hls;
    } else {
      player.src = url;
      player.volume = 1;
      player.autoplay = true;
      player.controls = true;
      player.load();
      player.addEventListener("canplay", () => safePlay(), { once: true });
    }
  } catch (e) {
    console.warn("swapStream erro", e);
    setStatus("Erro no stream", false);
  }
}

async function setupAudioGraph() {
  if (!player || STATE.analyser || STATE.analyserBlocked) return;
  try {
    STATE.audioCtx = STATE.audioCtx || new (window.AudioContext || window.webkitAudioContext)();
    STATE.src = STATE.src || STATE.audioCtx.createMediaElementSource(player);
    STATE.analyser = STATE.audioCtx.createAnalyser();
    STATE.analyser.fftSize = 256;
    STATE.analyser.smoothingTimeConstant = 0.82;
    STATE.src.connect(STATE.analyser);
    STATE.analyser.connect(STATE.audioCtx.destination);
  } catch (e) {
    // Alguns streams não enviam CORS; o player continua a tocar e o EQ passa para modo visual.
    console.warn("Equalizador real bloqueado pelo browser/CORS. A usar visualizer fallback.", e);
    STATE.analyserBlocked = true;
  }
}

async function safePlay() {
  if (!player) return;
  try {
    player.muted = false;
    player.volume = 1.0;
    await setupAudioGraph();
    if (STATE.audioCtx && STATE.audioCtx.state === "suspended") {
      await STATE.audioCtx.resume().catch(() => {});
    }
    const p = player.play();
    if (p && p.catch) {
      await p;
    }
    STATE.startedOnce = true;
    hideUnlockUI();
    setStatus("Ao vivo", true);
  } catch (e) {
    console.warn("safePlay erro", e);
    showUnlockUI();
    setStatus("Clique para ativar som", false);
  }
}

function resizeCanvas() {
  if (!eqCanvas) return;
  const r = eqCanvas.getBoundingClientRect();
  const ratio = window.devicePixelRatio || 1;
  eqCanvas.width = Math.max(360, Math.floor(r.width * ratio));
  eqCanvas.height = Math.max(120, Math.floor(150 * ratio));
}
window.addEventListener("resize", resizeCanvas);
resizeCanvas();

function drawBars(values) {
  if (!ctx || !eqCanvas) return;
  const W = eqCanvas.width;
  const H = eqCanvas.height;
  ctx.clearRect(0, 0, W, H);

  const gradient = ctx.createLinearGradient(0, 0, W, H);
  gradient.addColorStop(0, "rgba(0, 242, 255, 0.95)");
  gradient.addColorStop(0.5, "rgba(154, 77, 255, 0.95)");
  gradient.addColorStop(1, "rgba(255, 43, 214, 0.95)");
  ctx.fillStyle = gradient;
  ctx.shadowColor = "rgba(0, 242, 255, 0.55)";
  ctx.shadowBlur = 18;

  const count = Math.min(values.length, 70);
  const gap = 4;
  const barW = Math.max(3, (W - gap * count) / count);
  for (let i = 0; i < count; i++) {
    const v = values[i] / 255;
    const h = Math.max(8, v * (H - 18));
    const x = i * (barW + gap);
    const y = H - h - 8;
    roundRect(ctx, x, y, barW, h, Math.min(8, barW / 2));
    ctx.fill();
  }

  ctx.shadowBlur = 0;
  ctx.fillStyle = "rgba(255,255,255,0.18)";
  ctx.fillRect(0, H - 2, W, 1);
}

function roundRect(c, x, y, w, h, r) {
  c.beginPath();
  c.moveTo(x + r, y);
  c.arcTo(x + w, y, x + w, y + h, r);
  c.arcTo(x + w, y + h, x, y + h, r);
  c.arcTo(x, y + h, x, y, r);
  c.arcTo(x, y, x + w, y, r);
  c.closePath();
}

function drawEQ() {
  requestAnimationFrame(drawEQ);
  if (!ctx || !eqCanvas) return;

  if (STATE.analyser && player && !player.paused) {
    const arr = new Uint8Array(STATE.analyser.frequencyBinCount);
    STATE.analyser.getByteFrequencyData(arr);
    drawBars(Array.from(arr));
    return;
  }

  // Fallback bonito: mantém o painel vivo mesmo quando o browser bloqueia análise real.
  STATE.fakePhase += player && !player.paused ? 0.09 : 0.025;
  const vals = Array.from({ length: 70 }, (_, i) => {
    const wave = Math.sin(STATE.fakePhase + i * 0.33) * 0.5 + 0.5;
    const wave2 = Math.sin(STATE.fakePhase * 0.73 + i * 0.13) * 0.5 + 0.5;
    return 35 + (wave * 125 + wave2 * 65) * (player && !player.paused ? 1 : 0.55);
  });
  drawBars(vals);
}
drawEQ();

async function updateMeta() {
  const q = STATE.forceId ? `&force=${encodeURIComponent(STATE.forceId)}` : "";
  const m = await fetchJSON(`/metadata?t=${Date.now()}${q}`);
  if (!m) return;

  if (sourceBadge) sourceBadge.textContent = m.source && m.source !== "—" ? m.source : "A ouvir";

  if (!m.title || m.title === "—") {
    if (!STATE.lastMetaTitle && songNow) songNow.textContent = "🎵 A identificar música...";
    return;
  }

  if (m.title === STATE.lastMetaTitle) return;
  STATE.lastMetaTitle = m.title;

  if (songNow) {
    songNow.textContent = `🎵 ${m.title}`;
    songNow.classList.add("flash");
    setTimeout(() => songNow.classList.remove("flash"), 1600);
  }

  if (lyricsBox) lyricsBox.textContent = "A procurar letra...";
  if (artistBio) artistBio.textContent = "A carregar biografia...";
  if (ytFrame) ytFrame.src = "";
  if (ytStatus) ytStatus.textContent = "A procurar vídeo no YouTube...";
  if (coverArt) coverArt.src = DEFAULT_COVER;

  const artist = m.artist || splitSongArtist(m.title).artist;
  const song = m.song || splitSongArtist(m.title).song;
  if (song && artist) await enrich(artist, song);
  refreshHistory();
}

async function enrich(artist, title) {
  const d = await fetchJSON(`/enrich?artist=${encodeURIComponent(artist)}&title=${encodeURIComponent(title)}`);
  if (!d) return;

  if (coverArt) {
    coverArt.onerror = () => { coverArt.src = DEFAULT_COVER; };
    coverArt.src = d.cover || DEFAULT_COVER;
  }
  if (lyricsBox) lyricsBox.textContent = d.lyrics || "Letra não encontrada para esta música.";
  if (artistBio) artistBio.textContent = d.bio || "Biografia não encontrada.";

  if (ytFrame) {
    ytFrame.src = buildYouTubeEmbedUrl(d.youtube || "");
  }

  if (ytStatus) {
    if (d.youtube) {
      const label = d.youtube_title ? `Vídeo encontrado: ${d.youtube_title}` : "Vídeo encontrado no YouTube.";
      const link = d.youtube_watch ? ` <a class="yt-open" href="${d.youtube_watch}" target="_blank" rel="noopener">Abrir no YouTube</a>` : "";
      ytStatus.innerHTML = `${escapeHTML(label)}${link}<span class="yt-hint">Se o iframe ainda disser “Video unavailable”, usa o botão Abrir no YouTube; esse bloqueio vem do dono do vídeo.</span>`;
    } else {
      const reason = d.youtube_error || "Vídeo não encontrado.";
      const searchUrl = `https://www.youtube.com/results?search_query=${encodeURIComponent(`${artist} ${title}`)}`;
      ytStatus.innerHTML = `${escapeHTML(reason)} <a class="yt-open" href="${searchUrl}" target="_blank" rel="noopener">Pesquisar no YouTube</a>`;
    }
  }
}

async function refreshHistory() {
  const h = await fetchJSON(`/history?t=${Date.now()}`);
  if (!h || !histList) return;
  histList.innerHTML = "";

  h.slice(0, 40).forEach((i) => {
    const li = document.createElement("li");
    const when = new Date(i.when).toLocaleTimeString("pt-PT", { hour: "2-digit", minute: "2-digit" });
    li.innerHTML = `
      <span class="hist-time">${escapeHTML(when)}</span>
      <span class="hist-track">${escapeHTML(i.title || "—")}</span>
      <span class="hist-artist">${escapeHTML(i.artist || "—")}</span>
      <span class="hist-station">${escapeHTML(i.station || "—")}</span>`;
    histList.appendChild(li);
  });
}

async function tick(force = false) {
  const q = STATE.forceId ? `?force=${encodeURIComponent(STATE.forceId)}` : "";
  const d = await fetchJSON(`/now${q}`);
  if (!d || !d.agora) return;

  const a = d.agora;
  updateNowUI(d);
  if (force || a.url !== STATE.lastUrl) {
    STATE.lastMetaTitle = "";
    swapStream(a.url);
    setTimeout(() => {
      safePlay();
      updateMeta();
    }, 900);
  } else {
    updateMeta();
  }
  console.log("⏱ Atualizou programação:", a.titulo, "-", a.programa);
}

function wireButtons() {
  document.querySelectorAll(".stations-grid .btn").forEach((b) => {
    b.addEventListener("click", () => {
      STATE.forceId = b.dataset.id;
      tick(true);
    });
  });

  if (autoBtn) {
    autoBtn.addEventListener("click", () => {
      STATE.forceId = null;
      tick(true);
    });
  }

  if (soundUnlockBtn) soundUnlockBtn.addEventListener("click", safePlay);
  document.addEventListener("click", () => {
    if (!STATE.startedOnce || (STATE.audioCtx && STATE.audioCtx.state === "suspended")) safePlay();
  }, { once: false });

  if (player) {
    player.addEventListener("playing", () => setStatus("Ao vivo", true));
    player.addEventListener("waiting", () => setStatus("A carregar...", false));
    player.addEventListener("error", () => {
      setStatus("Erro no player", false);
      setTimeout(() => tick(true), 2500);
    });
  }
}

setInterval(() => {
  if (player && STATE.lastUrl && (player.paused || player.readyState < 2)) safePlay();
  if (STATE.audioCtx && STATE.audioCtx.state === "suspended") STATE.audioCtx.resume().catch(() => {});
}, 8000);

setInterval(updateMeta, 35000);
setInterval(() => {
  if (!STATE.forceId) tick(false);
}, 65000);

document.addEventListener("DOMContentLoaded", () => {
  if (coverArt) coverArt.src = DEFAULT_COVER;
  wireButtons();
  refreshHistory();
  tick(true);
});
