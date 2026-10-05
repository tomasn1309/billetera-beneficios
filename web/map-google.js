/* Adaptador Google Maps. Se activa cuando config.js define googleMapsKey.
   Si la key falta o falla, la página usa el mapa SVG (map-svg.js) como respaldo. */
(function () {
  const cfg = window.BB_CONFIG || {};
  if (!cfg.googleMapsKey) return;
  const svgFactory = window.BB_createMap;

  function loadApi() {
    return new Promise((resolve, reject) => {
      if (window.google?.maps) return resolve();
      const cb = "__bbMapsReady";
      window[cb] = () => resolve();
      window.gm_authFailure = () => reject(new Error("Google Maps rechazó la API key. Revisa que esté habilitada la Maps JavaScript API y que el dominio esté permitido."));
      const s = document.createElement("script");
      s.src = `https://maps.googleapis.com/maps/api/js?key=${encodeURIComponent(cfg.googleMapsKey)}&callback=${cb}&v=weekly&language=es&region=CL`;
      s.async = true; s.onerror = () => reject(new Error("No se pudo cargar Google Maps."));
      document.head.appendChild(s);
    });
  }

  const css = v => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
  const dark = () => matchMedia("(prefers-color-scheme: dark)").matches && document.documentElement.dataset.theme !== "light" || document.documentElement.dataset.theme === "dark";
  const LIGHT = [
    { elementType: "geometry", stylers: [{ color: "#eceef1" }] },
    { elementType: "labels.text.fill", stylers: [{ color: "#5a6475" }] },
    { elementType: "labels.text.stroke", stylers: [{ color: "#ffffff" }] },
    { featureType: "poi", stylers: [{ visibility: "off" }] },
    { featureType: "poi.park", elementType: "geometry", stylers: [{ visibility: "on" }, { color: "#dfe7dc" }] },
    { featureType: "road", elementType: "geometry", stylers: [{ color: "#ffffff" }] },
    { featureType: "road.highway", elementType: "geometry", stylers: [{ color: "#d9dde3" }] },
    { featureType: "transit", stylers: [{ visibility: "simplified" }] },
    { featureType: "water", elementType: "geometry", stylers: [{ color: "#bcd3e3" }] }
  ];
  const DARK = [
    { elementType: "geometry", stylers: [{ color: "#161d26" }] },
    { elementType: "labels.text.fill", stylers: [{ color: "#8b97a8" }] },
    { elementType: "labels.text.stroke", stylers: [{ color: "#0e131a" }] },
    { featureType: "poi", stylers: [{ visibility: "off" }] },
    { featureType: "road", elementType: "geometry", stylers: [{ color: "#232d3a" }] },
    { featureType: "road.highway", elementType: "geometry", stylers: [{ color: "#2c394a" }] },
    { featureType: "transit", stylers: [{ visibility: "simplified" }] },
    { featureType: "water", elementType: "geometry", stylers: [{ color: "#1f3a4e" }] }
  ];

  window.BB_createMap = async function (el, opts) {
    try { await loadApi(); }
    catch (err) {
      console.warn(err);
      const m = await svgFactory(el, opts);
      const note = document.querySelector("#mapNote");
      if (note) note.textContent = err.message + " Mostrando el mapa simple.";
      return m;
    }
    const g = google.maps;
    const HOME = { lat: -33.445, lng: -70.62 };
    const map = new g.Map(el, {
      center: HOME, zoom: 12, styles: dark() ? DARK : LIGHT,
      disableDefaultUI: true, zoomControl: true, gestureHandling: "greedy", clickableIcons: false
    });
    const info = new g.InfoWindow();
    let markers = [], userMarker = null, userHalo = null, picking = false;

    map.addListener("click", e => {
      if (!picking) return;
      picking = false; map.setOptions({ draggableCursor: null });
      opts.onPick({ lat: e.latLng.lat(), lng: e.latLng.lng() });
    });

    function icon(sp, act) {
      return {
        path: g.SymbolPath.CIRCLE, scale: act ? 12 : 9,
        fillColor: css("--" + sp.colorVar) || "#152030", fillOpacity: 1,
        strokeColor: "#ffffff", strokeWeight: 2.5
      };
    }
    return {
      render(spots, key) {
        markers.forEach(m => m.setMap(null)); markers = [];
        for (const sp of spots) {
          const act = sp.key === key;
          const m = new g.Marker({
            map, position: { lat: sp.lat, lng: sp.lng }, icon: icon(sp, act), zIndex: act ? 999 : 1,
            title: sp.items.map(b => b.descuento + " " + b.comercio).join(" / "),
            label: sp.items.length > 1 ? { text: String(sp.items.length), color: "#fff", fontSize: "11px", fontWeight: "700" } : null
          });
          m.addListener("click", () => { opts.onSpot(sp.key); });
          if (act) { info.setContent(window.BB_spotInfoHTML(sp)); info.open({ map, anchor: m }); }
          markers.push(m);
        }
        if (!spots.some(s => s.key === key)) info.close();
      },
      setUser(u) {
        if (userMarker) { userMarker.setMap(null); userHalo.setMap(null); userMarker = userHalo = null; }
        if (!u) return;
        userHalo = new g.Circle({ map, center: u, radius: 1000, strokeColor: css("--user"), strokeOpacity: .35, strokeWeight: 1, fillColor: css("--user"), fillOpacity: .07, clickable: false });
        userMarker = new g.Marker({ map, position: u, zIndex: 1000, title: "Tú", icon: { path: g.SymbolPath.CIRCLE, scale: 8, fillColor: css("--user"), fillOpacity: 1, strokeColor: "#fff", strokeWeight: 3 } });
      },
      focus(lat, lng, z) { map.panTo({ lat, lng }); map.setZoom(z || 14); },
      fit() { map.setCenter(HOME); map.setZoom(12); },
      startPick() { picking = true; map.setOptions({ draggableCursor: "crosshair" }); },
      resize() { g.event.trigger(map, "resize"); }
    };
  };
})();
