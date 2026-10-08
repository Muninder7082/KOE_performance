// Sends the browser to Google's Lighthouse Viewer with the stored report in the URL fragment.
(function () {
  var el = document.getElementById("viewer-url");
  if (el) window.location.replace(JSON.parse(el.textContent));
})();
