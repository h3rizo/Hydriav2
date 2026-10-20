(function () {
    const soundFiles = {
        success: "/static/formation/sounds/success.mp3",
        errorSoft: "/static/formation/sounds/error-soft.mp3",
        click: "/static/formation/sounds/click.mp3",
        quizComplete: "/static/formation/sounds/quiz-complete.mp3",
        levelUp: "/static/formation/sounds/level-up.mp3",
        badgeEarned: "/static/formation/sounds/badge-earned.mp3",
    };

    const soundPreferenceKey = "hydria-quiz-sound-enabled";
    let soundEnabled = true;
    const audioCache = {};

    function loadSoundPreference() {
        const raw = localStorage.getItem(soundPreferenceKey);
        soundEnabled = raw !== "0";
        document.querySelectorAll("[data-sound-toggle]").forEach((button) => {
            const icon = button.querySelector("i");
            const label = button.querySelector("span");
            if (icon) {
                icon.className = soundEnabled ? "fas fa-volume-high mr-2" : "fas fa-volume-xmark mr-2";
            }
            if (label) {
                label.textContent = soundEnabled ? "Sons actifs" : "Sons coupes";
            }
        });
        return soundEnabled;
    }

    function toggleSound() {
        soundEnabled = !soundEnabled;
        localStorage.setItem(soundPreferenceKey, soundEnabled ? "1" : "0");
        loadSoundPreference();
    }

    function getAudio(name) {
        if (!soundFiles[name]) {
            return null;
        }
        if (!audioCache[name]) {
            audioCache[name] = new Audio(soundFiles[name]);
            audioCache[name].preload = "none";
        }
        return audioCache[name];
    }

    function playSound(name) {
        if (!soundEnabled) {
            return;
        }
        const audio = getAudio(name);
        if (!audio) {
            return;
        }
        try {
            audio.currentTime = 0;
            const playPromise = audio.play();
            if (playPromise && typeof playPromise.catch === "function") {
                playPromise.catch(() => {});
            }
        } catch (_) {}
    }

    function updateMascotState(state) {
        const mascot = document.querySelector("[data-mascot]");
        const caption = document.querySelector("[data-mascot-caption]");
        if (!mascot) {
            return;
        }
        const sources = {
            neutral: mascot.dataset.neutralSrc,
            success: mascot.dataset.successSrc,
            error: mascot.dataset.errorSrc,
            complete: mascot.dataset.completeSrc || mascot.dataset.successSrc,
            encouragement: mascot.dataset.encouragementSrc || mascot.dataset.neutralSrc,
        };
        const nextSrc = sources[state] || sources.neutral;
        if (nextSrc) {
            mascot.src = nextSrc;
        }
        if (caption) {
            const messages = {
                neutral: "La mascotte Hydria vous accompagne.",
                success: "Bonne reponse, on continue.",
                error: "Pas grave, Hydria vous explique la bonne logique.",
                complete: "Session terminee, beau travail.",
                encouragement: "Continuez, l'XP viendra vite.",
            };
            caption.textContent = messages[state] || messages.neutral;
        }
    }

    function animateAnswerResult(isCorrect) {
        document.querySelectorAll("[data-feedback-panel]").forEach((panel) => {
            panel.classList.remove("quiz-xp-burst");
            void panel.offsetWidth;
            panel.classList.add("quiz-xp-burst");
        });
        playSound(isCorrect ? "success" : "errorSoft");
        updateMascotState(isCorrect ? "success" : "error");
    }

    function animateXpGain(points) {
        const xpNodes = document.querySelectorAll("[data-xp-value]");
        if (!xpNodes.length || !points) {
            return;
        }
        xpNodes.forEach((node) => {
            node.classList.remove("quiz-xp-burst");
            void node.offsetWidth;
            node.classList.add("quiz-xp-burst");
        });
    }

    function initChoiceCards() {
        document.querySelectorAll("[data-choice-card]").forEach((card) => {
            const input = card.querySelector("input");
            if (!input) {
                return;
            }
            card.addEventListener("click", () => {
                playSound("click");
                document.querySelectorAll("[data-choice-card]").forEach((item) => item.classList.remove("is-selected"));
                card.classList.add("is-selected");
            });
            if (input.checked) {
                card.classList.add("is-selected");
            }
        });
    }

    function initQuizReviewState() {
        const shell = document.querySelector(".quiz-shell");
        if (!shell) {
            return;
        }
        const state = shell.dataset.feedbackState || "neutral";
        updateMascotState(state);
        if (shell.dataset.reviewMode === "1") {
            animateAnswerResult(state === "success");
        }
        if (state === "complete") {
            playSound("quizComplete");
        }
    }

    function safeJson(id) {
        const node = document.getElementById(id);
        if (!node) {
            return null;
        }
        try {
            return JSON.parse(node.textContent);
        } catch (_) {
            return null;
        }
    }

    // Couleur du thème actif (DaisyUI : variables oklch "L C H"). Le canvas ne résout pas var() : on lit la valeur calculée.
    function themeColor(name, alpha, fallback) {
        const raw = getComputedStyle(document.documentElement).getPropertyValue("--" + name).trim();
        if (!raw) {
            return fallback;
        }
        return alpha === undefined ? `oklch(${raw})` : `oklch(${raw} / ${alpha})`;
    }

    const quizCharts = [];

    function applyChartTheme() {
        if (typeof window.Chart === "undefined") {
            return;
        }
        Chart.defaults.color = themeColor("bc", 0.85, "#475569");
        Chart.defaults.borderColor = themeColor("bc", 0.15, "rgba(100,116,139,0.25)");
        quizCharts.forEach((chart) => {
            if (chart.config.type === "doughnut") {
                chart.data.datasets.forEach((dataset) => { dataset.borderColor = themeColor("b1", undefined, "#ffffff"); });
            }
            chart.update();
        });
    }

    function initCharts() {
        if (typeof window.Chart === "undefined") {
            return;
        }
        applyChartTheme();
        new MutationObserver(applyChartTheme).observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
        const timeline = safeJson("quiz-chart-timeline") || [];
        const scores = safeJson("quiz-chart-theme-scores") || [];
        const counts = safeJson("quiz-chart-theme-counts") || [];

        const timelineCanvas = document.getElementById("xpTimelineChart");
        if (timelineCanvas) {
            quizCharts.push(new Chart(timelineCanvas, {
                type: "line",
                data: {
                    labels: timeline.map((item) => item.label),
                    datasets: [
                        {
                            label: "XP",
                            data: timeline.map((item) => item.xp),
                            borderColor: "#0ea5e9",
                            backgroundColor: "rgba(14,165,233,0.16)",
                            tension: 0.35,
                            fill: true,
                        },
                        {
                            label: "Score %",
                            data: timeline.map((item) => item.score),
                            borderColor: "#10b981",
                            backgroundColor: "rgba(16,185,129,0.08)",
                            tension: 0.35,
                            fill: false,
                        },
                    ],
                },
                options: { responsive: true, maintainAspectRatio: false },
            }));
        }

        const scoreCanvas = document.getElementById("themeScoreChart");
        if (scoreCanvas) {
            quizCharts.push(new Chart(scoreCanvas, {
                type: "bar",
                data: {
                    labels: scores.map((item) => item.theme),
                    datasets: [{
                        label: "Score moyen",
                        data: scores.map((item) => item.score),
                        backgroundColor: ["#0ea5e9", "#22c55e", "#f59e0b", "#8b5cf6", "#ef4444"],
                    }],
                },
                options: { responsive: true, maintainAspectRatio: false },
            }));
        }

        const countCanvas = document.getElementById("themeCountChart");
        if (countCanvas) {
            quizCharts.push(new Chart(countCanvas, {
                type: "doughnut",
                data: {
                    labels: counts.map((item) => item.theme),
                    datasets: [{
                        data: counts.map((item) => item.count),
                        backgroundColor: ["#0ea5e9", "#22c55e", "#f59e0b", "#8b5cf6", "#ef4444", "#14b8a6"],
                        borderColor: themeColor("b1", undefined, "#ffffff"),
                    }],
                },
                options: { responsive: true, maintainAspectRatio: false },
            }));
        }
    }

    document.addEventListener("DOMContentLoaded", () => {
        loadSoundPreference();
        initChoiceCards();
        initQuizReviewState();
        initCharts();
        document.querySelectorAll("[data-sound-toggle]").forEach((button) => {
            button.addEventListener("click", toggleSound);
        });
        const xpNode = document.querySelector("[data-xp-value]");
        if (xpNode) {
            animateXpGain(Number.parseInt(xpNode.textContent || "0", 10));
        }
    });

    window.playSound = playSound;
    window.toggleSound = toggleSound;
    window.loadSoundPreference = loadSoundPreference;
    window.updateMascotState = updateMascotState;
    window.animateAnswerResult = animateAnswerResult;
    window.animateXpGain = animateXpGain;
})();
