/* Adaptador Leaflet + OpenStreetMap (gratis, sin API key). Es el mapa por defecto de la web.
   Si Leaflet no cargó, queda el mapa SVG; si config.js trae googleMapsKey, map-google.js lo reemplaza. */
(function () {
  if (!window.L) return;
  const svgFactory = window.BB_createMap;
  const css = v => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
  const isDark = () => {
    const t = document.documentElement.dataset.theme;
    return t === "dark" || (t !== "light" && matchMedia("(prefers-color-scheme: dark)").matches);
  };
  const TILES = {
    light: "https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png",
    dark: "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
  };
  const ATTR = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &copy; <a href="https://carto.com/attributions">CARTO</a>';

  window.BB_createMap = async function (el, opts) {
    let map;
    try {
      el.innerHTML = "";
      map = L.map(el, { zoomControl: true, attributionControl: true }).setView([-33.445, -70.62], 12);
    } catch (err) {
      return svgFactory(el, opts);
    }
    let tiles = L.tileLayer(isDark() ? TILES.dark : TILES.light, { attribution: ATTR, subdomains: "abcd", maxZoom: 19 }).addTo(map);
    matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => tiles.setUrl(isDark() ? TILES.dark : TILES.light));

    const layer = L.layerGroup().addTo(map);
    let userLayer = null, picking = false;
    map.on("click", e => {
      if (!picking) return;
      picking = false; el.style.cursor = "";
      opts.onPick({ lat: e.latlng.lat, lng: e.latlng.lng });
    });

    return {
      render(spots, key) {
        layer.clearLayers();
        for (const sp of spots) {
          const act = sp.key === key;
          const m = L.circleMarker([sp.lat, sp.lng], {
            radius: act ? 12 : 8, color: "#ffffff", weight: 2.5,
            fillColor: css("--" + sp.colorVar), fillOpacity: 1
          }).addTo(layer);
          if (sp.items.length > 1) {
            L.marker([sp.lat, sp.lng], {
              interactive: false,
              icon: L.divIcon({ className: "bb-count", html: String(sp.items.length), iconSize: [16, 16] })
            }).addTo(layer);
          }
          m.on("click", () => opts.onSpot(sp.key));
          if (act) {
            m.bindPopup(window.BB_spotInfoHTML(sp), { maxWidth: 280 }).openPopup();
            m.bringToFront();
          }
        }
      },
      setUser(u) {
        if (userLayer) { userLayer.remove(); userLayer = null; }
        if (!u) return;
        const c = css("--user");
        userLayer = L.layerGroup([
          L.circle([u.lat, u.lng], { radius: 1000, color: c, weight: 1, opacity: .4, fillColor: c, fillOpacity: .07, interactive: false }),
          L.circleMarker([u.lat, u.lng], { radius: 8, color: "#ffffff", weight: 3, fillColor: c, fillOpacity: 1 }).bindTooltip("Tú")
        ]).addTo(map);
      },
      focus(lat, lng, z) { map.setView([lat, lng], z || 14); },
      fit() { map.setView([-33.445, -70.62], 12); },
      startPick() { picking = true; el.style.cursor = "crosshair"; },
      resize() { setTimeout(() => map.invalidateSize(), 50); }
    };
  };
})();
