/**
 * Hydria - Export universel des graphiques Chart.js
 * ---------------------------------------------------
 * Ajoute automatiquement un bouton "Exporter en PNG" sur CHAQUE graphique
 * Chart.js de l'application (existant ou créé dynamiquement plus tard),
 * sans qu'aucune page n'ait besoin d'être modifiée individuellement.
 *
 * Fonctionnement : s'enregistre comme plugin global Chart.js (Chart.register)
 * et se déclenche via le hook de cycle de vie "afterInit", appelé pour
 * chaque instance de graphique créée n'importe où dans l'app.
 *
 * Inclure ce fichier une fois par page (déjà fait dans les gabarits de
 * base de chaque module) : {% static 'js/chart_export.js' %}
 */
(function () {
    "use strict";

    var STYLE_ID = "hydria-chart-export-style";
    var BTN_CLASS = "hydria-chart-export-btn";
    var REF_KEY = "__hydriaChartRef";

    function injectStyleOnce() {
        if (document.getElementById(STYLE_ID)) return;
        var style = document.createElement("style");
        style.id = STYLE_ID;
        style.textContent =
            "." + BTN_CLASS + "{" +
            "position:absolute;top:6px;right:6px;z-index:30;" +
            "width:26px;height:26px;display:flex;align-items:center;justify-content:center;" +
            "border-radius:9999px;border:1px solid rgba(0,0,0,0.12);" +
            "background:rgba(255,255,255,0.85);color:#333;cursor:pointer;" +
            "font-size:12px;line-height:1;padding:0;opacity:0.55;" +
            "box-shadow:0 1px 2px rgba(0,0,0,0.15);" +
            "transition:opacity .15s ease,transform .1s ease;}" +
            "." + BTN_CLASS + ":hover{opacity:1;transform:scale(1.08);}" +
            "[data-theme='dark'] ." + BTN_CLASS + ",.dark ." + BTN_CLASS + "{" +
            "background:rgba(30,30,30,0.85);color:#eee;border-color:rgba(255,255,255,0.15);}";
        document.head.appendChild(style);
    }

    function sanitizeFilename(text) {
        return String(text || "graphique")
            .normalize("NFD").replace(/[̀-ͯ]/g, "")
            .replace(/[^a-zA-Z0-9_-]+/g, "_")
            .replace(/^_+|_+$/g, "")
            .slice(0, 60) || "graphique";
    }

    function guessChartTitle(chart) {
        try {
            var t = chart.options && chart.options.plugins && chart.options.plugins.title;
            if (t && t.text) return Array.isArray(t.text) ? t.text.join(" ") : t.text;
        } catch (e) { /* noop */ }
        var canvas = chart.canvas;
        if (canvas && canvas.id) return canvas.id;
        return document.title;
    }

    function exportChartAsPng(chart) {
        try {
            var url = chart.toBase64Image("image/png", 1.0);
            var link = document.createElement("a");
            link.href = url;
            link.download = sanitizeFilename(guessChartTitle(chart)) + ".png";
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
        } catch (err) {
            console.error("[hydria-chart-export] export impossible :", err);
            window.alert("Export du graphique impossible pour le moment.");
        }
    }

    function ensureButton(chart) {
        var canvas = chart.canvas;
        if (!canvas) return;

        // Toujours garder une référence à jour vers l'instance courante du
        // graphique (un canvas peut être réutilisé si le graphique est
        // détruit puis recréé au même endroit, ex. filtres dynamiques).
        canvas[REF_KEY] = chart;

        if (canvas.dataset.hydriaExportReady === "1") return;
        canvas.dataset.hydriaExportReady = "1";

        var container = canvas.parentElement;
        if (!container) return;

        var computedPosition = window.getComputedStyle(container).position;
        if (!computedPosition || computedPosition === "static") {
            container.style.position = "relative";
        }

        injectStyleOnce();

        var btn = document.createElement("button");
        btn.type = "button";
        btn.className = BTN_CLASS;
        btn.title = "Exporter ce graphique en PNG";
        btn.setAttribute("aria-label", "Exporter ce graphique en PNG");
        btn.innerHTML = '<i class="fas fa-download" aria-hidden="true"></i>';
        // Filet de sécurité si Font Awesome n'est pas chargé sur la page.
        if (!document.querySelector('link[href*="font-awesome"], link[href*="fontawesome"]') &&
            !window.FontAwesome) {
            btn.textContent = "⬇"; // flèche vers le bas
        }

        btn.addEventListener("click", function (evt) {
            evt.preventDefault();
            evt.stopPropagation();
            var current = canvas[REF_KEY];
            if (current) exportChartAsPng(current);
        });

        container.appendChild(btn);
    }

    var pluginRegistered = false;

    function registerHydriaExportPlugin() {
        if (pluginRegistered) return true;
        if (typeof window.Chart === "undefined" || typeof window.Chart.register !== "function") {
            return false;
        }
        try {
            // Enregistrer deux fois le même id ne crée pas de doublon (Chart.js
            // remplace l'entrée existante dans son registre de plugins), mais on
            // se protège quand même avec un drapeau local pour n'appeler
            // register() qu'une seule fois par page.
            window.Chart.register({
                id: "hydriaExportButton",
                afterInit: function (chart) {
                    // Micro-délai : laisser le temps au canvas d'être inséré/dimensionné.
                    setTimeout(function () { ensureButton(chart); }, 0);
                },
            });
            pluginRegistered = true;
        } catch (e) {
            console.error("[hydria-chart-export] impossible d'enregistrer le plugin :", e);
        }
        return pluginRegistered;
    }

    if (!registerHydriaExportPlugin()) {
        // Chart.js peut se charger après ce script selon l'ordre des <script>
        // de chaque page : on retente pendant quelques secondes.
        var attempts = 0;
        var pollId = setInterval(function () {
            attempts += 1;
            if (registerHydriaExportPlugin() || attempts > 100) {
                clearInterval(pollId);
            }
        }, 100);
    }
})();
