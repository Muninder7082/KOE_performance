// Boots the official Lighthouse renderer with the stored report data.
// The data sits in a non-executable <script type="application/json"> block, so the
// page needs no inline JavaScript (the Content-Security-Policy stays script-src 'self').
(function () {
  var el = document.getElementById("lhr-json");
  if (!el) return;
  window.__LIGHTHOUSE_JSON__ = JSON.parse(el.textContent);
  window.__initLighthouseReport__();
})();
