/*
 * Phase 5 - pre-remplissage IA du formulaire de saisie comptable.
 * Se greffe sur templates/accounting/saisie_workflow_compta.html.
 * Utilise les globales de la page : JOURNAUX, COMPTES, FOURNISSEURS, renderFeedback().
 * Endpoint : POST /comptabilite/justificatifs/scan/  (fichier scan OU {texte, base_id}).
 */
(function () {
  "use strict";

  // www.hydria.mg -> /comptabilite/justificatifs/scan/ ; sous-domaine compta -> /justificatifs/scan/
  var URL_CANDIDATES = ["/comptabilite/justificatifs/scan/", "/justificatifs/scan/"];
  var URL_PREFILL = URL_CANDIDATES[0];

  // Les globales de la page (JOURNAUX, COMPTES, FOURNISSEURS) sont des `const`
  // declarees dans un <script> classique anterieur : visibles ici comme
  // identifiants nus (scope global partage), mais PAS sur `window`.
  function JX() { return (typeof JOURNAUX !== "undefined" && Array.isArray(JOURNAUX)) ? JOURNAUX : []; }
  function CX() { return (typeof COMPTES !== "undefined" && Array.isArray(COMPTES)) ? COMPTES : []; }

  function csrf() {
    var el = document.querySelector('[name=csrfmiddlewaretoken]');
    return el ? el.value : "";
  }

  function flash(msg, kind) {
    var variant = kind === "error" ? "error" : kind === "ok" ? "success" : "info";
    // saisie_workflow_compta.html : renderFeedback(message, variant)
    if (typeof renderFeedback === "function") {
      renderFeedback(msg, variant === "info" ? "warn" : variant);
    // saisie_workflow.html : showFeedback(type, message)
    } else if (typeof showFeedback === "function") {
      showFeedback(variant, msg);
    }
    var s = document.getElementById("ia-status");
    if (s) s.textContent = msg;
  }

  function setInput(id, val) {
    var el = document.getElementById(id);
    if (!el || val == null || val === "") return;
    el.value = val;
    el.dispatchEvent(new Event("input", { bubbles: true }));
    el.dispatchEvent(new Event("change", { bubbles: true }));
  }

  function pct(x) { return Math.round((x || 0) * 100) + "%"; }

  function badge(fieldId, fs) {
    var el = document.getElementById(fieldId);
    if (!el) return;
    var host = el.previousElementSibling && el.previousElementSibling.tagName === "LABEL"
      ? el.previousElementSibling
      : (el.closest("div") ? el.closest("div").querySelector("label") : null);
    if (!host) return;
    var b = host.querySelector(".ia-badge");
    if (!fs || fs.value == null || fs.value === "") { if (b) b.remove(); return; }
    if (!b) {
      b = document.createElement("span");
      b.className = "ia-badge";
      host.appendChild(b);
    }
    var auto = !!fs.auto;
    b.style.cssText = "margin-left:6px;display:inline-block;padding:1px 6px;border-radius:9999px;"
      + "font-size:10px;font-weight:700;vertical-align:middle;"
      + (auto ? "background:#d1fae5;color:#065f46;" : "background:#fef3c7;color:#92400e;");
    b.textContent = (auto ? "IA ✓ " : "IA ? ") + pct(fs.confidence);
    b.title = (fs.label ? fs.label + " — " : "") + "source: " + (fs.source || "?");
  }

  function selectByCode(selectId, arr, code, baseId) {
    var sel = document.getElementById(selectId);
    if (!sel || !code || !Array.isArray(arr)) return false;
    var m = arr.filter(function (x) {
      var c = x.code != null ? x.code : x.compte;
      return c === code && (!baseId || !x.base_id || x.base_id === baseId);
    })[0];
    if (!m) {
      m = arr.filter(function (x) { return (x.code != null ? x.code : x.compte) === code; })[0];
    }
    if (!m) return false;
    sel.value = m.id;
    sel.dispatchEvent(new Event("change", { bubbles: true }));
    return sel.value === m.id;
  }

  function renderNeighbours(data) {
    var box = document.getElementById("ia-neighbours");
    if (!box) return;
    var ns = (data && data.neighbours) || [];
    if (!ns.length) { box.innerHTML = ""; return; }
    box.innerHTML = '<div style="color:#64748b;margin-bottom:2px;">Ecritures historiques les plus proches :</div>'
      + ns.map(function (n) {
        return '<div style="color:#475569;">'
          + '<span style="font-weight:600;">' + Math.round(n.similarite * 100) + '%</span> '
          + '<span style="color:#0e7490;">' + (n.compte_code || "-") + "/" + (n.journal_code || "-")
          + (n.fournisseur ? "/" + n.fournisseur : "") + "</span> "
          + escapeHtml((n.description || "").slice(0, 90))
          + "</div>";
      }).join("");
  }

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  function apply(data) {
    if (!data || data.status === "index_absent") {
      flash("Suggestions IA indisponibles (index non construit sur le serveur).", "warn");
      return;
    }
    if (data.status === "extraction_error") {
      flash("Lecture du justificatif indisponible : " + ((data.warnings || []).join(" ") || "erreur")
        + ". Utilisez le bouton « Suggerer d'apres le libelle ».", "warn");
      return;
    }

    var f = data.fields || {};
    var baseId = (document.getElementById("base_id") || {}).value || "";

    if (f.journal_code) { selectByCode("journal_id", JX(), f.journal_code.value, baseId); badge("journal_id", f.journal_code); }
    if (f.compte_code) { selectByCode("compte_id", CX(), f.compte_code.value, baseId); badge("compte_id", f.compte_code); }

    if (f.fournisseur && f.fournisseur.value) {
      var lbl = f.fournisseur.label ? (f.fournisseur.value + " - " + f.fournisseur.label) : f.fournisseur.value;
      setInput("fournisseur", lbl);
      badge("fournisseur", f.fournisseur);
    }

    var sens = f.sens && f.sens.value;
    var montant = f.montant && f.montant.value;
    if (montant && sens === "in") { setInput("montant_in", montant); badge("montant_in", f.montant); }
    else if (montant && sens === "out") { setInput("montant_out", montant); badge("montant_out", f.montant); }

    if (f.date_piece && f.date_piece.value) { setInput("date_m", f.date_piece.value); badge("date_m", f.date_piece); }

    var descEl = document.getElementById("description");
    if (data.extraction && descEl && !descEl.value.trim()) {
      var ex = data.extraction;
      var d = [ex.fournisseur_nom_brut, ex.type_piece && ex.type_piece !== "autre" ? ex.type_piece : "",
               ex.numero_piece ? "n° " + ex.numero_piece : ""].filter(Boolean).join(" ");
      if (d) setInput("description", d);
    }

    renderNeighbours(data);

    var msg = "Suggestions IA appliquees";
    if (sens && !montant) msg += " — sens probable : " + (sens === "in" ? "recette" : "depense");
    msg += ". Verifiez les champs marques « IA ? ».";
    if (data.warnings && data.warnings.length) msg += " (" + data.warnings.join(" ; ") + ")";
    flash(msg, "ok");
  }

  function busy(on) {
    var s = document.getElementById("ia-status");
    if (s) s.textContent = on ? "Analyse en cours..." : "";
    ["ia-file-btn", "ia-text-btn"].forEach(function (id) {
      var b = document.getElementById(id); if (b) b.disabled = on;
    });
  }

  // POST vers l'endpoint ; sur 404 on essaie l'autre chemin (www vs sous-domaine).
  function postPrefill(init, i) {
    i = i || 0;
    return fetch(URL_CANDIDATES[i], init).then(function (r) {
      if (r.status === 404 && i + 1 < URL_CANDIDATES.length) {
        return postPrefill(init, i + 1);
      }
      URL_PREFILL = URL_CANDIDATES[i];
      return r.json();
    });
  }

  function suggestFromText() {
    var texte = (document.getElementById("description") || {}).value || "";
    texte = texte.trim();
    if (texte.length < 4) { flash("Saisir d'abord un libelle dans Description.", "warn"); return; }
    var baseId = (document.getElementById("base_id") || {}).value || "";
    busy(true);
    postPrefill({
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRFToken": csrf() },
      credentials: "same-origin",
      body: JSON.stringify({ texte: texte, base_id: baseId }),
    })
      .then(apply)
      .catch(function () { flash("Erreur reseau lors de la suggestion.", "error"); })
      .finally(function () { busy(false); });
  }

  function suggestFromFile(file) {
    if (!file) return;
    var baseId = (document.getElementById("base_id") || {}).value || "";
    var fd = new FormData();
    fd.append("scan", file);
    if (baseId) fd.append("base_id", baseId);
    busy(true);
    flash("Lecture du justificatif " + file.name + "...", "warn");
    postPrefill({
      method: "POST",
      headers: { "X-CSRFToken": csrf() },
      credentials: "same-origin",
      body: fd,
    })
      .then(apply)
      .catch(function () { flash("Erreur reseau lors de l'envoi du justificatif.", "error"); })
      .finally(function () { busy(false); });
  }

  function init() {
    var fileBtn = document.getElementById("ia-file-btn");
    var fileInput = document.getElementById("ia-file");
    var textBtn = document.getElementById("ia-text-btn");
    var zone = document.getElementById("ia-prefill");
    if (!zone) return;

    if (fileBtn && fileInput) {
      fileBtn.addEventListener("click", function () { fileInput.click(); });
      fileInput.addEventListener("change", function () {
        if (fileInput.files && fileInput.files[0]) suggestFromFile(fileInput.files[0]);
      });
    }
    if (textBtn) textBtn.addEventListener("click", suggestFromText);

    ["dragenter", "dragover"].forEach(function (ev) {
      zone.addEventListener(ev, function (e) { e.preventDefault(); zone.style.background = "#ecfeff"; });
    });
    ["dragleave", "drop"].forEach(function (ev) {
      zone.addEventListener(ev, function (e) { e.preventDefault(); zone.style.background = ""; });
    });
    zone.addEventListener("drop", function (e) {
      var dt = e.dataTransfer;
      if (dt && dt.files && dt.files[0]) suggestFromFile(dt.files[0]);
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
