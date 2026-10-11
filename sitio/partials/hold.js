/* ======================================================================
   partials/hold.js — mantener apretada una flecha ▲▼ repite (11/10/2026).
   Tras medio segundo apretada, la flecha "se toca sola" cada 90 ms hasta
   que se suelta. Usa el mismo clic que un toque normal, así que la cuenta
   es exactamente la misma. El clic que el navegador manda al soltar se
   descarta, para no sumar un paso de más.
   ====================================================================== */
(function () {
  if (!window.PointerEvent) return;
  Array.prototype.forEach.call(document.querySelectorAll(".stepper .nudge"), function (btn) {
    var wait = null, rep = null, repeated = false, swallow = false;
    function stop() {
      clearTimeout(wait); clearInterval(rep); wait = rep = null;
      if (repeated) swallow = true;
      repeated = false;
    }
    btn.addEventListener("pointerdown", function (e) {
      if (e.button !== 0) return;
      swallow = false; repeated = false;
      wait = setTimeout(function () {
        rep = setInterval(function () { repeated = true; btn.click(); }, 90);
      }, 500);
    });
    ["pointerup", "pointerleave", "pointercancel"].forEach(function (ev) { btn.addEventListener(ev, stop); });
    btn.addEventListener("click", function (e) {
      if (e.isTrusted && swallow) { e.stopImmediatePropagation(); e.preventDefault(); swallow = false; }
    }, true);
    /* en el teléfono, apretar fijo no abre el menú de "copiar" */
    btn.addEventListener("contextmenu", function (e) { e.preventDefault(); });
  });
})();
