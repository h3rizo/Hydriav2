/*
 * Phase C - formulaire de saisie guidee.
 * Se greffe sur templates/accounting/saisie_workflow.html.
 * Quand le compte cat selectionne a une RegleSaisieCompte, affiche un mini-form
 * (champs pilotes par la config) et compose automatiquement :
 *   #description, #fournisseur, #detail, #activ, #fin  + verrouille In/Out selon le sens.
 * Lit la globale COMPTES de la page (identifiant nu, comme prefill_saisie.js).
 * Endpoints : /comptabilite/regles-saisie/api/{pour-compte,composer,autocomplete}/
 *             (fallback /regles-saisie/api/... pour le sous-domaine compta)
 */
(function () {
  "use strict";

  var API = ["/comptabilite/regles-saisie/api/", "/regles-saisie/api/"];

  function CX() { return (typeof COMPTES !== "undefined" && Array.isArray(COMPTES)) ? COMPTES : []; }
  function el(id) { return document.getElementById(id); }
  function csrf() { var e = document.querySelector("[name=csrfmiddlewaretoken]"); return e ? e.value : ""; }
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  function api(path, init, i) {
    i = i || 0;
    return fetch(API[i] + path, init).then(function (r) {
      if (r.status === 404 && i + 1 < API.length) return api(path, init, i + 1);
      return r.json();
    });
  }

  var host = null;
  var state = { code: "", regle: null, valeurs: {}, labelToId: {}, timer: null };

  function compteCode() {
    var id = (el("compte_id") || {}).value || "";
    var c = CX().find(function (x) { return x.id === id; });
    return c ? (c.compte || "") : "";
  }

  function setVal(id, v) {
    var e = el(id);
    if (!e || v == null || v === "") return;
    e.value = v;
    e.dispatchEvent(new Event("input", { bubbles: true }));
    e.dispatchEvent(new Event("change", { bubbles: true }));
  }

  function lockMontants(sens) {
    var inp = el("montant_in"), out = el("montant_out");
    if (!inp || !out) return;
    [inp, out].forEach(function (e) { e.disabled = false; e.classList.remove("input-disabled"); });
    if (sens === "in") { out.value = ""; out.disabled = true; out.classList.add("input-disabled"); }
    else if (sens === "out") { inp.value = ""; inp.disabled = true; inp.classList.add("input-disabled"); }
  }
  function unlockMontants() {
    [el("montant_in"), el("montant_out")].forEach(function (e) {
      if (e) { e.disabled = false; e.classList.remove("input-disabled"); }
    });
  }

  // Le sens par defaut de la regle peut etre surcharge par un champ (ex: select
  // "Avance / Remboursement" avec sortie:"sens" sur le compte 00PERS) : le badge
  // et le verrouillage In/Out doivent donc suivre le sens COMPOSE, pas seulement
  // le sens statique de la regle.
  function updateSensBadge(sens) {
    var b = el("sg-sens-badge");
    if (!b) return;
    b.className = "badge badge-sm " + (sens === "in" ? "badge-success" : "badge-error");
    b.textContent = sens === "in" ? "Recette (In)" : "Depense (Out)";
  }

  // ---- visibilite conditionnelle (visible_si: "cible==ouvrage", "!prestation", ...) ----
  function condOk(expr) {
    if (!expr) return true;
    expr = String(expr).trim();
    var neg = expr.charAt(0) === "!";
    if (neg) expr = expr.slice(1).trim();
    var res;
    if (expr.indexOf("==") >= 0) {
      var a = expr.split("==");
      res = String(state.valeurs[a[0].trim()] || "") === a[1].trim();
    } else if (expr.indexOf("!=") >= 0) {
      var b = expr.split("!=");
      res = String(state.valeurs[b[0].trim()] || "") !== b[1].trim();
    } else {
      res = !!state.valeurs[expr];
    }
    return neg ? !res : res;
  }

  function applyVisibility() {
    var champs = (state.regle && state.regle.config && state.regle.config.champs) || [];
    champs.forEach(function (ch) {
      var wrap = el("sgw-" + ch.code);
      if (wrap) wrap.hidden = !condOk(ch.visible_si);
    });
  }

  // ---- rendu d'un champ ----
  var AC = { fournisseur_ac: "fournisseur", ouvrage_ac: "ouvrage", employe_ac: "employe", vehicule_ac: "vehicule" };

  function champHtml(ch) {
    if (ch.type === "prestation" && ch.fixe === true) return "";        // force -> pas d'UI
    if (ch.type === "fixe") return "";                                  // valeur constante -> pas d'UI
    var label = esc(ch.label || ch.code) + (ch.obligatoire ? ' <span class="text-error">*</span>' : "");
    var inner;
    if (AC[ch.type]) {
      inner = '<input id="sg-' + ch.code + '" list="sgdl-' + ch.code + '" class="input input-bordered input-sm w-full" autocomplete="off" placeholder="Rechercher...">'
        + '<datalist id="sgdl-' + ch.code + '"></datalist>';
    } else if (ch.type === "select") {
      inner = '<select id="sg-' + ch.code + '" class="select select-bordered select-sm w-full">'
        + '<option value="">--</option>'
        + (ch.options || []).map(function (o) { return '<option value="' + esc(o.val) + '">' + esc(o.val) + "</option>"; }).join("")
        + "</select>";
    } else if (ch.type === "nombre") {
      inner = '<input id="sg-' + ch.code + '" type="number" step="any" class="input input-bordered input-sm w-full">';
    } else if (ch.type === "prestation") {
      inner = '<label class="cursor-pointer flex items-center gap-2"><input id="sg-' + ch.code + '" type="checkbox" class="checkbox checkbox-sm"> <span class="text-xs">oui</span></label>';
    } else if (ch.type === "mois_annee" || ch.type === "date_jour1") {
      inner = '<input id="sg-' + ch.code + '" type="month" class="input input-bordered input-sm w-full">';
    } else if (ch.type === "annee") {
      inner = '<input id="sg-' + ch.code + '" type="number" min="2000" max="2100" class="input input-bordered input-sm w-full" placeholder="2026">';
    } else {
      inner = '<input id="sg-' + ch.code + '" type="text" class="input input-bordered input-sm w-full">';
    }
    return '<div id="sgw-' + ch.code + '" class="form-control"><label class="label py-0"><span class="label-text text-xs">'
      + label + "</span></label>" + inner + "</div>";
  }

  function readChamp(ch) {
    var e = el("sg-" + ch.code);
    if (!e) return "";
    if (ch.type === "prestation") return e.checked;
    if (ch.type === "mois_annee" || ch.type === "date_jour1") return e.value ? e.value.replace("-", " ") : "";  // 2026-09 -> "2026 09"
    if (AC[ch.type]) {
      var id = state.labelToId[ch.code + "::" + e.value];
      return id || "";
    }
    return e.value;
  }

  function wireChamp(ch) {
    var e = el("sg-" + ch.code);
    if (!e) return;
    function onChange() {
      state.valeurs[ch.code] = readChamp(ch);
      applyVisibility();
      schedule();
    }
    e.addEventListener("input", onChange);
    e.addEventListener("change", onChange);   // <input month>, <select>, checkbox
    if (AC[ch.type]) {
      e.addEventListener("input", function () { acSearch(ch, e.value); });
      acSearch(ch, "");
    }
  }

  function acSearch(ch, q) {
    var params = "kind=" + AC[ch.type] + "&q=" + encodeURIComponent(q || "") + "&compte=" + encodeURIComponent(state.code);
    if (ch.filtre_poste) params += "&filtre_poste=" + encodeURIComponent(ch.filtre_poste);
    if (ch.filtre) params += "&filtre=" + encodeURIComponent(ch.filtre);
    api("autocomplete/?" + params, { credentials: "same-origin" })
      .then(function (d) {
        var dl = el("sgdl-" + ch.code);
        if (!dl || !d || !d.items) return;
        dl.innerHTML = "";
        d.items.forEach(function (it) {
          state.labelToId[ch.code + "::" + it.label] = it.id;
          var o = document.createElement("option");
          o.value = it.label;
          dl.appendChild(o);
        });
      })
      .catch(function () {});
  }

  // ---- composition ----
  function schedule() {
    if (state.timer) clearTimeout(state.timer);
    state.timer = setTimeout(recompose, 300);
  }

  function recompose() {
    if (!state.regle) return;
    var code = state.code;
    api("composer/", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRFToken": csrf() },
      credentials: "same-origin",
      body: JSON.stringify({ compte: code, valeurs: state.valeurs }),
    }).then(function (d) {
      if (code !== state.code || !d || !d.resultat) return;
      var r = d.resultat;
      setVal("description", r.description);
      setVal("fournisseur", r.fournisseur);
      setVal("detail", r.detail);
      setVal("activ", r.activ);
      setVal("fin", r.fin);
      lockMontants(r.sens);
      updateSensBadge(r.sens);
      var ap = el("sg-apercu");
      if (ap) {
        ap.textContent = r.description || "(description vide - completer les champs)";
        if (r.warnings && r.warnings.length) ap.textContent += "   ⚠ " + r.warnings.join(" · ");
      }
    }).catch(function () {});
  }

  // ---- rendu du panneau ----
  function render() {
    if (!host) return;
    var r = state.regle;
    if (!r) { host.innerHTML = ""; host.hidden = true; unlockMontants(); return; }
    host.hidden = false;
    var champs = (r.config && r.config.champs) || [];
    var grid = champs.map(champHtml).join("");
    host.innerHTML =
      '<div class="rounded-xl border border-primary/40 bg-primary/5 p-3 mt-2">'
      + '<div class="flex flex-wrap items-center justify-between gap-2 mb-2">'
      + '<span class="text-sm font-semibold text-primary"><i class="fas fa-wand-magic-sparkles mr-1"></i>Saisie guidee &mdash; '
      + esc(r.libelle || r.compte_cible) + "</span>"
      + '<span id="sg-sens-badge" class="badge badge-sm ' + (r.sens === "in" ? "badge-success" : "badge-error") + '">'
      + (r.sens === "in" ? "Recette (In)" : "Depense (Out)") + "</span>"
      + "</div>"
      + '<div class="grid grid-cols-1 md:grid-cols-2 gap-2">' + grid + "</div>"
      + '<div class="mt-2"><span class="label-text text-xs opacity-60">Description composee</span>'
      + '<div id="sg-apercu" class="text-xs font-mono bg-base-200 rounded p-2 mt-1 break-all"></div></div>'
      + "</div>";
    // valeurs fixes -> etat initial
    state.valeurs = {};
    champs.forEach(function (ch) {
      if (ch.fixe != null && ch.type === "fixe") state.valeurs[ch.code] = ch.fixe;
      if (ch.type === "prestation" && ch.fixe === true) state.valeurs[ch.code] = true;
    });
    champs.forEach(wireChamp);
    applyVisibility();
    lockMontants(r.sens);
    recompose();
  }

  function onCompteChange() {
    var code = compteCode();
    if (code === state.code) return;
    state.code = code;
    state.regle = null;
    state.labelToId = {};
    if (!code) { render(); return; }
    api("pour-compte/?compte=" + encodeURIComponent(code), { credentials: "same-origin" })
      .then(function (d) {
        if (compteCode() !== code) return;
        state.regle = (d && d.regle) ? d.regle : null;
        render();
      })
      .catch(function () { state.regle = null; render(); });
  }

  function init() {
    var anchor = el("compte-hints");
    if (!anchor || !el("compte_id")) return;
    host = document.createElement("div");
    host.id = "saisie-guidee";
    host.hidden = true;
    anchor.parentNode.insertBefore(host, anchor.nextSibling);
    el("compte_id").addEventListener("change", onCompteChange);
    onCompteChange();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
