  /* ======================================================================
     partials/verdict.js — LA cuenta de "¿entra?", compartida (11/10/2026).
     build_site.py la inyecta tal cual en la home (template.html) y en cada
     ficha (template_operator.html). Así una misma maleta da el mismo
     resultado en las dos páginas: no hay una segunda copia que se desfase.
     Usa del entorno: t(), round1(), units, IN_PER_CM.
     ====================================================================== */
  /* ---------- the comparison ----------
     El idioma NO toca esta parte. Un mismo equipaje tiene que dar el mismo
     estado en las dos versiones: lo único que cambia es el texto. */

  var FITS = "fits", MAYBE = "maybe", OVER = "over", UNKNOWN = "unknown", RULE = "rule";

  function limitTriple(maxCm) {
    if (!maxCm) return null;
    var v = [maxCm.length, maxCm.width, maxCm.height];
    if (v.some(function (n) { return n === null || n === undefined; })) return null;
    return v.sort(function (x, y) { return y - x; });
  }

  /* Compares sorted bag dims against sorted limit dims. Sorting both means a bag
     that only fits rotated still counts as fitting, which is how a sizer works.
     Tolerance is never treated as a pass: if the bag only clears the limit by
     borrowing the wheel allowance, the honest answer is "maybe, go and re-measure". */
  function compareDims(bagCm, limit, wheels) {
    if (!limit) return { state: UNKNOWN };
    var over = [];
    for (var i = 0; i < 3; i++) {
      var excess = round1(bagCm[i] - limit[i]);
      if (excess > 0) over.push({ axis: i, excess: excess });
    }
    if (!over.length) return { state: FITS };

    var tolerance = wheels && wheels.included_in_measurement === false
      ? wheels.tolerance_cm : null;
    if (tolerance !== null && tolerance !== undefined) {
      var rescued = over.every(function (o) { return o.excess <= tolerance; });
      if (rescued) {
        return {
          state: MAYBE,
          by: Math.max.apply(null, over.map(function (o) { return o.excess; })),
          tolerance: tolerance
        };
      }
    }
    return { state: OVER, by: Math.max.apply(null, over.map(function (o) { return o.excess; })) };
  }

  function compareWeight(bagKg, maxKg) {
    if (maxKg === null || maxKg === undefined) return UNKNOWN;
    if (bagKg === null) return UNKNOWN;
    return bagKg <= maxKg ? FITS : OVER;
  }

  function isNum(v) { return v !== null && v !== undefined; }

  /* Peso combinado (esquema 1.4, 26/09/2026). Si el operador publica peso
     para ESTE bulto, vale ese. Si solo publica un peso para los dos bultos
     juntos, se compara contra ese total: una maleta sola que pesa más que el
     total no entra, pase lo que pase con el otro bulto. Nunca se reparte el
     total entre los bultos: esa cifra el operador no la publicó. */
  function assess(allowance, b, wheels, combinedKg) {
    if (!allowance) return null;
    var dims = compareDims(b.cm, limitTriple(allowance.max_cm), wheels);
    var shared = !isNum(allowance.max_kg) && isNum(combinedKg);
    var maxKg = shared ? combinedKg : (isNum(allowance.max_kg) ? allowance.max_kg : null);
    var weight = compareWeight(b.kg, maxKg);
    return { dims: dims, weight: weight, allowance: allowance, maxKg: maxKg, shared: shared };
  }

  function fmtCm(maxCm) {
    return [maxCm.length, maxCm.width, maxCm.height].join(" × ") + " cm";
  }

  function fmtLen(cm) {
    return units.length === "in" ? round1(cm * IN_PER_CM) + " in" : round1(cm) + " cm";
  }

  function kgSuffix(res) {
    if (!isNum(res.maxKg)) return "";
    return res.shared ? t("kg_suffix_shared", { kg: res.maxKg }) : t("kg_suffix", { kg: res.maxKg });
  }

  /* Datos para el gráfico: la maleta del usuario contra la franquicia que se evaluó. */
  function mkCompare(bagCm, res, label) {
    var limit = limitTriple(res.allowance.max_cm);
    if (!limit) return null;
    /* allowance viaja solo para mostrar la ficha; no interviene en el veredicto */
    return { bag: bagCm, limit: limit, label: label, allowance: res.allowance,
             maxKg: res.maxKg, shared: res.shared };
  }

  function pushShared(out, op, res) {
    if (res && res.shared) {
      out.flags.push({ tone: "band", text: t("flag_combined", { name: op.name, kg: res.maxKg }) });
    }
  }

  /* Decides the band and builds the human sentences for one operator. */
  function verdictFor(op, b) {
    var out = { op: op, flags: [] };

    /* Reglas descriptivas: el operador describe qué podés llevar sin dar medidas.
       Es un estado propio, distinto de "no tenemos el dato": acá sí hay información
       oficial, solo que no es un número. Nunca se convierte en un veredicto.
       La cita se muestra SIEMPRE en su idioma original, sin traducir. */
    if (op.limit_type !== "dimensional") {
      var dr = op.descriptive_rule || {};
      var ruleText = dr.en || dr.es || null;
      var ruleLang = dr.en ? "en" : (dr.es ? "es" : null);
      if (ruleText) {
        out.band = RULE;
        out.verdict = t("band_rule_title");
        out.detail = t("d_rule");
        out.rule = ruleText;
        out.ruleLang = ruleLang;
      } else {
        out.band = UNKNOWN;
        out.verdict = t("band_unknown_title");
        out.detail = t("d_unknown");
      }
      return out;
    }

    var wheels = op.wheels_handles || {};
    var combined = isNum(op.combined_max_kg) ? op.combined_max_kg : null;
    var personal = assess(op.personal_item, b, wheels, combined);
    var cabin = assess(op.cabin_bag, b, wheels, combined);

    /* wheels caveat applies to every dimensional result */
    if (wheels.included_in_measurement === true) {
      out.flags.push({ tone: "neutral", text: t("flag_wheels_included") });
    } else if (wheels.included_in_measurement === false) {
      out.flags.push({
        tone: "neutral",
        text: (wheels.tolerance_cm !== null && wheels.tolerance_cm !== undefined)
          ? t("flag_wheels_excluded_tol", { tol: wheels.tolerance_cm })
          : t("flag_wheels_excluded")
      });
    } else {
      out.flags.push({ tone: "neutral", text: t("flag_wheels_unknown") });
    }

    /* La tarifa a la que corresponden las cifras (esquema 1.4). Nombre
       comercial del operador, sin traducir. Si no está confirmada, no se
       muestra nada: el aviso genérico de tarifas vive en la ficha. */
    if (op.reference_fare) {
      out.flags.push({ tone: "info", text: t("flag_fare", { fare: op.reference_fare }) });
    }

    var candidates = [];
    if (personal) candidates.push({ kind: "personal", label: t("label_personal"), res: personal });
    if (cabin) candidates.push({ kind: "cabin", label: t("label_cabin"), res: cabin });

    /* prefer an included allowance that fits outright */
    var best = null;
    candidates.forEach(function (c) {
      var included = c.res.allowance.included === true;
      var fits = c.res.dims.state === FITS && c.res.weight !== OVER;
      if (fits && included && !best) best = c;
    });
    if (best) {
      out.band = FITS;
      out.verdict = t("band_pass_title");
      out.detail = t("d_fits", {
        label: best.label,
        dims: fmtCm(best.res.allowance.max_cm),
        kg: kgSuffix(best.res)
      });
      if (best.res.weight === UNKNOWN && !isNum(best.res.maxKg)) {
        out.flags.push({ tone: "band", text: t("flag_no_weight") });
      }
      pushShared(out, op, best.res);
      out.compare = mkCompare(b.cm, best.res, best.label);
      return out;
    }

    /* then an allowance that fits but has to be bought */
    var paid = null;
    candidates.forEach(function (c) {
      var fits = c.res.dims.state === FITS && c.res.weight !== OVER;
      if (fits && c.res.allowance.included === false && !paid) paid = c;
    });
    if (paid) {
      out.band = "paid";
      out.verdict = t("band_paid_title");
      out.detail = t("d_paid", {
        label: paid.label,
        dims: fmtCm(paid.res.allowance.max_cm),
        kg: kgSuffix(paid.res)
      });
      if (paid.res.allowance.requires_addon) {
        out.flags.push({ tone: "band", text: t("flag_addon", { addon: paid.res.allowance.requires_addon }) });
      }
      pushShared(out, op, paid.res);
      out.compare = mkCompare(b.cm, paid.res, paid.label);
      return out;
    }

    /* then a maybe, rescued only by the wheel tolerance */
    var maybe = null;
    candidates.forEach(function (c) {
      if (c.res.dims.state === MAYBE && c.res.weight !== OVER && !maybe) maybe = c;
    });
    if (maybe) {
      out.band = UNKNOWN;
      out.verdict = t("v_wheels");
      out.detail = t("d_maybe", {
        by: fmtLen(maybe.res.dims.by),
        label: maybe.label,
        dims: fmtCm(maybe.res.allowance.max_cm)
      });
      out.flags.push({
        tone: "band",
        text: t("flag_maybe", { tol: maybe.res.dims.tolerance }) +
          (maybe.res.allowance.included === false && maybe.res.allowance.requires_addon
            ? t("flag_maybe_addon", { addon: maybe.res.allowance.requires_addon })
            : "")
      });
      pushShared(out, op, maybe.res);
      out.compare = mkCompare(b.cm, maybe.res, maybe.label);
      return out;
    }

    /* anything unresolvable for lack of published data */
    var missing = candidates.filter(function (c) { return c.res.dims.state === UNKNOWN; });
    if (missing.length === candidates.length && candidates.length) {
      out.band = UNKNOWN;
      out.verdict = t("band_unknown_title");
      out.detail = t("d_unknown");
      return out;
    }

    /* otherwise it's over */
    out.band = OVER;
    out.verdict = t("band_fail_title");
    var biggest = candidates.filter(function (c) { return c.res.allowance.max_cm; })
      .sort(function (x, y) {
        var lx = limitTriple(x.res.allowance.max_cm), ly = limitTriple(y.res.allowance.max_cm);
        return (ly ? ly[0] : 0) - (lx ? lx[0] : 0);
      })[0];

    if (biggest) {
      var overWeight = biggest.res.weight === OVER;
      var overDims = biggest.res.dims.state === OVER;
      var dims = fmtCm(biggest.res.allowance.max_cm);
      if (overDims && overWeight) {
        out.detail = t("d_over_both", {
          dims: dims, by: fmtLen(biggest.res.dims.by), kg: biggest.res.maxKg
        });
      } else if (overWeight) {
        out.detail = t("d_over_weight", {
          label: biggest.label, dims: dims, kg: biggest.res.maxKg
        });
      } else {
        out.detail = t("d_over_dims", { dims: dims, by: fmtLen(biggest.res.dims.by) });
      }
      if (overWeight) pushShared(out, op, biggest.res);
      out.compare = mkCompare(b.cm, biggest.res, biggest.label);
    } else {
      out.detail = t("d_over_generic");
    }
    return out;
  }


