/* Mapa SVG sin dependencias externas: límites comunales reales (BCN) de Santiago.
   Se usa en la versión artifact y como respaldo si no hay API key de Google Maps. */
window.BB_createMap = window.BB_createMap || async function (el, opts) {
  const NS = "http://www.w3.org/2000/svg";
  const { W, H, B, c: COM } = opts.comunas;
  const proj = (lat, lng) => [(lng - B.w) / (B.e - B.w) * W, (B.n - lat) / (B.n - B.s) * H];
  const unproj = (x, y) => ({ lat: B.n - y / H * (B.n - B.s), lng: B.w + x / W * (B.e - B.w) });
  const HOME = { x: 230, y: 170, w: 560, h: 560 * 0.72 }; // Gran Santiago urbano
  let vb = { ...HOME }, aspect = 0.72;
  const RIVER = [[-33.352, -70.505], [-33.362, -70.528], [-33.378, -70.552], [-33.388, -70.572], [-33.395, -70.588], [-33.408, -70.601], [-33.418, -70.615], [-33.425, -70.630], [-33.431, -70.648], [-33.432, -70.664], [-33.428, -70.682], [-33.420, -70.700], [-33.414, -70.722], [-33.418, -70.745], [-33.43, -70.77]];
  const LABELS = new Set(["Santiago", "Providencia", "Las Condes", "Vitacura", "Ñuñoa", "La Reina", "Lo Barnechea", "Macul", "Peñalolén", "La Florida", "San Miguel", "San Joaquín", "Recoleta", "Independencia", "Estación Central", "Maipú", "Puente Alto", "Huechuraba", "Quinta Normal", "La Cisterna", "Conchalí", "Cerrillos", "Pudahuel", "Quilicura", "Renca", "San Bernardo", "El Bosque", "La Granja", "Lo Prado", "Pedro Aguirre Cerda", "San Ramón", "Lo Espejo", "La Pintana", "Cerro Navia"]);

  const svg = document.createElementNS(NS, "svg");
  svg.setAttribute("role", "img");
  svg.setAttribute("aria-label", "Mapa de Santiago con los locales que tienen beneficio");
  el.innerHTML = ""; el.appendChild(svg);
  const gBase = document.createElementNS(NS, "g"), gLab = document.createElementNS(NS, "g"), gPins = document.createElementNS(NS, "g"), gUser = document.createElementNS(NS, "g");
  svg.append(gBase, gLab, gPins, gUser);

  const riverPts = RIVER.map(p => proj(...p).map(v => v.toFixed(1)).join(",")).join(" ");
  gBase.innerHTML = `<rect x="-3000" y="-3000" width="7000" height="7000" fill="var(--map-land)"/>` +
    COM.map(c => `<path d="${c.d}" fill="${LABELS.has(c.n) ? "var(--map-urban)" : "var(--map-land)"}" stroke="var(--map-line)" stroke-width="1.4" vector-effect="non-scaling-stroke"/>`).join("") +
    `<polyline points="${riverPts}" fill="none" stroke="var(--map-river)" stroke-width="3.5" vector-effect="non-scaling-stroke" stroke-linecap="round" stroke-linejoin="round"/>`;

  let spots = [], activeKey = null, user = null, picking = false;
  const scale = () => vb.w / W;

  function drawLabels() {
    const s = scale(), fs = 11.5 * s * 1.6;
    gLab.innerHTML = COM.filter(c => LABELS.has(c.n)).map(c =>
      `<text x="${c.c[0]}" y="${c.c[1]}" text-anchor="middle" font-size="${fs}" fill="var(--map-label)" font-family="var(--f-body)" font-weight="500" pointer-events="none">${c.n}</text>`).join("");
  }
  function drawPins() {
    const s = scale() * 1.6;
    gPins.innerHTML = spots.map(sp => {
      const [x, y] = proj(sp.lat, sp.lng), act = sp.key === activeKey, r = (act ? 11 : 8) * s;
      return `<g data-key="${sp.key}" style="cursor:pointer">
        <circle cx="${x}" cy="${y}" r="${r * 2.1}" fill="transparent"/>
        ${act ? `<circle cx="${x}" cy="${y}" r="${r + 6 * s}" fill="${sp.color}" opacity=".22"/>` : ""}
        <circle cx="${x}" cy="${y}" r="${r}" fill="${sp.color}" stroke="var(--surface)" stroke-width="${2.2 * s}"/>
        ${sp.items.length > 1 ? `<text x="${x}" y="${y + 3.6 * s}" text-anchor="middle" font-size="${10 * s}" font-weight="700" fill="var(--surface)" font-family="var(--f-body)" pointer-events="none">${sp.items.length}</text>` : ""}
      </g>`;
    }).join("");
  }
  function drawUser() {
    if (!user) { gUser.innerHTML = ""; return; }
    const s = scale() * 1.6, [x, y] = proj(user.lat, user.lng);
    gUser.innerHTML = `<circle cx="${x}" cy="${y}" r="${22 * s}" fill="var(--user)" opacity=".14"/>
      <circle cx="${x}" cy="${y}" r="${7 * s}" fill="var(--user)" stroke="#fff" stroke-width="${2.5 * s}"/>`;
  }
  function apply() {
    const r = el.getBoundingClientRect();
    aspect = r.width ? r.height / r.width : aspect;
    vb.h = vb.w * aspect;
    svg.setAttribute("viewBox", `${vb.x} ${vb.y} ${vb.w} ${vb.h}`);
  }
  function redraw() { apply(); drawLabels(); drawPins(); drawUser(); }

  function zoomAt(f, cx, cy) {
    const nw = Math.min(W * 1.2, Math.max(40, vb.w * f));
    cx = cx ?? vb.x + vb.w / 2; cy = cy ?? vb.y + vb.h / 2;
    vb = { x: cx - (cx - vb.x) * nw / vb.w, y: cy - (cy - vb.y) * nw / vb.w, w: nw, h: nw * aspect };
    redraw();
  }
  const toSvg = (cx, cy) => { const r = svg.getBoundingClientRect(); return [vb.x + (cx - r.left) / r.width * vb.w, vb.y + (cy - r.top) / r.height * vb.h]; };

  svg.addEventListener("wheel", e => { e.preventDefault(); const [x, y] = toSvg(e.clientX, e.clientY); zoomAt(e.deltaY > 0 ? 1.18 : 0.85, x, y); }, { passive: false });
  const ptrs = new Map(); let start = null, moved = false, pinch = null;
  svg.addEventListener("pointerdown", e => {
    svg.setPointerCapture(e.pointerId); ptrs.set(e.pointerId, [e.clientX, e.clientY]);
    if (ptrs.size === 1) { start = { x: e.clientX, y: e.clientY, vb: { ...vb }, target: e.target }; moved = false; }
    if (ptrs.size === 2) { const [a, b] = [...ptrs.values()]; pinch = { d: Math.hypot(a[0] - b[0], a[1] - b[1]), w: vb.w }; }
  });
  svg.addEventListener("pointermove", e => {
    if (!ptrs.has(e.pointerId)) return; ptrs.set(e.pointerId, [e.clientX, e.clientY]);
    if (ptrs.size === 2 && pinch) {
      const [a, b] = [...ptrs.values()]; const d = Math.hypot(a[0] - b[0], a[1] - b[1]);
      const [cx, cy] = toSvg((a[0] + b[0]) / 2, (a[1] + b[1]) / 2); zoomAt((pinch.w * pinch.d / d) / vb.w, cx, cy); moved = true; return;
    }
    if (!start) return;
    const r = svg.getBoundingClientRect();
    if (Math.abs(e.clientX - start.x) + Math.abs(e.clientY - start.y) > 5) moved = true;
    if (!moved) return;
    vb.x = start.vb.x - (e.clientX - start.x) / r.width * vb.w;
    vb.y = start.vb.y - (e.clientY - start.y) / r.height * vb.h;
    svg.setAttribute("viewBox", `${vb.x} ${vb.y} ${vb.w} ${vb.h}`);
  });
  function up(e) {
    ptrs.delete(e.pointerId); if (ptrs.size < 2) pinch = null;
    if (ptrs.size) return;
    const wasMoved = moved, tgt = start && start.target; start = null;
    if (wasMoved) return;
    if (picking) {
      const [x, y] = toSvg(e.clientX, e.clientY); picking = false; svg.classList.remove("picking"); opts.onPick(unproj(x, y)); return;
    }
    const g = tgt && tgt.closest && tgt.closest("[data-key]");
    if (g) opts.onSpot(g.dataset.key);
  }
  svg.addEventListener("pointerup", up); svg.addEventListener("pointercancel", up);
  if (window.ResizeObserver) new ResizeObserver(() => redraw()).observe(el);
  redraw();

  return {
    render(sp, key) { spots = sp; activeKey = key; drawPins(); },
    setUser(u) { user = u; drawUser(); },
    focus(lat, lng, z) {
      const [x, y] = proj(lat, lng); const w = z >= 15 ? 190 : 300;
      vb = { x: x - w / 2, y: y - w * aspect / 2, w, h: w * aspect }; redraw();
    },
    fit() { vb = { ...HOME }; redraw(); },
    startPick() { picking = true; svg.classList.add("picking"); },
    resize() { redraw(); }
  };
};
