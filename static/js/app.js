(function () {
  var form = document.getElementById("comic-form");
  var overlay = document.getElementById("loading");
  var msg = document.getElementById("loading-msg");
  if (!form || !overlay) return;

  var steps = ["Planning your panels...", "Writing captions and dialogue...", "Inking the illustrations...", "Laying out the page..."];
  form.addEventListener("submit", function () {
    var btn = form.querySelector("button[type=submit]");
    if (btn) { btn.disabled = true; btn.textContent = "Creating..."; }
    overlay.hidden = false;
    var i = 0;
    setInterval(function () { i = (i + 1) % steps.length; msg.textContent = steps[i]; }, 6000);
  });
  // Back/forward cache: never leave the page stuck in "loading"
  window.addEventListener("pageshow", function (e) { if (e.persisted) location.reload(); });
})();
