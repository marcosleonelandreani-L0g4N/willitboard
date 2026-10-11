/* ======================================================================
   partials/nogo.js — banner chico de "qué no se puede llevar" con flechas
   (11/10/2026). Lo usan la home y las fichas de aerolíneas europeas.
   La lista se desliza sola con el dedo (scroll-snap); este script agrega
   las flechas, los puntos y la vuelta al principio. Sin script, la lista
   sigue siendo deslizable y se lee entera.
   ====================================================================== */
(function () {
  var reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  Array.prototype.forEach.call(document.querySelectorAll(".nogo-c__track"), function (track) {
    var idp = track.id.replace(/-track$/, "");
    var items = Array.prototype.slice.call(track.children);
    var dots = document.getElementById(idp + "-dots");
    var label = dots ? dots.getAttribute("data-label") : "";
    if (!items.length) return;

    function perView() {
      var w = items[0].getBoundingClientRect().width;
      return w > 0 ? Math.max(1, Math.round(track.clientWidth / w)) : 1;
    }
    function pages() { return Math.ceil(items.length / perView()); }
    function pageLeft(n) { return items[n * perView()].offsetLeft - items[0].offsetLeft; }
    function current() {
      var P = pages(), best = 0, dist = Infinity;
      for (var n = 0; n < P; n++) {
        var d = Math.abs(track.scrollLeft - pageLeft(n));
        if (d < dist) { dist = d; best = n; }
      }
      return best;
    }
    function go(n) {
      var P = pages();
      n = (n + P) % P;
      track.scrollTo({ left: pageLeft(n), behavior: reduce ? "auto" : "smooth" });
      paint(n);
    }
    function paint(active) {
      if (!dots) return;
      var P = pages(), c = active === undefined ? current() : active;
      if (dots.children.length !== P) {
        dots.innerHTML = "";
        for (var n = 0; n < P; n++) {
          var b = document.createElement("button");
          b.type = "button";
          b.className = "nogo-c__dot";
          b.setAttribute("aria-label", label.replace("{n}", n + 1).replace("{total}", P));
          b.addEventListener("click", (function (k) { return function () { go(k); }; })(n));
          dots.appendChild(b);
        }
      }
      Array.prototype.forEach.call(dots.children, function (b, i) {
        if (i === c) b.setAttribute("aria-current", "true"); else b.removeAttribute("aria-current");
      });
    }
    Array.prototype.forEach.call(document.querySelectorAll('[data-nogo="' + idp + '"]'), function (btn) {
      btn.addEventListener("click", function () { go(current() + Number(btn.getAttribute("data-dir"))); });
    });
    var pending = false;
    track.addEventListener("scroll", function () {
      if (pending) return;
      pending = true;
      requestAnimationFrame(function () { pending = false; paint(); });
    });
    window.addEventListener("resize", function () { paint(); });
    paint();
  });
})();
