  /* ======================================================================
     partials/fiche.js — "¿Entra tu maleta en X?" dentro de la ficha
     (11/10/2026). La decisión la toma verdictFor(), de partials/verdict.js,
     la MISMA función que usa la home: acá solo se leen los campos, se pinta
     el resultado y se arma el enlace a la home con las mismas medidas.
     Lectura de campos idéntica a la home: un número > 0 o nada.
     ====================================================================== */
  var tryEls = ["try-a", "try-b", "try-c", "try-w"].map(function (id) { return document.getElementById(id); });
  var tryOut = document.getElementById("try-out");
  var tryV = document.getElementById("try-v");
  var tryD = document.getElementById("try-d");
  var tryAll = document.getElementById("try-all");

  if (tryOut && tryEls.every(Boolean)) {
    var tryHome = tryAll.getAttribute("href").split("?")[0];

    var readNum = function (el) {
      var raw = parseFloat(el.value);
      return isFinite(raw) && raw > 0 ? raw : null;
    };

    var tryRender = function () {
      var dims = [0, 1, 2].map(function (i) { return readNum(tryEls[i]); });
      var kg = readNum(tryEls[3]);
      var q = [];
      if (dims.some(function (d) { return d === null; })) {
        tryOut.className = "tryit__out";
        tryV.textContent = t("fiche_try_empty");
        tryD.innerHTML = "";
      } else {
        var v = verdictFor(OP, { cm: dims.slice().sort(function (x, y) { return y - x; }), kg: kg });
        tryOut.className = "tryit__out tryit__out--" + v.band;
        tryV.textContent = v.verdict;
        tryD.innerHTML = v.detail || "";
        q.push("l=" + round1(dims[0]), "w=" + round1(dims[1]), "h=" + round1(dims[2]));
      }
      if (kg !== null) q.push("kg=" + round1(kg));
      tryAll.setAttribute("href", tryHome + (q.length ? "?" + q.join("&") : ""));
    };

    /* mismo paso que la home: 1 cm y 0,5 kg; con Shift, 0,1 */
    var tryNudge = function (el, dir, fine) {
      var step = fine ? 0.1 : (el === tryEls[3] ? 0.5 : 1);
      var cur = parseFloat(el.value);
      if (!isFinite(cur)) cur = 0;
      var next = round1(cur + dir * step);
      el.value = String(next < 0 ? 0 : next);
      el.classList.remove("is-bump"); void el.offsetWidth; el.classList.add("is-bump");
      tryRender();
    };

    Array.prototype.forEach.call(document.querySelectorAll(".tryit .nudge"), function (btn) {
      btn.addEventListener("click", function () {
        tryNudge(document.getElementById(btn.getAttribute("data-nudge")), Number(btn.getAttribute("data-dir")), false);
      });
    });
    tryEls.forEach(function (el) {
      el.addEventListener("input", tryRender);
      el.addEventListener("keydown", function (e) {
        if (e.key !== "ArrowUp" && e.key !== "ArrowDown") return;
        e.preventDefault();
        tryNudge(el, e.key === "ArrowUp" ? 1 : -1, e.shiftKey);
      });
      el.addEventListener("wheel", function (e) {
        if (document.activeElement !== el) return;
        e.preventDefault();
        tryNudge(el, e.deltaY < 0 ? 1 : -1, e.shiftKey);
      }, { passive: false });
    });
    tryRender();
  }
