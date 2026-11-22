/* Leaflet helpers: display maps + the collection-form GPS picker. */
(function () {
  "use strict";
  var TILE_URL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png";
  var ATTRIBUTION = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors';

  function emptyState(el, text) {
    el.innerHTML = '<div class="map-empty"><div><i class="bi bi-geo-alt fs-2"></i><p class="mb-0 mt-2">' + text + "</p></div></div>";
  }

  function baseMap(el, center, zoom) {
    if (typeof L === "undefined") { emptyState(el, "The map library could not be loaded. Check your internet connection."); return null; }
    var map = L.map(el, { scrollWheelZoom: false }).setView(center, zoom);
    L.tileLayer(TILE_URL, { maxZoom: 19, attribution: ATTRIBUTION }).addTo(map);
    return map;
  }

  function esc(s) { var d = document.createElement("div"); d.textContent = s == null ? "" : String(s); return d.innerHTML; }

  // <div class="map-box" data-markers-id="markers-json">
  window.initDisplayMaps = function () {
    document.querySelectorAll("[data-markers-id]").forEach(function (el) {
      var node = document.getElementById(el.dataset.markersId);
      var markers = node ? JSON.parse(node.textContent) : [];
      if (!markers.length) { emptyState(el, "No GPS coordinates were recorded, so no exact location is shown."); return; }
      var map = baseMap(el, [markers[0].lat, markers[0].lng], 12);
      if (!map) return;
      var group = [];
      markers.forEach(function (m) {
        var note = m.source ? "<br><small>Coordinates: " + esc(m.source) + (m.accuracy ? " (±" + esc(m.accuracy) + " m)" : "") + "</small>" : "";
        var marker = L.marker([m.lat, m.lng]).addTo(map)
          .bindPopup("<strong>" + esc(m.title) + "</strong><br>" + esc(m.detail) + note);
        group.push(marker);
      });
      if (group.length > 1) map.fitBounds(L.featureGroup(group).getBounds().pad(0.3));
      else group[0].openPopup();
    });
  };

  // Collection form picker
  window.initCollectionPicker = function (regions) {
    var el = document.getElementById("pick-map");
    if (!el) return;
    var latInput = document.getElementById("id_latitude");
    var lngInput = document.getElementById("id_longitude");
    var srcInput = document.getElementById("id_coordinate_source");
    var accInput = document.getElementById("id_gps_accuracy_m");
    var status = document.getElementById("gps-status");
    var btn = document.getElementById("gps-capture");

    var start = [22.7196, 75.8577]; // fallback view only; nothing is submitted from it
    var map = baseMap(el, start, 5);
    if (!map) return;
    var marker = null;

    (regions || []).forEach(function (r) {
      L.circle([r.lat, r.lng], { radius: r.radius_km * 1000, color: "#1f9d6b", weight: 2, fillOpacity: 0.08 })
        .addTo(map).bindTooltip("Approved region: " + r.name);
    });

    function setStatus(text, kind) {
      status.className = "small mt-2 " + (kind === "bad" ? "text-danger" : kind === "ok" ? "text-success" : "text-muted-2");
      status.textContent = text;
    }

    function place(lat, lng, source, accuracy, zoom) {
      if (marker) marker.setLatLng([lat, lng]); else marker = L.marker([lat, lng], { draggable: true }).addTo(map);
      marker.off("dragend").on("dragend", function () {
        var p = marker.getLatLng(); setFields(p.lat, p.lng, "MANUAL", "");
        setStatus("Pin moved: coordinates will be saved as entered manually.", "info");
      });
      map.setView([lat, lng], zoom || Math.max(map.getZoom(), 13));
    }

    function setFields(lat, lng, source, accuracy) {
      latInput.value = Number(lat).toFixed(6);
      lngInput.value = Number(lng).toFixed(6);
      srcInput.value = source;
      accInput.value = accuracy === "" || accuracy == null ? "" : Math.round(accuracy);
    }

    btn.addEventListener("click", function () {
      if (!("geolocation" in navigator)) { setStatus("This browser has no Geolocation API. Enter coordinates manually or click the map.", "bad"); return; }
      btn.disabled = true; setStatus("Requesting your location…", "info");
      navigator.geolocation.getCurrentPosition(function (pos) {
        btn.disabled = false;
        setFields(pos.coords.latitude, pos.coords.longitude, "GPS", pos.coords.accuracy);
        place(pos.coords.latitude, pos.coords.longitude, "GPS", pos.coords.accuracy, 15);
        setStatus("Location captured by device GPS (accuracy ±" + Math.round(pos.coords.accuracy) + " m).", "ok");
      }, function (err) {
        btn.disabled = false;
        var why = err.code === 1 ? "Location permission was denied." : err.code === 3 ? "The location request timed out." : "Your position is unavailable.";
        setStatus(why + " Enter latitude and longitude manually below, or click the map.", "bad");
      }, { enableHighAccuracy: true, timeout: 15000, maximumAge: 0 });
    });

    map.on("click", function (e) {
      setFields(e.latlng.lat, e.latlng.lng, "MANUAL", "");
      place(e.latlng.lat, e.latlng.lng, "MANUAL", "");
      setStatus("Point chosen on the map: saved as entered manually.", "info");
    });

    function fromInputs() {
      var lat = parseFloat(latInput.value), lng = parseFloat(lngInput.value);
      if (isNaN(lat) || isNaN(lng) || lat < -90 || lat > 90 || lng < -180 || lng > 180) return;
      srcInput.value = "MANUAL"; accInput.value = "";
      place(lat, lng, "MANUAL", "", 14);
      setStatus("Manual coordinates shown on the map.", "info");
    }
    latInput.addEventListener("change", fromInputs);
    lngInput.addEventListener("change", fromInputs);
    if (latInput.value && lngInput.value) {
      var lat0 = parseFloat(latInput.value), lng0 = parseFloat(lngInput.value);
      if (!isNaN(lat0) && !isNaN(lng0)) place(lat0, lng0, srcInput.value || "MANUAL", "", 14);
    }
  };

  document.addEventListener("DOMContentLoaded", window.initDisplayMaps);
})();
