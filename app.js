/* Mi Billetera de Beneficios — lógica compartida por la web (Google Maps) y la versión artifact (mapa SVG). */
(function () {
  "use strict";
  const DAYS = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"];
  const FULL = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"];
  const FULLCAP = FULL.map(d => d[0].toUpperCase() + d.slice(1));
  const ORDER = ["bch", "san", "fal", "cop", "ent"];
  const $ = s => document.querySelector(s);
  const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const store = {
    get(k, d) { try { const v = localStorage.getItem("bb-" + k); return v == null ? d : JSON.parse(v); } catch (_) { return d; } },
    set(k, v) { try { localStorage.setItem("bb-" + k, JSON.stringify(v)); } catch (_) {} }
  };

  const now = new Date();
  const todayIdx = (now.getDay() + 6) % 7;
  const todayISO = now.toISOString().slice(0, 10);

  let DATA, COMUNAS, MAP;
  const st = {
    day: todayIdx,
    provs: new Set(store.get("provs", ORDER)),
    cat: "",
    q: "",
    user: null,          // {lat,lng,label,source}
    near: false,
    active: null,        // id de beneficio
    spot: null           // key del punto abierto en el mapa
  };

  /* ---------- utilidades ---------- */
  function km(a, b) {
    const R = 6371, r = Math.PI / 180;
    const dLat = (b.lat - a.lat) * r, dLng = (b.lng - a.lng) * r;
    const h = Math.sin(dLat / 2) ** 2 + Math.cos(a.lat * r) * Math.cos(b.lat * r) * Math.sin(dLng / 2) ** 2;
    return 2 * R * Math.asin(Math.sqrt(h));
  }
  const fmtKm = d => d < 1 ? Math.round(d * 1000 / 10) * 10 + " m" : d.toFixed(d < 10 ? 1 : 0).replace(".", ",") + " km";
  const color = p => `var(--${DATA.proveedores[p].color})`;
  const nearest = b => {
    if (!st.user || !b.ubicaciones?.length) return null;
    let best = null;
    for (const u of b.ubicaciones) { const d = km(st.user, u); if (!best || d < best.d) best = { d, u }; }
    return best;
  };
  const isNew = b => b.origen === "scraper" && b.primer_visto && (Date.parse(DATA.generado) - Date.parse(b.primer_visto)) / 864e5 <= 10;
  const mapsSearch = q => "https://www.google.com/maps/search/?api=1&query=" + encodeURIComponent(q);
  const mapsDir = u => "https://www.google.com/maps/dir/?api=1&destination=" + u.lat + "," + u.lng +
    (st.user ? "&origin=" + st.user.lat + "," + st.user.lng : "");

  function active() {
    return DATA.beneficios.filter(b => b.estado === "activo" && (!b.vigencia_hasta || b.vigencia_hasta >= todayISO));
  }
  function visible() {
    const q = st.q.trim().toLowerCase();
    let arr = active().filter(b => b.dias.includes(st.day) && st.provs.has(b.proveedor) &&
      (!st.cat || b.categoria === st.cat) && (!q || (b.comercio + " " + b.detalle).toLowerCase().includes(q)));
    return arr;
  }

  /* ---------- render ---------- */
  function renderHead() {
    const vis = visible();
    const best = vis.filter(b => b.descuento_valor).sort((a, b) => b.descuento_valor - a.descuento_valor)[0];
    $("#dayTitle").textContent = st.day === todayIdx ? "Hoy, " + FULL[st.day] : FULLCAP[st.day];
    $("#lede").innerHTML = vis.length
      ? `<b>${vis.length} beneficios</b> con tus tarjetas${best ? `, el mayor es <b>${esc(best.descuento)} en ${esc(best.comercio)}</b>` : ""}.`
      : "Ningún beneficio con estos filtros.";
  }

  function renderWeek() {
    const base = active().filter(b => st.provs.has(b.proveedor) && (!st.cat || b.categoria === st.cat));
    const counts = DAYS.map((_, i) => ORDER.map(p => base.filter(b => b.proveedor === p && b.dias.includes(i)).length));
    const max = Math.max(1, ...counts.map(c => c.reduce((a, b) => a + b, 0)));
    $("#week").innerHTML = DAYS.map((d, i) => {
      const tot = counts[i].reduce((a, b) => a + b, 0);
      const bars = ORDER.map((p, j) => counts[i][j] ? `<i style="--c:${color(p)};height:${counts[i][j] / max * 100}%"></i>` : "").join("");
      return `<button type="button" class="wd" data-d="${i}" aria-pressed="${i === st.day}" aria-label="${FULLCAP[i]}: ${tot} beneficios">
        <span class="name">${d}</span><span class="bars" aria-hidden="true">${bars}</span>
        <span class="n">${tot}</span><span class="today-mark">${i === todayIdx ? "hoy" : ""}</span></button>`;
    }).join("");
  }

  function renderFilters() {
    $("#provChips").innerHTML = ORDER.map(p => `<button type="button" class="chip" data-p="${p}" style="--c:${color(p)}" aria-pressed="${st.provs.has(p)}"><i></i>${esc(DATA.proveedores[p].nombre)}</button>`).join("");
    const sel = $("#cat");
    if (!sel.options.length) {
      sel.innerHTML = `<option value="">Todos los rubros</option>` + Object.entries(DATA.categorias).map(([k, v]) => `<option value="${k}">${esc(v)}</option>`).join("");
    }
  }

  function itemHTML(b) {
    const n = nearest(b);
    const toks = b.descuento.split(" "), mi = Math.max(0, toks.findIndex(t => /\d/.test(t)));
    const main = toks[mi], rest = toks.filter((_, i) => i !== mi).join(" ");
    const facts = [`<li><span>Con</span> ${esc(b.tarjetas)}</li>`];
    if (b.tope) facts.push(`<li><span>Tope</span> ${esc(b.tope)}</li>`);
    if (b.canal) facts.push(`<li>${esc(b.canal)}</li>`);
    if (b.dias.length === 7) facts.push(`<li>Todos los días</li>`);
    if (b.verificado) facts.push(`<li><span>Vigente${b.vigencia_hasta ? " hasta" : ""}</span> ${b.vigencia_hasta ? new Date(b.vigencia_hasta + "T12:00").toLocaleDateString("es-CL", { day: "numeric", month: "short" }) : ""}</li>`);
    else facts.push(`<li class="warn">Confirma en la app antes de pagar</li>`);
    const links = [];
    if (n) links.push(`<a href="${mapsDir(n.u)}" target="_blank" rel="noopener">Cómo llegar</a>`);
    else if (b.ubicaciones?.length) links.push(`<a href="${mapsDir(b.ubicaciones[0])}" target="_blank" rel="noopener">Cómo llegar</a>`);
    else if (b.cadena) links.push(`<a href="${mapsSearch(b.comercio.replace(/\(.*\)/, "") + (st.user ? " cerca de " + st.user.lat + "," + st.user.lng : " Santiago"))}" target="_blank" rel="noopener">Buscar locales</a>`);
    links.push(`<a href="${esc(b.fuente)}" target="_blank" rel="noopener">Condiciones</a>`);
    return `<article class="item${st.active === b.id ? " active" : ""}" data-id="${esc(b.id)}" style="--c:${color(b.proveedor)}">
      <div class="disc${/\d/.test(main) ? "" : " word"}">${esc(main)}${rest ? `<small>${esc(rest)}</small>` : ""}</div>
      <div><h4>${esc(b.comercio)}${n ? `<span class="dist">a ${fmtKm(n.d)}</span>` : ""}${isNew(b) ? `<span class="new">Nuevo</span>` : ""}</h4>
      <p>${esc(b.detalle)}</p><ul class="facts">${facts.join("")}</ul><div class="links">${links.join("")}</div></div></article>`;
  }

  function renderList() {
    const vis = visible();
    $("#listCount").textContent = vis.length ? (st.near && st.user ? "Más cercanos primero" : "Por tarjeta") : "";
    if (!vis.length) {
      $("#list").innerHTML = `<div class="empty"><strong>Sin beneficios para este filtro</strong>Prueba otro día, activa más tarjetas o elige “Todos los rubros”.</div>`;
      return;
    }
    if (st.near && st.user) {
      const sorted = vis.map(b => ({ b, n: nearest(b) })).sort((x, y) => (x.n ? x.n.d : 1e9) - (y.n ? y.n.d : 1e9));
      const withLoc = sorted.filter(x => x.n), rest = sorted.filter(x => !x.n);
      $("#list").innerHTML =
        (withLoc.length ? `<div class="group"><h3>Con local cerca de ti <span>${withLoc.length}</span></h3>${withLoc.map(x => itemHTML(x.b)).join("")}</div>` : "") +
        (rest.length ? `<div class="group"><h3>Cadenas y online <span>${rest.length}</span></h3>${rest.map(x => itemHTML(x.b)).join("")}</div>` : "");
      return;
    }
    $("#list").innerHTML = ORDER.filter(p => vis.some(b => b.proveedor === p)).map(p => {
      const arr = vis.filter(b => b.proveedor === p).sort((a, b) => (a.dias.length === 7) - (b.dias.length === 7) || (b.descuento_valor || 0) - (a.descuento_valor || 0));
      return `<div class="group" style="--c:${color(p)}"><h3><i></i>${esc(DATA.proveedores[p].nombre)} <span>${arr.length}</span></h3>${arr.map(itemHTML).join("")}</div>`;
    }).join("");
  }

  function spots() {
    const m = {};
    for (const b of visible()) for (const u of b.ubicaciones || []) {
      const k = u.lat.toFixed(4) + "," + u.lng.toFixed(4);
      (m[k] = m[k] || { key: k, lat: u.lat, lng: u.lng, label: u.nombre, address: u.direccion, aprox: u.aprox, items: [] }).items.push(b);
    }
    return Object.values(m).map(s => ({ ...s, color: color(s.items[0].proveedor), colorVar: DATA.proveedores[s.items[0].proveedor].color }));
  }

  function renderMap() {
    if (!MAP) return;
    const sp = spots();
    MAP.render(sp, st.spot);
    $("#mapCount").textContent = sp.length ? `${sp.length} lugares el ${FULL[st.day]}` : `Sin locales en el mapa el ${FULL[st.day]}`;
    renderSpotCard(sp.find(s => s.key === st.spot));
  }

  function spotRows(s) {
    return s.items.map(b => `<div class="row" style="--c:${color(b.proveedor)}"><b>${esc(b.descuento.split(" ").find(t => /\d/.test(t)) || b.descuento)}</b><span>${esc(b.comercio)}, ${esc(DATA.proveedores[b.proveedor].nombre)}</span></div>`).join("");
  }
  function renderSpotCard(s) {
    const el = $("#mapcard");
    if (!el) return;
    if (!s) { el.hidden = true; return; }
    const d = st.user ? `, a ${fmtKm(km(st.user, s))}` : "";
    el.innerHTML = `<h5>${esc(s.address || s.label)}${d}</h5>${spotRows(s)}<div class="links"><a href="${mapsDir(s)}" target="_blank" rel="noopener">Cómo llegar</a></div>`;
    el.hidden = false;
  }
  window.BB_spotInfoHTML = s => `<div class="gm-iw"><h5>${esc(s.address || s.label)}${st.user ? `, a ${fmtKm(km(st.user, s))}` : ""}</h5>${s.items.map(b => `<div class="row"><b style="color:${getComputedStyle(document.documentElement).getPropertyValue("--" + DATA.proveedores[b.proveedor].color)}">${esc(b.descuento.split(" ").find(t => /\d/.test(t)) || b.descuento)}</b><span>${esc(b.comercio)}</span></div>`).join("")}<p><a href="${mapsDir(s)}" target="_blank" rel="noopener">Cómo llegar</a></p></div>`;

  function renderWhere() {
    const s = $("#whereStatus");
    s.textContent = st.user ? `Usando ${st.user.label}` : "";
    $("#nearToggle").disabled = !st.user;
    $("#nearToggle").checked = st.near && !!st.user;
  }

  function renderAll() { renderHead(); renderWeek(); renderFilters(); renderList(); renderMap(); renderWhere(); }

  /* ---------- ubicación ---------- */
  function setUser(pos) {
    st.user = pos;
    if (pos) { st.near = true; store.set("user", pos.source === "gps" ? null : pos); }
    MAP && MAP.setUser(pos);
    if (pos && MAP) MAP.focus(pos.lat, pos.lng, 13);
    renderAll();
  }
  function locate() {
    const s = $("#whereStatus");
    if (!navigator.geolocation) { s.textContent = "Este navegador no entrega ubicación. Elige tu comuna o márcala en el mapa."; return; }
    s.textContent = "Buscando tu ubicación…";
    navigator.geolocation.getCurrentPosition(
      p => setUser({ lat: p.coords.latitude, lng: p.coords.longitude, label: "tu ubicación actual", source: "gps" }),
      () => { s.textContent = "No se pudo obtener tu ubicación. Elige tu comuna o márcala en el mapa."; },
      { enableHighAccuracy: true, timeout: 10000, maximumAge: 120000 }
    );
  }
  function comunaLatLng(c) {
    const { W, H, B } = COMUNAS;
    return { lat: B.n - c.c[1] / H * (B.n - B.s), lng: B.w + c.c[0] / W * (B.e - B.w) };
  }

  /* ---------- eventos ---------- */
  function bind() {
    $("#week").addEventListener("click", e => { const b = e.target.closest(".wd"); if (!b) return; st.day = +b.dataset.d; st.active = null; st.spot = null; renderAll(); });
    $("#provChips").addEventListener("click", e => {
      const b = e.target.closest(".chip"); if (!b) return; const p = b.dataset.p;
      st.provs.has(p) ? st.provs.delete(p) : st.provs.add(p); store.set("provs", [...st.provs]); renderAll();
    });
    $("#cat").addEventListener("change", e => { st.cat = e.target.value; renderAll(); });
    $("#q").addEventListener("input", e => { st.q = e.target.value; renderHead(); renderList(); renderMap(); });
    $("#nearToggle").addEventListener("change", e => { st.near = e.target.checked; renderList(); });
    $("#locate").addEventListener("click", locate);
    $("#comuna").addEventListener("change", e => {
      const c = COMUNAS.c.find(x => x.n === e.target.value); if (!c) return;
      setUser({ ...comunaLatLng(c), label: "el centro de " + c.n, source: "comuna" });
    });
    $("#pick").addEventListener("click", () => { MAP && MAP.startPick(); $("#pick").classList.add("on"); $("#whereStatus").textContent = "Toca el mapa donde estás."; setView("map"); });
    $("#list").addEventListener("click", e => {
      if (e.target.closest("a")) return;
      const it = e.target.closest(".item"); if (!it) return;
      const b = DATA.beneficios.find(x => x.id === it.dataset.id); st.active = b.id;
      const u = nearest(b)?.u || b.ubicaciones?.[0];
      if (u) { st.spot = u.lat.toFixed(4) + "," + u.lng.toFixed(4); MAP && MAP.focus(u.lat, u.lng, 15); }
      renderList(); renderMap();
      if (u && matchMedia("(max-width:900px)").matches) setView("map");
    });
    $("#reset").addEventListener("click", () => MAP && MAP.fit());
    $("#vList").addEventListener("click", () => setView("list"));
    $("#vMap").addEventListener("click", () => setView("map"));
  }
  function setView(v) {
    $("#main").dataset.view = v;
    $("#vList").setAttribute("aria-pressed", v === "list");
    $("#vMap").setAttribute("aria-pressed", v === "map");
    if (v === "map" && MAP?.resize) MAP.resize();
  }

  /* ---------- arranque ---------- */
  async function boot() {
    DATA = window.BB_DATA || await fetch("data/beneficios.json", { cache: "no-cache" }).then(r => r.json());
    COMUNAS = window.BB_COMUNAS || await fetch("comunas.json").then(r => r.json());
    const urban = ["Santiago", "Providencia", "Las Condes", "Vitacura", "Ñuñoa", "La Reina", "Lo Barnechea", "Macul", "Peñalolén", "La Florida", "San Miguel", "San Joaquín", "Recoleta", "Independencia", "Estación Central", "Maipú", "Puente Alto", "Huechuraba", "Quinta Normal", "La Cisterna", "Conchalí", "Cerrillos", "Pudahuel", "Quilicura", "Renca", "San Bernardo", "El Bosque", "La Granja", "Lo Prado", "Pedro Aguirre Cerda", "San Ramón", "Lo Espejo", "La Pintana", "Cerro Navia"];
    $("#comuna").innerHTML = `<option value="">Elegir comuna</option>` + COMUNAS.c.filter(c => urban.includes(c.n)).map(c => c.n).sort((a, b) => a.localeCompare(b, "es")).map(n => `<option>${esc(n)}</option>`).join("");
    $("#updated").textContent = new Date(DATA.generado + "T12:00").toLocaleDateString("es-CL", { day: "numeric", month: "long", year: "numeric" });
    bind();
    const saved = store.get("user", null);
    if (saved) { st.user = saved; st.near = true; }
    renderAll();

    const factory = window.BB_createMap;
    if (factory) {
      try {
        MAP = await factory($("#map"), {
          comunas: COMUNAS,
          onSpot(key) { st.spot = key; const s = spots().find(x => x.key === key); st.active = s ? s.items[0].id : null; renderList(); renderMap(); },
          onPick(ll) { $("#pick").classList.remove("on"); setUser({ ...ll, label: "el punto que marcaste", source: "mapa" }); }
        });
        if (st.user) MAP.setUser(st.user);
        renderMap();
      } catch (err) {
        $("#map").innerHTML = `<div class="empty"><strong>El mapa no cargó</strong>${esc(err.message || err)}</div>`;
      }
    }
  }
  document.readyState === "loading" ? document.addEventListener("DOMContentLoaded", boot) : boot();
})();
