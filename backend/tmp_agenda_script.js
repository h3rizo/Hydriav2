
        (function () {
            // Recuperation immediate du theme sauvegarde
            const savedTheme = localStorage.getItem('hydria-theme') || 'hydriaDark';
            // Application immediate sur l'element HTML
            document.documentElement.setAttribute('data-theme', savedTheme);
        })();
    </script>

    <!-- Meta tags pour PWA -->
    <meta name="theme-color" content="#3b82f6">
    <meta name="mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
    <meta name="apple-mobile-web-app-title" content="Hydria">
    <link rel="manifest" href="/static/manifest.json">

    <!-- Apple Touch Icons -->
    <link rel="apple-touch-icon" sizes="180x180" href="/static/images/icons/icon-192x192.png">
    <link rel="apple-touch-icon" sizes="152x152" href="/static/images/icons/icon-152x152.png">
    <link rel="apple-touch-icon" sizes="144x144" href="/static/images/icons/icon-144x144.png">
    <link rel="apple-touch-icon" sizes="120x120" href="/static/images/icons/icon-128x128.png">

    <!-- Scripts PWA -->
    <script src="/static/js/offline-db.js" defer></script>
    <script src="/static/js/pwa-manager.js" defer></script>

    <!-- Styles pour le preloader (placés dans le head pour un chargement prioritaire) -->
    <style>
        #preloader {
            transition: opacity 0.75s ease-out, visibility 0.75s ease-out;
        }

        #preloader.preloader-hidden {
            opacity: 0;
            visibility: hidden;
            pointer-events: none;
            /* Empêche les interactions après disparition */
        }

        .user-info-banner-content {
            max-height: 400px;
            transition: max-height 0.25s ease, opacity 0.2s ease;
            overflow: hidden;
        }

        .user-info-banner-collapsed .user-info-banner-content {
            max-height: 0;
            opacity: 0;
            pointer-events: none;
        }

        /* Navbar desktop compacte: centre compressible, zone utilisateur toujours visible */
        @media (min-width: 1024px) {
            .navbar {
                display: flex !important;
                gap: 0.35rem;
                align-items: flex-end;
            }

            .navbar-start,
            .navbar-end {
                width: auto !important;
                flex: 0 0 auto;
            }

            .navbar-center {
                width: auto !important;
                position: static !important;
                transform: none !important;
                left: auto !important;
                right: auto !important;
                flex: 1 1 auto !important;
                min-width: 0;
                display: flex;
                justify-content: center;
                align-self: flex-end;
                padding-bottom: 0.2rem;
            }

            .navbar-center .btn.btn-sm {
                padding-left: 0.45rem;
                padding-right: 0.45rem;
                font-size: 0.78rem;
                white-space: nowrap;
            }

            .navbar-end {
                align-self: center;
            }
        }

        /* Force absolu du menu desktop (anti-conflit Daisy/Tailwind) */
        .desktop-main-menu {
            display: flex !important;
            flex-direction: row !important;
            flex-wrap: wrap !important;
            align-items: center !important;
            justify-content: center !important;
            gap: 0.3rem !important;
            width: 100% !important;
            margin: 0 auto !important;
            padding: 0 0.25rem !important;
        }

        .desktop-main-menu > li {
            display: flex !important;
            width: auto !important;
            flex: 0 0 auto !important;
        }

        /* Menus sobres + icones colorees */
        .desktop-main-menu > li > a,
        .desktop-main-menu > li > .dropdown > [role="button"] {
            border-radius: 0.5rem !important;
            border: 1px solid transparent !important;
            background: transparent !important;
            color: inherit !important;
            transition: transform 0.15s ease, background 0.2s ease !important;
        }

        .desktop-main-menu > li > a:hover,
        .desktop-main-menu > li > .dropdown > [role="button"]:hover {
            background: rgba(255, 255, 255, 0.06) !important;
            transform: translateY(-1px);
        }

        .desktop-main-menu > li:nth-child(1) i:first-child { color: #14b8a6 !important; }
        .desktop-main-menu > li:nth-child(2) i:first-child { color: #3b82f6 !important; }
        .desktop-main-menu > li:nth-child(3) i:first-child { color: #8b5cf6 !important; }
        .desktop-main-menu > li:nth-child(4) i:first-child { color: #10b981 !important; }
        .desktop-main-menu > li:nth-child(5) i:first-child { color: #f59e0b !important; }
        .desktop-main-menu > li:nth-child(6) i:first-child { color: #ec4899 !important; }
        .desktop-main-menu > li:nth-child(7) i:first-child { color: #22c55e !important; }
        .desktop-main-menu > li:nth-child(8) i:first-child { color: #f97316 !important; }
        .desktop-main-menu > li:nth-child(9) i:first-child { color: #6366f1 !important; }
        .desktop-main-menu > li:nth-child(10) i:first-child { color: #06b6d4 !important; }

        /* Menus dropdown: sans cadre, icones colorees uniquement */
        .desktop-main-menu .dropdown-content > li > a {
            border-radius: 0.5rem;
            margin: 0.1rem 0;
            border: none !important;
            background: transparent !important;
            color: inherit !important;
            transition: background 0.15s ease, transform 0.15s ease;
        }

        .desktop-main-menu .dropdown-content > li > a:hover {
            background: rgba(255, 255, 255, 0.06) !important;
            transform: translateX(1px);
        }

        .desktop-main-menu .dropdown-content > li:nth-child(6n + 1) > a i:first-child { color: #14b8a6 !important; }
        .desktop-main-menu .dropdown-content > li:nth-child(6n + 2) > a i:first-child { color: #3b82f6 !important; }
        .desktop-main-menu .dropdown-content > li:nth-child(6n + 3) > a i:first-child { color: #a855f7 !important; }
        .desktop-main-menu .dropdown-content > li:nth-child(6n + 4) > a i:first-child { color: #f59e0b !important; }
        .desktop-main-menu .dropdown-content > li:nth-child(6n + 5) > a i:first-child { color: #22c55e !important; }
        .desktop-main-menu .dropdown-content > li:nth-child(6n + 6) > a i:first-child { color: #ec4899 !important; }

        /* Sidebar mobile: palette d'icones cohérente avec la navbar */
        .mobile-main-menu > li:nth-child(1) > a i:first-child:not([class*='text-']),
        .mobile-main-menu > li:nth-child(1) > details > summary i:first-child:not([class*='text-']) { color: #14b8a6 !important; }
        .mobile-main-menu > li:nth-child(2) > a i:first-child:not([class*='text-']),
        .mobile-main-menu > li:nth-child(2) > details > summary i:first-child:not([class*='text-']) { color: #3b82f6 !important; }
        .mobile-main-menu > li:nth-child(3) > a i:first-child:not([class*='text-']),
        .mobile-main-menu > li:nth-child(3) > details > summary i:first-child:not([class*='text-']) { color: #8b5cf6 !important; }
        .mobile-main-menu > li:nth-child(4) > a i:first-child:not([class*='text-']),
        .mobile-main-menu > li:nth-child(4) > details > summary i:first-child:not([class*='text-']) { color: #10b981 !important; }
        .mobile-main-menu > li:nth-child(5) > a i:first-child:not([class*='text-']),
        .mobile-main-menu > li:nth-child(5) > details > summary i:first-child:not([class*='text-']) { color: #f59e0b !important; }
        .mobile-main-menu > li:nth-child(6) > a i:first-child:not([class*='text-']),
        .mobile-main-menu > li:nth-child(6) > details > summary i:first-child:not([class*='text-']) { color: #ec4899 !important; }
        .mobile-main-menu > li:nth-child(7) > a i:first-child:not([class*='text-']),
        .mobile-main-menu > li:nth-child(7) > details > summary i:first-child:not([class*='text-']) { color: #22c55e !important; }
        .mobile-main-menu > li:nth-child(8) > a i:first-child:not([class*='text-']),
        .mobile-main-menu > li:nth-child(8) > details > summary i:first-child:not([class*='text-']) { color: #f97316 !important; }
        .mobile-main-menu > li:nth-child(9) > a i:first-child:not([class*='text-']),
        .mobile-main-menu > li:nth-child(9) > details > summary i:first-child:not([class*='text-']) { color: #6366f1 !important; }
        .mobile-main-menu > li:nth-child(10) > a i:first-child:not([class*='text-']),
        .mobile-main-menu > li:nth-child(10) > details > summary i:first-child:not([class*='text-']) { color: #06b6d4 !important; }

        .mobile-main-menu details > ul > li:nth-child(6n + 1) > a i:first-child:not([class*='text-']) { color: #14b8a6 !important; }
        .mobile-main-menu details > ul > li:nth-child(6n + 2) > a i:first-child:not([class*='text-']) { color: #3b82f6 !important; }
        .mobile-main-menu details > ul > li:nth-child(6n + 3) > a i:first-child:not([class*='text-']) { color: #a855f7 !important; }
        .mobile-main-menu details > ul > li:nth-child(6n + 4) > a i:first-child:not([class*='text-']) { color: #f59e0b !important; }
        .mobile-main-menu details > ul > li:nth-child(6n + 5) > a i:first-child:not([class*='text-']) { color: #22c55e !important; }
        .mobile-main-menu details > ul > li:nth-child(6n + 6) > a i:first-child:not([class*='text-']) { color: #ec4899 !important; }

        @media (min-width: 1024px) and (max-width: 1366px) {
            .navbar-center .btn.btn-sm {
                padding-left: 0.35rem;
                padding-right: 0.35rem;
                font-size: 0.74rem;
            }

            #online-status {
                display: none !important;
            }
        }

    </style>

    
<style>
.planning-agenda-shell {
    --agenda-accent: var(--primary, #2563eb);
    --agenda-accent-soft: var(--accent, #059669);
    --agenda-highlight: var(--warning, #d97706);
    --agenda-accent-contrast: var(--primary-content, #ffffff);
    --agenda-success: var(--success, #059669);
    --agenda-bg-1: var(--base-100, #ffffff);
    --agenda-bg-2: var(--base-200, #f8fafc);
    --agenda-bg-3: var(--base-300, #e2e8f0);
    --agenda-text: var(--base-content, #1e293b);
    --agenda-grid-line: rgba(30, 41, 59, 0.05);
    --agenda-shadow-soft: rgba(15, 23, 42, 0.14);
    --agenda-shadow-strong: rgba(15, 23, 42, 0.24);
    --agenda-hover-border: rgba(37, 99, 235, 0.32);
    --agenda-today-border: rgba(14, 165, 233, 0.5);
    --agenda-today-ring: rgba(14, 165, 233, 0.18);
    --agenda-count-bg: rgba(37, 99, 235, 0.14);
    --agenda-selected-count-bg: rgba(255, 255, 255, 0.18);
    --agenda-muted: rgba(30, 41, 59, 0.62);
    --agenda-soft: rgba(30, 41, 59, 0.55);
    --agenda-selected-meta: rgba(255, 255, 255, 0.82);
    --agenda-active-border: rgba(37, 99, 235, 0.42);
    --agenda-active-shadow: rgba(37, 99, 235, 0.12);
    --agenda-empty-bg: rgba(248, 250, 252, 0.85);
    --agenda-detail-bg: rgba(248, 250, 252, 0.7);
}

[data-theme="hydriaDark"] .planning-agenda-shell {
    --agenda-grid-line: rgba(255, 255, 255, 0.04);
    --agenda-shadow-soft: rgba(0, 0, 0, 0.34);
    --agenda-shadow-strong: rgba(0, 0, 0, 0.45);
    --agenda-hover-border: rgba(59, 130, 246, 0.45);
    --agenda-today-border: rgba(14, 165, 233, 0.58);
    --agenda-today-ring: rgba(14, 165, 233, 0.22);
    --agenda-count-bg: rgba(59, 130, 246, 0.22);
    --agenda-selected-count-bg: rgba(255, 255, 255, 0.22);
    --agenda-muted: rgba(255, 255, 255, 0.7);
    --agenda-soft: rgba(255, 255, 255, 0.55);
    --agenda-selected-meta: rgba(255, 255, 255, 0.86);
    --agenda-active-border: rgba(59, 130, 246, 0.55);
    --agenda-active-shadow: rgba(0, 0, 0, 0.24);
    --agenda-empty-bg: rgba(55, 65, 81, 0.55);
    --agenda-detail-bg: rgba(75, 85, 99, 0.4);
}

[data-theme="winter"] .planning-agenda-shell {
    --agenda-grid-line: rgba(30, 41, 59, 0.05);
    --agenda-shadow-soft: rgba(15, 23, 42, 0.14);
    --agenda-shadow-strong: rgba(15, 23, 42, 0.24);
    --agenda-hover-border: rgba(37, 99, 235, 0.32);
    --agenda-today-border: rgba(14, 165, 233, 0.45);
    --agenda-today-ring: rgba(14, 165, 233, 0.14);
    --agenda-count-bg: rgba(37, 99, 235, 0.14);
    --agenda-selected-count-bg: rgba(255, 255, 255, 0.18);
    --agenda-muted: rgba(30, 41, 59, 0.62);
    --agenda-soft: rgba(30, 41, 59, 0.55);
    --agenda-selected-meta: rgba(255, 255, 255, 0.82);
    --agenda-active-border: rgba(37, 99, 235, 0.42);
    --agenda-active-shadow: rgba(37, 99, 235, 0.12);
    --agenda-empty-bg: rgba(248, 250, 252, 0.85);
    --agenda-detail-bg: rgba(248, 250, 252, 0.7);
}

.agenda-hero {
    position: relative;
    overflow: hidden;
    border: 1px solid var(--agenda-bg-3);
    background:
        radial-gradient(circle at top left, var(--agenda-count-bg), transparent 34%),
        radial-gradient(circle at top right, rgba(245, 158, 11, 0.14), transparent 28%),
        linear-gradient(135deg, var(--agenda-bg-1) 0%, var(--agenda-bg-2) 100%);
}

.agenda-hero::after {
    content: "";
    position: absolute;
    inset: 0;
    background-image:
        linear-gradient(var(--agenda-grid-line) 1px, transparent 1px),
        linear-gradient(90deg, var(--agenda-grid-line) 1px, transparent 1px);
    background-size: 22px 22px;
    pointer-events: none;
}

.agenda-sticky-shell {
    position: sticky;
    top: 1rem;
    z-index: 25;
}

.agenda-calendar-card {
    border: 1px solid var(--agenda-bg-3);
    background:
        linear-gradient(180deg, var(--agenda-bg-1) 0%, var(--agenda-bg-2) 100%);
    backdrop-filter: blur(14px);
    box-shadow: 0 24px 48px var(--agenda-shadow-soft);
}

.agenda-weekdays,
.agenda-calendar-grid {
    display: grid;
    grid-template-columns: repeat(7, minmax(0, 1fr));
    gap: 0.45rem;
}

.agenda-weekday {
    text-align: center;
    font-size: 0.7rem;
    font-weight: 700;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--agenda-soft);
}

.agenda-day-button {
    min-height: 4.25rem;
    border: 1px solid var(--agenda-bg-3);
    border-radius: 1rem;
    padding: 0.55rem;
    text-align: left;
    background: var(--agenda-bg-1);
    transition: transform 0.18s ease, box-shadow 0.18s ease, border-color 0.18s ease, background 0.18s ease;
}

.agenda-day-button:hover {
    transform: translateY(-1px);
    box-shadow: 0 12px 24px var(--agenda-shadow-soft);
    border-color: var(--agenda-hover-border);
}

.agenda-day-button.is-selected {
    color: var(--agenda-accent-contrast);
    border-color: transparent;
    background: linear-gradient(135deg, var(--agenda-accent) 0%, var(--agenda-accent-soft) 100%);
    box-shadow: 0 18px 32px var(--agenda-shadow-strong);
}

.agenda-day-button.is-today:not(.is-selected) {
    border-color: var(--agenda-today-border);
    box-shadow: inset 0 0 0 1px var(--agenda-today-ring);
}

.agenda-day-button.is-outside {
    opacity: 0.42;
}

.agenda-day-button.week-mode {
    min-height: 5rem;
}

.agenda-day-top {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.5rem;
}

.agenda-day-number {
    font-size: 1.05rem;
    font-weight: 700;
    line-height: 1;
}

.agenda-day-count {
    min-width: 1.6rem;
    padding: 0.12rem 0.4rem;
    border-radius: 999px;
    font-size: 0.72rem;
    font-weight: 700;
    text-align: center;
    background: var(--agenda-count-bg);
    color: var(--agenda-accent);
}

.agenda-day-button.is-selected .agenda-day-count {
    color: var(--agenda-accent-contrast);
    background: var(--agenda-selected-count-bg);
}

.agenda-day-meta {
    margin-top: 0.7rem;
    font-size: 0.72rem;
    color: var(--agenda-muted);
}

.agenda-day-button.is-selected .agenda-day-meta {
    color: var(--agenda-selected-meta);
}

.agenda-summary-chip {
    border: 1px solid var(--agenda-bg-3);
    background: var(--agenda-bg-1);
}

.agenda-day-section {
    scroll-margin-top: 16rem;
    border: 1px solid var(--agenda-bg-3);
    background: var(--agenda-bg-1);
    transition: border-color 0.18s ease, box-shadow 0.18s ease, transform 0.18s ease;
}

.agenda-day-section.is-active {
    border-color: var(--agenda-active-border);
    box-shadow: 0 20px 36px var(--agenda-active-shadow);
}

.agenda-day-section-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 1rem;
}

.agenda-day-empty {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    border: 1px dashed var(--agenda-bg-3);
    border-radius: 1rem;
    padding: 1rem;
    color: var(--agenda-muted);
    background: var(--agenda-empty-bg);
}

.agenda-event-card {
    border: 1px solid var(--agenda-bg-3);
    border-left-width: 5px;
    border-radius: 1rem;
    padding: 1rem;
    background: linear-gradient(180deg, var(--agenda-bg-1) 0%, var(--agenda-bg-2) 100%);
}

.agenda-event-card.pending {
    border-left-color: var(--agenda-highlight);
}

.agenda-event-card.validated {
    border-left-color: var(--agenda-success);
}

.agenda-detail-shell {
    border-top: 1px solid var(--agenda-bg-3);
    margin-top: 0.9rem;
    padding-top: 0.9rem;
}

.agenda-detail-block + .agenda-detail-block {
    margin-top: 0.9rem;
}

.agenda-detail-item {
    border: 1px solid var(--agenda-bg-3);
    border-radius: 0.85rem;
    padding: 0.75rem;
    background: var(--agenda-detail-bg);
}

.agenda-fab {
    position: fixed;
    right: 1rem;
    bottom: calc(1rem + env(safe-area-inset-bottom, 0px));
    z-index: 35;
    box-shadow: 0 20px 40px var(--agenda-shadow-strong);
}

.agenda-toast {
    position: fixed;
    left: 50%;
    bottom: calc(5.8rem + env(safe-area-inset-bottom, 0px));
    z-index: 40;
    transform: translateX(-50%) translateY(120%);
    transition: transform 0.22s ease;
}

.agenda-toast.is-visible {
    transform: translateX(-50%) translateY(0);
}

@media (max-width: 768px) {
    .agenda-sticky-shell {
        top: 0.75rem;
    }

    .agenda-day-button {
        min-height: 4.6rem;
        padding: 0.5rem;
    }

    .agenda-day-number {
        font-size: 1rem;
    }

    .agenda-day-section {
        scroll-margin-top: 18rem;
    }
}
</style>

    
</head>

<body class="min-h-screen bg-base-100">

    <!-- Bandeau informations utilisateur -->
    
    <div id="user-info-banner" class="bg-gradient-to-r from-primary/10 to-accent/10 border-b border-primary/20 user-info-banner-collapsed">
        <div class="container mx-auto px-4 py-2">
            <div class="flex items-center justify-between gap-2 text-sm">
                <button id="toggle-user-info-banner" type="button" class="btn btn-ghost btn-xs">
                    <i class="fas fa-chevron-down mr-1"></i>
                    
                    
                        
                        <img src="/media/logos/organisations/logo_soakoja.png?v=20260303a" alt="Soakoja" class="h-6 w-auto max-w-[7rem] object-contain mr-1">
                        
                    
                    
                    Infos utilisateur
                </button>
            </div>
            <div class="user-info-banner-content">
            <div class="flex flex-wrap items-center justify-between gap-2 text-sm mt-2">
                <div class="flex flex-wrap items-center gap-4">
                    <!-- Organisation -->
                    
                    <div class="flex items-center gap-2">
                        <i class="fas fa-building text-primary"></i>
                        <span class="font-semibold">Soakoja</span>
                    </div>
                    

                    <!-- Base -->
                    
                    <div class="flex items-center gap-2">
                        <i class="fas fa-map-marker-alt text-info"></i>
                        <span>Base: <strong>Vavatenina SK</strong></span>
                    </div>
                    

                    <!-- Employé -->
                    <div class="flex items-center gap-2">
                        <i class="fas fa-user text-accent"></i>
                        <span>HERIZO</span>
                    </div>

                    <!-- Poste -->
                    
                    <div class="flex items-center gap-2">
                        <i class="fas fa-briefcase text-warning"></i>
                        <span class="badge badge-sm badge-outline">Directeur (Soakoja)</span>
                    </div>
                    

                    <!-- Indicateur statut connexion -->
                    <div id="connection-status" class="badge badge-sm badge-success">
                        <i class="fas fa-wifi mr-1"></i>
                        <span>En ligne</span>
                    </div>

                    <!-- Indicateur de synchronisation (masqué par défaut) -->
                    <div id="sync-indicator" class="hidden flex items-center gap-1">
                        <span class="loading loading-spinner loading-xs text-info"></span>
                        <span class="text-xs">Sync...</span>
                    </div>

                    <!-- Bouton installation PWA (masqué par défaut) -->
                    <button id="pwa-install-btn" class="btn btn-primary btn-xs hidden" onclick="pwaManager.install()">
                        <i class="fas fa-download mr-1"></i>Installer l'app
                    </button>

                    <!-- Tracking GPS avec indicateur de qualité -->
                    <div id="gps-indicator" class="flex items-center gap-2">
                        <!-- État initial: GPS désactivé -->
                        <i class="fas fa-map-marker-alt text-base-content/30" id="gps-icon"></i>
                        <span class="text-xs" id="gps-text">
                            
                            <strong>Mahavelona</strong>
                            
                            (14367,9 km)
                            
                            
                        </span>
                        <span class="badge badge-xs" id="gps-precision-badge" style="display: none;"></span>
                    </div>

                    <!-- Temps de connexion du mois -->
                    
                    <div class="flex items-center gap-2">
                        <i class="fas fa-clock text-info"></i>
                        <span class="text-xs">
                            <strong>11,5h</strong> ce mois
                        </span>
                    </div>
                    
                </div>

                <!-- Permissions -->
                <div class="flex items-center gap-2">
                    <i class="fas fa-shield-alt text-success"></i>
                    <span class="text-xs italic">
                        
                        Accès standard
                        
                    </span>
                </div>
            </div>
            </div>
        </div>
    </div>
    

    <!-- Navbar -->
    <nav class="navbar bg-base-100 shadow-sm border-b border-base-300">
        <div class="navbar-start">
            <div class="dropdown">
                <div tabindex="0" role="button" class="btn btn-ghost lg:hidden">
                    <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                            d="M4 6h16M4 12h8m-8 6h16"></path>
                    </svg>
                </div>
                <ul tabindex="0"
                    class="mobile-main-menu menu menu-sm dropdown-content bg-base-100 rounded-box z-[1] mt-3 w-64 p-2 shadow lg:hidden">
                    
                    
                    
                    <!-- Applications -->
                    <li>
                        <a href="/accueil/" class="font-semibold bg-gradient-to-r from-primary/20 to-accent/20">
                            <i class="fas fa-th mr-2 text-primary"></i>Applications
                        </a>
                    </li>

                    <!-- Recherche -->
                    <li>
                        <a href="/recherche/" class="font-semibold"><i
                                class="fas fa-search mr-2 text-primary"></i>Recherche</a>
                    </li>

                    <!-- Tableaux & Rapports -->
                    <li>
                        <details>
                            <summary><i class="fas fa-tachometer-alt mr-2"></i>Tableaux & Rapports</summary>
                            <ul>
                                
                                <li class="divider">Tableaux de Bord</li>
                                <li><a href="/dashboard/"><i class="fas fa-home mr-2"></i>Vue d'ensemble</a></li>
                                <li><a href="/geography/dashboard/"><i class="fas fa-map-marked-alt mr-2 text-primary"></i>Géographie & Population</a></li>
                                <li><a href="/dashboard/carte/"><i class="fas fa-map mr-2 text-accent"></i>Carte interactive</a></li>
                                <li><a href="/dashboard/paiements-forfaitaires/"><i class="fas fa-coins mr-2 text-warning"></i>Paiements forfaitaires</a></li>
                                <li><a href="/plannings/volumetrique/global/"><i class="fas fa-tint mr-2 text-info"></i>Paiements au volume</a></li>
                                <li><a href="/plannings/conso-cartes-sociales/global/"><i class="fas fa-credit-card mr-2 text-success"></i>Paiements cartes sociales</a></li>
                                <li><a href="/dashboard/depenses/"><i class="fas fa-chart-line mr-2 text-error"></i>Dépenses</a></li>
                                <li><a href="/dashboard/infrastructures/"><i class="fas fa-tools mr-2 text-success"></i>État des ouvrages</a></li>
                                <li><a href="/comptabilite/dashboard/"><i class="fas fa-calculator mr-2 text-primary"></i>Comptabilité</a></li>
                                <li class="divider">Rapports & Analyses</li>
                                <li><a href="/rapports/"><i class="fas fa-dashboard mr-2"></i>Tableau de bord rapports</a></li>
                                <li><a href="/rapports/activites-par-employe/"><i class="fas fa-users mr-2"></i>Activités par employé</a></li>
                                <li><a href="/rapports/performance-bases/"><i class="fas fa-building mr-2"></i>Performance bases</a></li>
                                <li><a href="/rapports/indicateurs-diamex/"><i class="fas fa-sync mr-2"></i>Indicateurs DiameX</a></li>
                                <li><a href="/plannings/visites/"><i class="fas fa-chart-bar mr-2 text-info"></i>Comptage visites</a></li>
                                <li><a href="/organisations/ouvrages/grading-annuel/"><i class="fas fa-chart-line mr-2 text-success"></i>Gradings Annuels Ouvrages</a></li>
                                <li><a href="/organisations/ouvrages/grading-annuel/analyse/"><i class="fas fa-chart-bar mr-2 text-info"></i>Analyse des Gradings</a></li>
                                <li class="divider">Analyses consommation</li>
                                <li><a href="/plannings/volumetrique/analyse-consommation/"><i class="fas fa-chart-line mr-2 text-success"></i>Analyse consommation</a></li>
                                <li><a href="/plannings/volumetrique/analyse-par-point-eau/"><i class="fas fa-tint mr-2 text-info"></i>Analyse par point d'eau</a></li>
                                <li><a href="/plannings/volumetrique/tableau-points-eau/"><i class="fas fa-table mr-2 text-primary"></i>Tableau points d'eau</a></li>
                                <li><a href="/plannings/cartes-sociales/analyse/"><i class="fas fa-id-card mr-2 text-warning"></i>Analyse Cartes Sociales</a></li>
                                <li><a href="/plannings/meteo/analyse/"><i class="fas fa-cloud-sun mr-2 text-info"></i>Analyse Météo</a></li>
                                <li><a href="/plannings/analyse-pieces/"><i class="fas fa-cogs mr-2 text-primary"></i>Analyse Pièces de Rechange</a></li>
                                
                            </ul>
                        </details>
                    </li>

                    
                    <li>
                        <details>
                            <summary><i class="fas fa-calendar-alt mr-2"></i>Plannings</summary>
                            <ul>
                                <li><a href="/plannings/"><i class="fas fa-chart-line mr-2"></i>Vue d'ensemble</a></li>
                                <li><a href="/plannings/liste/"><i class="fas fa-list mr-2 text-primary"></i>Liste Plannings</a></li>
                                <li><a href="/workflows-chantier/"><i class="fas fa-project-diagram mr-2 text-accent"></i>Workflow Chantier</a></li>
                                <li><a href="/plannings/calendrier/"><i class="fas fa-calendar-alt mr-2"></i>Vue calendrier</a></li>
                                <li><a href="/plannings/"><i class="fas fa-edit mr-2"></i>Saisie planning</a></li>
                                <li><a href="/plannings/reparations/"><i class="fas fa-tools mr-2 text-warning"></i>Suivi réparations</a></li>
                                <li class="divider">Opérations terrain</li>
                                <li><a href="/plannings/livraisons/"><i class="fas fa-hiking mr-2"></i>Livraison</a></li>
                                <li><a href="/plannings/avances/"><i class="fas fa-hand-holding-usd mr-2"></i>Avance</a></li>
                                <li><a href="/plannings/indemnites/"><i class="fas fa-coins mr-2 text-warning"></i>Indemnités Journalières</a></li>
                                <li><a href="/plannings/indemnites/hors-zone/"><i class="fas fa-route mr-2 text-warning"></i>Indemnités Hors Zone</a></li>
                                <li><a href="/facturation/caissiere/retours/"><i class="fas fa-undo mr-2 text-success"></i>Retour</a></li>
                                <li><a href="/plannings/indemnites/retour/"><i class="fas fa-file-invoice-dollar mr-2 text-success"></i>Retour Indemnités</a></li>
                                <li><a href="/facturation/frais-deplacement/retours/"><i class="fas fa-route mr-2 text-info"></i>Retour Frais Déplacement</a></li>
                                <li class="divider">Remboursements Famille</li>
                                <li><a href="/frais-medicaux/"><i class="fas fa-hospital-user mr-2 text-error"></i>Frais Médicaux</a></li>
                                <li><a href="/frais-scolarite/"><i class="fas fa-graduation-cap mr-2 text-info"></i>Frais de Scolarité</a></li>
                                <li class="divider">Suivi & Contrôle</li>
                                <li><a href="/inspections/"><i class="fas fa-clipboard-check mr-2 text-success"></i>Inspections & Maintenance</a></li>
                                <li><a href="/inspections/analyses-eau/"><i class="fas fa-flask mr-2 text-info"></i>Analyses d'eau</a></li>
                                <li><a href="#"><i class="fas fa-search mr-2 text-info"></i>Suivi avance</a></li>
                                <li class="divider">Planning & Activités</li>
                                <li><a href="/plannings/crud/types-activites/table/"><i class="fas fa-tasks mr-2 text-primary"></i>Types d'Activités</a></li>
                                <li><a href="/plannings/crud/types-designations/table/"><i class="fas fa-tag mr-2 text-info"></i>Types de Désignations</a></li>
                                <li><a href="/plannings/deplacements/"><i class="fas fa-route mr-2 text-warning"></i>Déplacements</a></li>
                                <li class="divider">Congés & Permissions</li>
                                <li><a href="/types-permissions/"><i class="fas fa-list mr-2 text-primary"></i>Types de Permissions</a></li>
                                <li><a href="/demandes-conges/"><i class="fas fa-calendar-check mr-2 text-info"></i>Demandes de Congés</a></li>
                                <li><a href="/suivi-conges/"><i class="fas fa-chart-line mr-2 text-success"></i>Suivi des Congés</a></li>
                                <li><a href="/recuperations/"><i class="fas fa-calendar-plus mr-2 text-warning"></i>Récupérations</a></li>
                                <li class="divider">Chantiers</li>
                                <li><a href="/chantiers/demandes/"><i class="fas fa-clipboard-list mr-2 text-primary"></i>Demandes Villages</a></li>
                                <li><a href="/chantiers/validations-sources/"><i class="fas fa-tint mr-2 text-info"></i>Validation Sources</a></li>
                                <li><a href="/chantiers/chantiers/"><i class="fas fa-hard-hat mr-2 text-warning"></i>Chantiers</a></li>
                                <li><a href="/chantiers/chantiers/kanban/"><i class="fas fa-th mr-2 text-accent"></i>Kanban Chantiers</a></li>
                                <li><a href="/chantiers/tacherons/"><i class="fas fa-user-hard-hat mr-2 text-secondary"></i>Tâcherons</a></li>
                                <li class="divider">WASH & Enquêtes</li>
                                <li><a href="/chantiers/chantiers/?enquetes=1"><i class="fas fa-home mr-2 text-success"></i>Ménages & Enquêtes</a></li>
                                <li><a href="/chantiers/chantiers/?animations=1"><i class="fas fa-chalkboard-teacher mr-2 text-info"></i>Animations WASH</a></li>
                                <li class="divider">Évaluation & Performance</li>
                                <li><a href="/plannings/crud/fiches-poste/table/"><i class="fas fa-tasks mr-2 text-primary"></i>Fiches de poste</a></li>
                                <li><a href="/employes/evaluations/"><i class="fas fa-star mr-2 text-warning"></i>Évaluations</a></li>
                                <li><a href="/plannings/evaluation-objectifs/"><i class="fas fa-chart-line mr-2 text-info"></i>Évaluation Objectifs Planning</a></li>
                            </ul>
                        </details>
                    </li>

                    <li>
                        <details>
                            <summary><i class="fas fa-credit-card mr-2"></i>Facturation</summary>
                            <ul>
                                <li class="divider">Volumétrique</li>
                                <li><a href="/facturation/releves/"><i class="fas fa-list mr-2"></i>Liste des relevés</a></li>
                                <li><a href="/facturation/facturation/"><i class="fas fa-calculator mr-2 text-success"></i>Facturation volumétrique</a></li>
                                <li><a href="/facturation/coupures-eau/"><i class="fas fa-faucet mr-2 text-warning"></i>Gestion coupures/remises eau</a></li>
                                <li><a href="/facturation/encaissement/"><i class="fas fa-cash-register mr-2 text-accent"></i>Encaissement factures</a></li>
                                <li><a href="/facturation/compteurs/"><i class="fas fa-tachometer-alt mr-2"></i>Compteurs de tête</a></li>
                                <li><a href="/plannings/volumetrique/"><i class="fas fa-tint mr-2 text-info"></i>Gestion volumétrique</a></li>
                                <li><a href="/facturation/demandes-bp/"><i class="fas fa-plug mr-2 text-warning"></i>Demandes BP</a></li>
                                <li><a href="/dashboard/expenses/"><i class="fas fa-file-invoice-dollar mr-2 text-error"></i>Dépenses services</a></li>
                                <li class="divider">Cartes sociales</li>
                                <li><a href="/facturation/cartes-sociales/"><i class="fas fa-print mr-2 text-info"></i>Émission tickets</a></li>
                                <li><a href="/facturation/cartes-sociales/encaissement/"><i class="fas fa-cash-register mr-2 text-success"></i>Encaissement</a></li>
                                <li class="divider">Forfaitaire</li>
                                <li><a href="/facturation/paiements-forfaitaires/"><i class="fas fa-money-bill-wave mr-2 text-success"></i>Controle paiements forfaitaires</a></li>
                                <li><a href="/facturation/suivi-forfaitaires/"><i class="fas fa-chart-line mr-2 text-info"></i>Suivi paiements forfaitaires</a></li>
                                <li class="divider">Usagers</li>
                                <li><a href="/usagers/representants/"><i class="fas fa-users mr-2 text-info"></i>Représentantes & Avis</a></li>
                                <li><a href="/comptabilite/etat-taxes-communales/"><i class="fas fa-university mr-2 text-secondary"></i>État Taxes Communales</a></li>
                                <li><a href="/comptabilite/etat-impot-synthetique/"><i class="fas fa-file-invoice-dollar mr-2 text-warning"></i>État Impôt Synthétique</a></li>
                                <li><a href="/comptabilite/dashboard-paiements-volume/"><i class="fas fa-tint mr-2 text-info"></i>Paiements au Volume</a></li>
                                <li><a href="/comptabilite/dashboard-paiements-forfaitaire/"><i class="fas fa-chart-line mr-2 text-success"></i>Paiements forfaitaires</a></li>
                                <li><a href="/comptabilite/dashboard-paiements-cartes-sociales/"><i class="fas fa-credit-card mr-2 text-success"></i>Paiements cartes sociales</a></li>
                            </ul>
                        </details>
                    </li>

                    <li>
                        <details>
                            <summary><i class="fas fa-boxes mr-2"></i>Achats/Stocks</summary>
                            <ul>
                                <li class="divider">Tableau de bord</li>
                                <li><a href="/stocks/"><i class="fas fa-chart-line mr-2"></i>Vue d'ensemble</a></li>
                                <li class="divider">Workflow Inventaire</li>
                                <li><a href="/stocks/stocks/"><i class="fas fa-warehouse mr-2"></i>Inventaires</a></li>
                                <li><a href="/stocks/fiches-stock/"><i class="fas fa-clipboard-list mr-2 text-primary"></i>Fiches de Stock</a></li>
                                <li><a href="/stocks/stock/resume/"><i class="fas fa-chart-bar mr-2 text-info"></i>Résumé Stocks</a></li>
                                <li><a href="/stocks/commandes/"><i class="fas fa-calculator mr-2 text-warning"></i>Calcul Commandes</a></li>
                                <li><a href="/stocks/purchases/"><i class="fas fa-receipt mr-2 text-primary"></i>Bons de Commande</a></li>
                                <li class="divider">Autres Opérations</li>
                                <li><a href="/stocks/achats/"><i class="fas fa-shopping-cart mr-2"></i>Saisie Achats</a></li>
                                <li><a href="/stocks/transferts/"><i class="fas fa-exchange-alt mr-2 text-info"></i>Transferts</a></li>
                                <li class="divider">Parc Véhicules</li>
                                <li><a href="/stocks/vehicules/"><i class="fas fa-motorcycle mr-2 text-accent"></i>Gestion Véhicules</a></li>
                            </ul>
                        </details>
                    </li>
                    

                    <!-- Conversations -->
                    <li>
                        <details>
                            <summary><i class="fas fa-comments mr-2 text-accent"></i>Conversations <span id="global-unread-badge-mobile" class="badge badge-error badge-xs ml-1 hidden">0</span></summary>
                            <ul>
                                <li><a href="/conversations/" class="flex items-center gap-3"><i class="fas fa-inbox text-accent"></i>Mes conversations</a></li>
                                <li><a onclick="event.preventDefault(); document.getElementById('newDirectModal')?.showModal()" class="flex items-center gap-3 cursor-pointer"><i class="fas fa-comment text-info"></i>Nouveau chat</a></li>
                                <li><a onclick="event.preventDefault(); document.getElementById('newGroupModal')?.showModal()" class="flex items-center gap-3 cursor-pointer"><i class="fas fa-users text-success"></i>Nouveau groupe</a></li>
                                <li class="divider">Assistant IA</li>
                                <li><a onclick="toggleFloatingChat()" class="flex items-center gap-3 cursor-pointer"><i class="fas fa-robot text-primary"></i>Ouvrir l'assistant</a></li>
                                <li><a onclick="openQuickQuery()" class="flex items-center gap-3 cursor-pointer"><i class="fas fa-bolt text-warning"></i>Requête rapide</a></li>
                                <li><a onclick="openCalculatorModal()" class="flex items-center gap-3 cursor-pointer"><i class="fas fa-calculator text-success"></i>Calculatrice</a></li>
                            </ul>
                        </details>
                    </li>
                    
                    <li>
                        <details>
                            <summary><i class="fas fa-calculator mr-2"></i>Comptabilité</summary>
                            <ul>
                                <li><a href="/comptabilite/dashboard/">Tableau de bord</a></li>
                                <li><a href="/comptabilite/entries/">Comptabilité DiameX</a></li>
                                <li><a href="/comptabilite/comparaison-soldes/"><i
                                            class="fas fa-balance-scale mr-2 text-info"></i>Comparaison Soldes</a></li>
                                <li><a href="/comptabilite/soldes-reels/"><i
                                            class="fas fa-file-invoice-dollar mr-2 text-success"></i>Soldes Réels</a>
                                </li>
                                <li><a href="/comptabilite/controle-conversion/"><i
                                            class="fas fa-exchange-alt mr-2 text-warning"></i>Contrôle Conversion</a>
                                </li>
                                <li><a href="/comptabilite/conversion-partie-double/"><i
                                            class="fas fa-balance-scale mr-2 text-primary"></i>Conversion Partie
                                        Double</a></li>
                                <li><a href="/comptabilite/import/">Import DiameX</a></li>
                                <li><a href="/comptabilite/temporaire/">Transactions
                                        Temporaires</a></li>
                                <li><a href="/comptabilite/temporaire/salaires/"><i
                                            class="fas fa-money-check-alt mr-2 text-success"></i>Export Paie &
                                        Charges</a></li>
                                <li class="divider">Budget & Fonds</li>
                                <li><a href="/comptabilite/budgets/"><i
                                            class="fas fa-list-alt mr-2 text-primary"></i>Budgets annuels</a></li>
                                <li><a href="/comptabilite/demandes-fonds/"><i
                                            class="fas fa-hand-holding-usd mr-2 text-success"></i>Demandes de fonds</a>
                                </li>
                                <li class="divider">Vérifications</li>
                                <li><a href="/comptabilite/verification-unifiee/" class="font-bold"><i
                                            class="fas fa-clipboard-check mr-2 text-primary"></i>o Vérification
                                        Unifiée</a></li>
                                <li><a href="/comptabilite/verification-scans/"><i
                                            class="fas fa-file-pdf mr-2 text-warning"></i>Vérification scans</a></li>
                                <li><a href="/verification-paiements/"><i
                                            class="fas fa-clipboard-check mr-2 text-primary"></i>Vérification Paiements
                                        Employés</a></li>
                                <li><a href="/verification-paiements-croisee/"><i
                                            class="fas fa-table mr-2 text-warning"></i>Analyse Croisée (Mois -
                                        Types)</a></li>
                                <li><a href="/comptabilite/verification-fournisseurs/"><i
                                            class="fas fa-hiking mr-2 text-success"></i>Vérification Fournisseurs</a>
                                </li>
                                <li><a href="/comptabilite/verification-avec-ouvrage/"><i
                                            class="fas fa-building mr-2 text-accent"></i>Vérification avec Ouvrage</a>
                                </li>
                                <li><a href="/comptabilite/verification-sans-ouvrage/"><i
                                            class="fas fa-file-invoice mr-2 text-info"></i>Vérification sans Ouvrage</a>
                                </li>
                                <li class="divider">Évaluation</li>
                                <li><a href="/comptabilite/evaluation-saisie/"><i
                                            class="fas fa-chart-line mr-2 text-success"></i>Évaluation Saisie</a></li>
                                <li class="divider">Recoupements</li>
                                <li><a href="/comptabilite/recoupement/planning/"><i
                                            class="fas fa-calendar-alt mr-2 text-warning"></i>Recoupement Planning</a>
                                </li>
                                <li><a href="/comptabilite/recoupement/achats/"><i
                                            class="fas fa-shopping-cart mr-2 text-warning"></i>Recoupement Achats</a>
                                </li>
                                <li class="divider">Documentation</li>
                                <li><a href="/comptabilite/documentation/saisie/"><i
                                            class="fas fa-folder-open mr-2 text-primary"></i>Saisie documents</a></li>
                                <li><a href="/comptabilite/documentation/rapport/"><i
                                            class="fas fa-chart-bar mr-2 text-info"></i>Rapport documents</a></li>
                                <li class="divider">Déclarations & Taxes</li>
                                <li><a href="/comptabilite/declaration-communication/"><i
                                            class="fas fa-file-invoice mr-2 text-error"></i>Déclaration Communication
                                        Impôts</a></li>
                                <li><a href="/comptabilite/natures-declaration/"><i
                                            class="fas fa-tags mr-2 text-warning"></i>Natures de Déclaration</a></li>
                            </ul>
                        </details>
                    </li>
                    


                    
                    <li>
                        <details>
                            <summary><i class="fas fa-cogs mr-2"></i>Référentiel</summary>
                            <ul>
                                <li class="divider">Interface Admin</li>
                                <li><a href="/admin/"><i class="fas fa-tools mr-2"></i>Interface Django</a></li>
                                <li><a href="/fichiers/"><i class="fas fa-folder-open mr-2"></i>Gestion Fichiers</a></li>
                                <li class="divider">Géographie</li>
                                <li>
                                    <a href="/geography/" class="tooltip tooltip-right"
                                        data-tip="Régions, Districts, Communes, Fokontanys, Villages, Parcelles">
                                        <i class="fas fa-map-marker-alt mr-2 text-info"></i>Géographie
                                    </a>
                                </li>
                                <li><a href="/geography/consolidated/"><i class="fas fa-table mr-2 text-success"></i>Géographie Consolidée</a></li>
                                <li><a href="/geography/capture-donnees/"><i class="fas fa-mobile-alt mr-2 text-warning"></i>Capture Données Terrain</a>
                                </li>
                                <li>
                                    <a href="/organisations/" class="tooltip tooltip-right"
                                        data-tip="Organisations, Bases, Comptes, Postes, Magasins, Journaux, Employés">
                                        <i class="fas fa-building mr-2 text-primary"></i>Organisations
                                    </a>
                                </li>
                                <li><a href="/facturation/fournisseurs/"><i class="fas fa-store mr-2 text-success"></i>Fournisseurs</a></li>
                                <li class="divider">Ouvrages</li>
                                <li>
                                    <a href="/organisations/ouvrages/" class="tooltip tooltip-right"
                                        data-tip="Ouvrages, Points d'Eau, Équipements, Compteurs, Tarifs, Modalités, Adresses, Fournisseurs, Cartes Sociales">
                                        <i class="fas fa-tools mr-2 text-warning"></i>Ouvrages
                                    </a>
                                </li>
                                <li><a href="/facturation/consolidated-points-eau/"><i class="fas fa-tint mr-2 text-info"></i>Points d'Eau Consolidés</a></li>
                                <li><a href="/consolidated-equipements/"><i class="fas fa-cogs mr-2 text-accent"></i>Équipements Consolidés</a></li>
                                <li><a href="/ouvrages/types/"><i class="fas fa-cogs mr-2 text-accent"></i>Types d'Ouvrages</a></li>
                                <li><a href="/organisations/types-equipements/"><i class="fas fa-tools mr-2 text-warning"></i>Types d'Équipements</a></li>
                                <li><a href="/facturation/types-points-eau/"><i class="fas fa-tint mr-2 text-secondary"></i>Types Points d'Eau</a></li>
                                <li class="divider">Planning & Activités</li>
                                <li><a href="/plannings/crud/types-activites/table/"><i class="fas fa-tasks mr-2 text-primary"></i>Types d'Activités</a></li>
                                <li><a href="/plannings/crud/types-designations/table/"><i class="fas fa-tag mr-2 text-info"></i>Types de Désignations</a></li>
                                <li><a href="/plannings/deplacements/"><i class="fas fa-route mr-2 text-warning"></i>Déplacements</a></li>
                                <li class="divider">Inspections & Contrôle</li>
                                <li><a href="/inspections/gestion-checklists/"><i class="fas fa-clipboard-check mr-2 text-warning"></i>Checklists & Activités Correctives</a></li>
                                <li><a href="/inspections/points-controle/table/"><i class="fas fa-bullseye mr-2 text-info"></i>Points de Contrôle (Tableau)</a></li>
                                <li><a href="/inspections/analyses-eau/"><i class="fas fa-flask mr-2 text-info"></i>Analyses d'eau</a></li>
                                <li class="divider">Documentation</li>
                                <li><a href="/systeme/manuel/"><i class="fas fa-book text-info mr-2"></i>Manuel d'utilisateur</a></li>
                                <li><a href="/documentation/architecture/"><i class="fas fa-sitemap mr-2 text-primary"></i>Architecture & Workflows</a>
                                </li>
                            </ul>
                        </details>
                    </li>

                    
                    <li>
                        <details>
                            <summary><i class="fas fa-cogs mr-2"></i>Administration</summary>
                            <ul>
                                <li class="divider">Ressources Humaines</li>
                                <li><a href="/employes/list/"><i
                                            class="fas fa-users mr-2 text-primary"></i>Employés</a></li>
                                <li><a href="/positions-gps/"><i class="fas fa-map-marked-alt mr-2 text-info"></i>Positions GPS Employes</a></li>
                                <li><a href="/employes-cascade/"><i
                                            class="fas fa-database mr-2 text-info"></i>Employés & Bases DiameX</a></li>
                                <li><a href="/postes/"><i
                                            class="fas fa-briefcase mr-2 text-secondary"></i>Postes</a></li>
                                <li><a href="/contrats-travail/"><i
                                            class="fas fa-file-contract mr-2 text-warning"></i>Contrats Travail & Avenants</a></li>
                                            <li><a href="/gardiens/"><i
                                            class="fas fa-shield-alt mr-2 text-primary"></i>Gestion des Gardiens</a>
                                </li>
                                <li><a href="/grilles-salaire/"><i
                                            class="fas fa-money-check-alt mr-2 text-success"></i>Grilles de Salaire</a>
                                </li>
                                <li><a href="/fiches-paie-mensuelles/"><i
                                            class="fas fa-file-invoice mr-2 text-primary"></i>Fiches de Paie
                                        Mensuelles</a></li>
                                <li><a href="/paiements-irsa/"><i
                                            class="fas fa-receipt mr-2 text-warning"></i>Paiements IRSA</a></li>
                            <li><a href="/paiements-cnaps-fmfp/"><i
                                            class="fas fa-file-invoice-dollar mr-2 text-info"></i>Paiements
                                        CNaPS/FMFP</a></li>
                            <li><a href="/paiements-mutuelle-sante/"><i
                                            class="fas fa-hospital mr-2 text-success"></i>Paiements Mutuelle Santé</a>
                                </li>
                            <li><a href="/paiements-iri/"><i
                                            class="fas fa-percentage mr-2 text-error"></i>Paiements IRI</a></li>
                                <li class="divider">Recrutement</li>
                                <li><a href="/recrutement/inscription/"><i
                                            class="fas fa-user-plus mr-2 text-success"></i>Test de Recrutement</a>
                                </li>
                                <li><a href="/recrutement/gestion/candidats/"><i
                                            class="fas fa-user-tie mr-2 text-success"></i>Candidats Préconfigurés</a>
                                </li>
                                <li><a href="/recrutement/gestion/questions/"><i
                                            class="fas fa-question-circle mr-2 text-info"></i>Questions de Test</a></li>
                                <li><a href="/recrutement/gestion/resultats/"><i class="fas fa-clipboard-check mr-2 text-primary"></i>Résultats candidats</a></li>
                                <li class="divider">Configuration</li>
                                <li><a href="/config/salaire/"><i
                                            class="fas fa-money-bill-wave mr-2 text-success"></i>Configuration
                                        Salaires</a></li>
                                <li><a href="/config/tranches-irsa/"><i
                                            class="fas fa-calculator mr-2 text-warning"></i>Tranches IRSA</a></li>
                                <li class="divider">Budget & Prévisions</li>
                                <li><a href="/facturation/previsions/"><i
                                            class="fas fa-chart-line mr-2 text-success"></i>Prévisions budgétaires</a>
                                </li>
                                <li class="divider">Système</li>
                                <li><a href="/systeme/users/"><i
                                            class="fas fa-users-cog mr-2"></i>Gestion utilisateurs</a></li>
                                <li><a href="/systeme/parameters/"><i
                                            class="fas fa-sliders-h mr-2"></i>Paramètres système</a></li>
                                <li><a href="/systeme/logs/"><i
                                            class="fas fa-file-alt mr-2"></i>Logs & monitoring</a></li>
                            </ul>
                        </details>
                    </li>

                    
                    
                    
                    
                    
                </ul>
            </div>
            <a href="/" class="btn btn-ghost text-xl font-bold text-accent">
                <img src="/static/images/icons/icons8-vase-94.png" alt="Hydria" class="h-6 w-6 mr-2">
                <span>Hydria</span>
            </a>
        </div>

<div class="navbar-center hidden lg:flex">
            <ul class="desktop-main-menu flex flex-wrap justify-center items-center gap-1 w-full"
                style="display:flex;flex-direction:row;flex-wrap:wrap;justify-content:center;align-items:center;gap:.3rem;width:100%;">
                
                
                
                <!-- Page d'accueil Applications - EN PREMIER -->
                <li>
                    <a href="/accueil/" class="btn btn-sm bg-gradient-to-r from-primary to-accent text-primary-content hover:shadow-lg">
                        <i class="fas fa-th mr-1"></i>Applications
                    </a>
                </li>

                <!-- Recherche globale -->
                <li>
                    <a href="/recherche/" class="btn btn-ghost btn-sm">
                        <i class="fas fa-search mr-1 text-primary"></i>Recherche
                    </a>
                </li>

                <!-- Tableaux de bord & Rapports groupés -->
                <li>
                    <div class="dropdown dropdown-hover dropdown-end">
                        <div tabindex="0" role="button" class="btn btn-ghost btn-sm">
                            <i class="fas fa-tachometer-alt mr-1"></i>Tableaux & Rapports<i class="fas fa-chevron-down ml-1 text-xs"></i>
                        </div>
                        <ul tabindex="0" class="dropdown-content menu bg-base-100 rounded-box z-[1] w-72 p-2 shadow border border-base-300">
                            
                            <li class="menu-title text-xs text-primary font-semibold px-2 py-1">Tableaux de Bord</li>
                            <li><a href="/dashboard/"><i class="fas fa-home mr-2"></i>Vue d'ensemble</a></li>
                            <li><a href="/geography/dashboard/"><i class="fas fa-map-marked-alt mr-2 text-primary"></i>Géographie & Population</a></li>
                            <li><a href="/dashboard/carte/"><i class="fas fa-map mr-2 text-accent"></i>Carte interactive</a></li>
                            <li><a href="/dashboard/paiements-forfaitaires/"><i class="fas fa-coins mr-2 text-warning"></i>Paiements forfaitaires</a></li>
                            <li><a href="/plannings/volumetrique/global/"><i class="fas fa-tint mr-2 text-info"></i>Paiements au volume</a></li>
                            <li><a href="/plannings/conso-cartes-sociales/global/"><i class="fas fa-credit-card mr-2 text-success"></i>Paiements cartes sociales</a></li>
                            <li><a href="/dashboard/depenses/"><i class="fas fa-chart-line mr-2 text-error"></i>Dépenses</a></li>
                            <li><a href="/dashboard/infrastructures/"><i class="fas fa-tools mr-2 text-success"></i>État des ouvrages</a></li>
                            <li><a href="/comptabilite/dashboard/"><i class="fas fa-calculator mr-2 text-primary"></i>Comptabilité</a></li>
                            <li><hr class="my-1"></li>
                            <li class="menu-title text-xs text-secondary font-semibold px-2 py-1">Rapports & Analyses</li>
                            <li><a href="/rapports/"><i class="fas fa-dashboard mr-2"></i>Tableau de bord rapports</a></li>
                            <li><a href="/rapports/activites-par-employe/"><i class="fas fa-users mr-2"></i>Activités par employé</a></li>
                            <li><a href="/rapports/performance-bases/"><i class="fas fa-building mr-2"></i>Performance bases</a></li>
                            <li><a href="/rapports/indicateurs-diamex/"><i class="fas fa-sync mr-2"></i>Indicateurs DiameX</a></li>
                            <li><a href="/plannings/visites/"><i class="fas fa-chart-bar mr-2 text-info"></i>Comptage visites</a></li>
                            <li><a href="/organisations/ouvrages/grading-annuel/"><i class="fas fa-chart-line mr-2 text-success"></i>Gradings Annuels Ouvrages</a></li>
                            <li><a href="/organisations/ouvrages/grading-annuel/analyse/"><i class="fas fa-chart-bar mr-2 text-info"></i>Analyse des Gradings</a></li>
                            <li><hr class="my-1"></li>
                            <li class="menu-title text-xs text-secondary font-semibold px-2 py-1">Analyses consommation</li>
                            <li><a href="/plannings/volumetrique/analyse-consommation/"><i class="fas fa-chart-line mr-2 text-success"></i>Analyse consommation</a></li>
                            <li><a href="/plannings/volumetrique/analyse-par-point-eau/"><i class="fas fa-tint mr-2 text-info"></i>Analyse par point d'eau</a></li>
                            <li><a href="/plannings/volumetrique/tableau-points-eau/"><i class="fas fa-table mr-2 text-primary"></i>Tableau points d'eau</a></li>
                            <li><a href="/plannings/cartes-sociales/analyse/"><i class="fas fa-id-card mr-2 text-warning"></i>Analyse Cartes Sociales</a></li>
                            <li><a href="/plannings/meteo/analyse/"><i class="fas fa-cloud-sun mr-2 text-info"></i>Analyse Météo</a></li>
                            <li><a href="/plannings/analyse-pieces/"><i class="fas fa-cogs mr-2 text-primary"></i>Analyse Pièces de Rechange</a></li>
                            
                        </ul>
                    </div>
                </li>

                
                <!-- Plannings avec dropdown -->
                <li>
                    <div class="dropdown dropdown-hover dropdown-end">
                        <div tabindex="0" role="button" class="btn btn-ghost btn-sm">
                            <i class="fas fa-calendar-alt mr-1"></i>Plannings<i class="fas fa-chevron-down ml-1 text-xs"></i>
                        </div>
                        <ul tabindex="0" class="dropdown-content menu bg-base-100 rounded-box z-[1] w-72 p-2 shadow border border-base-300">
                            <li><a href="/plannings/"><i class="fas fa-chart-line mr-2"></i>Vue d'ensemble</a></li>
                            <li><a href="/plannings/liste/"><i class="fas fa-list mr-2 text-primary"></i>Liste Plannings</a></li>
                            <li><a href="/workflows-chantier/"><i class="fas fa-project-diagram mr-2 text-accent"></i>Workflow Chantier</a></li>
                            <li><a href="/plannings/calendrier/"><i class="fas fa-calendar-alt mr-2"></i>Vue calendrier</a></li>
                            <li><a href="/plannings/"><i class="fas fa-edit mr-2"></i>Saisie planning</a></li>
                            <li><a href="/plannings/reparations/"><i class="fas fa-tools mr-2 text-warning"></i>Suivi réparations</a></li>
                            <li><hr class="my-1"></li>
                            <li class="menu-title text-xs text-base-content/70 font-semibold px-2 py-1">Opérations terrain</li>
                            <li><a href="/plannings/livraisons/"><i class="fas fa-hiking mr-2"></i>Livraison</a></li>
                            <li><a href="/plannings/avances/"><i class="fas fa-hand-holding-usd mr-2"></i>Avance</a></li>
                            <li><a href="/plannings/indemnites/"><i class="fas fa-coins mr-2 text-warning"></i>Indemnités Journalières</a></li>
                            <li><a href="/plannings/indemnites/hors-zone/"><i class="fas fa-route mr-2 text-warning"></i>Indemnités Hors Zone</a></li>
                            <li><a href="/facturation/caissiere/retours/"><i class="fas fa-undo mr-2 text-success"></i>Retour</a></li>
                            <li><a href="/plannings/indemnites/retour/"><i class="fas fa-file-invoice-dollar mr-2 text-success"></i>Retour Indemnités</a></li>
                            <li><a href="/facturation/frais-deplacement/retours/"><i class="fas fa-route mr-2 text-info"></i>Retour Frais Déplacement</a></li>
                            <li><hr class="my-1"></li>
                            <li class="menu-title text-xs text-secondary font-semibold px-2 py-1">Remboursements Famille</li>
                            <li><a href="/frais-medicaux/"><i class="fas fa-hospital-user mr-2 text-error"></i>Frais Médicaux</a></li>
                            <li><a href="/frais-scolarite/"><i class="fas fa-graduation-cap mr-2 text-info"></i>Frais de Scolarité</a></li>
                            <li><hr class="my-1"></li>
                            <li class="menu-title text-xs text-base-content/70 font-semibold px-2 py-1">Suivi & Contrôle</li>
                            <li><a href="/inspections/"><i class="fas fa-clipboard-check mr-2 text-success"></i>Inspections & Maintenance</a></li>
                            <li><a href="/inspections/analyses-eau/"><i class="fas fa-flask mr-2 text-info"></i>Analyses d'eau</a></li>


                            <li><a href="#"><i class="fas fa-search mr-2 text-info"></i>Suivi avance</a></li>
                            <li><hr class="my-1"></li>
                            <li class="menu-title text-xs text-base-content/70 font-semibold px-2 py-1">Planning & Activités</li>
                            <li><a href="/plannings/crud/types-activites/table/"><i class="fas fa-tasks mr-2 text-primary"></i>Types d'Activités</a></li>
                            <li><a href="/plannings/crud/types-designations/table/"><i class="fas fa-tag mr-2 text-info"></i>Types de Désignations</a></li>
                            <li><a href="/plannings/deplacements/"><i class="fas fa-route mr-2 text-warning"></i>Déplacements</a></li>
                            <li><hr class="my-1"></li>
                            <li class="menu-title text-xs text-info font-semibold px-2 py-1">Congés & Permissions</li>
                            <li><a href="/types-permissions/"><i class="fas fa-list mr-2 text-primary"></i>Types de Permissions</a></li>
                            <li><a href="/demandes-conges/"><i class="fas fa-calendar-check mr-2 text-info"></i>Demandes de Congés</a></li>
                            <li><a href="/suivi-conges/"><i class="fas fa-chart-line mr-2 text-success"></i>Suivi des Congés</a></li>
                            <li><a href="/recuperations/"><i class="fas fa-calendar-plus mr-2 text-warning"></i>Récupérations</a></li>
                            <li><hr class="my-1"></li>
                            <li class="menu-title text-xs text-primary font-semibold px-2 py-1">Chantiers</li>
                            <li><a href="/chantiers/demandes/"><i class="fas fa-clipboard-list mr-2 text-primary"></i>Demandes Villages</a></li>
                            <li><a href="/chantiers/validations-sources/"><i class="fas fa-tint mr-2 text-info"></i>Validation Sources</a></li>
                            <li><a href="/chantiers/chantiers/"><i class="fas fa-hard-hat mr-2 text-warning"></i>Chantiers</a></li>
                            <li><a href="/chantiers/chantiers/kanban/"><i class="fas fa-th mr-2 text-accent"></i>Kanban Chantiers</a></li>
                            <li><a href="/chantiers/tacherons/"><i class="fas fa-user-hard-hat mr-2 text-secondary"></i>Tâcherons</a></li>
                            <li><hr class="my-1"></li>
                            <li class="menu-title text-xs text-success font-semibold px-2 py-1">WASH & Enquêtes</li>
                            <li><a href="/chantiers/chantiers/?enquetes=1"><i class="fas fa-home mr-2 text-success"></i>Ménages & Enquêtes</a></li>
                            <li><a href="/chantiers/chantiers/?animations=1"><i class="fas fa-chalkboard-teacher mr-2 text-info"></i>Animations WASH</a></li>
                            <li><hr class="my-1"></li>
                            <li class="menu-title text-xs text-base-content/70 font-semibold px-2 py-1">Configuration planning</li>
                            <li><a href="/plannings/crud/types-activites/table/"><i class="fas fa-tasks mr-2 text-primary"></i>Types d'Activités</a></li>
                            <li><a href="/plannings/crud/types-designations/table/"><i class="fas fa-tag mr-2 text-info"></i>Types de Désignations</a></li>
                            <li><hr class="my-1"></li>
                            <li class="menu-title text-xs text-warning font-semibold px-2 py-1">Évaluation & Performance</li>
                            <li><a href="/plannings/crud/fiches-poste/table/"><i class="fas fa-tasks mr-2 text-primary"></i>Fiches de poste</a></li>
                            <li><a href="/employes/evaluations/"><i class="fas fa-star mr-2 text-warning"></i>Évaluations</a></li>
                            <li><a href="/plannings/evaluation-objectifs/"><i class="fas fa-chart-line mr-2 text-info"></i>Évaluation Objectifs Planning</a></li>
                        </ul>
                    </div>
                </li>

                <!-- Facturation complète : Paiements, Relevés & Cartes sociales groupés -->
                <li>
                    <div class="dropdown dropdown-hover dropdown-end">
                        <div tabindex="0" role="button" class="btn btn-ghost btn-sm">
                            <i class="fas fa-credit-card mr-1"></i>Facturation<i class="fas fa-chevron-down ml-1 text-xs"></i>
                        </div>
                        <ul tabindex="0" class="dropdown-content menu bg-base-100 rounded-box z-[1] w-64 p-2 shadow border border-base-300">
                            <li class="menu-title text-xs text-warning font-semibold px-2 py-1">Volumtrique</li>
                            <li><a href="/facturation/releves/"><i class="fas fa-list mr-2"></i>Liste des relevés</a></li>
                            <li><a href="/facturation/facturation/"><i class="fas fa-calculator mr-2 text-success"></i>Facturation volumétrique</a></li>
                            <li><a href="/facturation/coupures-eau/"><i class="fas fa-faucet mr-2 text-warning"></i>Gestion coupures/remises eau</a></li>
                            <li><a href="/facturation/encaissement/"><i class="fas fa-cash-register mr-2 text-accent"></i>Encaissement factures</a></li>
                            <li><a href="/facturation/compteurs/"><i class="fas fa-tachometer-alt mr-2"></i>Compteurs de tête</a></li>
                            <li><a href="/plannings/volumetrique/"><i class="fas fa-tint mr-2 text-info"></i>Gestion volumétrique</a></li>
                            <li><a href="/facturation/demandes-bp/"><i class="fas fa-plug mr-2 text-warning"></i>Demandes BP</a></li>
                            <li><a href="/dashboard/expenses/"><i class="fas fa-file-invoice-dollar mr-2 text-error"></i>Dépenses services</a></li>
                            <li><hr class="my-1"></li>
                            <li class="menu-title text-xs text-success font-semibold px-2 py-1">Cartes sociales</li>
                            <li><a href="/facturation/cartes-sociales/"><i class="fas fa-print mr-2 text-info"></i>Émission tickets</a></li>
                            <li><a href="/facturation/cartes-sociales/encaissement/"><i class="fas fa-cash-register mr-2 text-success"></i>Encaissement</a></li>
                            <li><hr class="my-1"></li>
                            <li class="menu-title text-xs text-info font-semibold px-2 py-1">Forfaitaire</li>
                            <li><a href="/facturation/paiements-forfaitaires/"><i class="fas fa-money-bill-wave mr-2 text-success"></i>Controle paiements forfaitaires</a></li>
                            <li><a href="/facturation/suivi-forfaitaires/"><i class="fas fa-chart-line mr-2 text-info"></i>Suivi paiements forfaitaires</a></li>
                            <li><hr class="my-1"></li>
                            <li class="menu-title text-xs text-info font-semibold px-2 py-1">Usagers</li>
                            <li><a href="/usagers/representants/"><i class="fas fa-users mr-2 text-info"></i>Représentantes & Avis</a></li>
                            <li><a href="/comptabilite/etat-taxes-communales/"><i class="fas fa-university mr-2 text-secondary"></i>État Taxes Communales</a></li>
                            <li><a href="/comptabilite/etat-impot-synthetique/"><i class="fas fa-file-invoice-dollar mr-2 text-warning"></i>État Impôt Synthétique</a></li>
                            <li><a href="/comptabilite/dashboard-paiements-volume/"><i class="fas fa-tint mr-2 text-info"></i>Paiements au Volume</a></li>
                            <li><a href="/comptabilite/dashboard-paiements-forfaitaire/"><i class="fas fa-chart-line mr-2 text-success"></i>Paiements forfaitaires</a></li>
                            <li><a href="/comptabilite/dashboard-paiements-cartes-sociales/"><i class="fas fa-credit-card mr-2 text-success"></i>Paiements cartes sociales</a></li>
                        </ul>
                    </div>
                </li>

                <!-- Achats/Stocks avec dropdown -->
                <li>
                    <div class="dropdown dropdown-hover dropdown-end">
                        <div tabindex="0" role="button" class="btn btn-ghost btn-sm">
                            <i class="fas fa-boxes mr-1"></i>Achats/Stocks<i class="fas fa-chevron-down ml-1 text-xs"></i>
                        </div>
                        <ul tabindex="0" class="dropdown-content menu bg-base-100 rounded-box z-[1] w-64 p-2 shadow border border-base-300">
                            <li class="menu-title text-xs font-semibold px-2 py-1">?? Tableau de bord</li>
                            <li><a href="/stocks/"><i class="fas fa-chart-line mr-2"></i>Vue d'ensemble</a></li>
                            <li><hr class="my-1"></li>
                            <li class="menu-title text-xs text-success font-semibold px-2 py-1">?? Workflow Inventaire</li>
                            <li><a href="/stocks/stocks/"><i class="fas fa-warehouse mr-2"></i>Inventaires</a></li>
                            <li><a href="/stocks/fiches-stock/"><i class="fas fa-clipboard-list mr-2 text-primary"></i>Fiches de Stock</a></li>
                            <li><a href="/stocks/stock/resume/"><i class="fas fa-chart-bar mr-2 text-info"></i>Résumé Stocks</a></li>
                            <li><a href="/stocks/commandes/"><i class="fas fa-calculator mr-2 text-warning"></i>Calcul Commandes</a></li>
                            <li><a href="/stocks/purchases/"><i class="fas fa-receipt mr-2 text-primary"></i>Bons de Commande</a></li>
                            <li><hr class="my-1"></li>
                            <li class="menu-title text-xs text-info font-semibold px-2 py-1">?? Autres Opérations</li>
                            <li><a href="/stocks/achats/"><i class="fas fa-shopping-cart mr-2"></i>Saisie Achats</a></li>
                            <li><a href="/stocks/transferts/"><i class="fas fa-exchange-alt mr-2 text-info"></i>Transferts</a></li>
                            <li><hr class="my-1"></li>
                            <li class="menu-title text-xs text-accent font-semibold px-2 py-1">??? Parc Véhicules</li>
                            <li><a href="/stocks/vehicules/"><i class="fas fa-motorcycle mr-2 text-accent"></i>Gestion Véhicules</a></li>
                        </ul>
                    </div>
                </li>
                

                <!-- Conversations avec dropdown -->
                <li>
                    <div class="dropdown dropdown-hover dropdown-end">
                        <div tabindex="0" role="button" class="btn btn-ghost btn-sm">
                            <i class="fas fa-comments mr-1 text-accent"></i>Conversations <span id="global-unread-badge" class="badge badge-error badge-xs ml-1 hidden">0</span><i class="fas fa-chevron-down ml-1 text-xs"></i>
                        </div>
                        <ul tabindex="0" class="dropdown-content menu bg-base-100 rounded-box z-[1] w-64 p-2 shadow border border-base-300">
                            <li class="menu-title text-xs text-accent font-semibold px-2 py-1">Conversations</li>
                            <li><a href="/conversations/" class="flex items-center gap-3"><i class="fas fa-inbox text-accent"></i>Mes conversations</a></li>
                            <li><a onclick="event.preventDefault(); document.getElementById('newDirectModal')?.showModal()" class="flex items-center gap-3 cursor-pointer"><i class="fas fa-comment text-info"></i>Nouveau chat</a></li>
                            <li><a onclick="event.preventDefault(); document.getElementById('newGroupModal')?.showModal()" class="flex items-center gap-3 cursor-pointer"><i class="fas fa-users text-success"></i>Nouveau groupe</a></li>
                            <li><hr class="my-1"></li>
                            <li class="menu-title text-xs text-primary font-semibold px-2 py-1">Assistant IA</li>
                            <li><a onclick="toggleFloatingChat()" class="flex items-center gap-3 cursor-pointer"><i class="fas fa-robot text-primary"></i>Ouvrir l'assistant</a></li>
                            <li><a onclick="openQuickQuery()" class="flex items-center gap-3 cursor-pointer"><i class="fas fa-bolt text-warning"></i>Requête rapide</a></li>
                            <li><a onclick="openCalculatorModal()" class="flex items-center gap-3 cursor-pointer"><i class="fas fa-calculator text-success"></i>Calculatrice</a></li>
                        </ul>
                    </div>
                </li>

                <!-- Comptabilité avec dropdown -->
                
                <li>
                    <div class="dropdown dropdown-hover dropdown-end">
                        <div tabindex="0" role="button" class="btn btn-ghost btn-sm">
                            <i class="fas fa-calculator mr-1"></i>Comptabilité<i class="fas fa-chevron-down ml-1 text-xs"></i>
                        </div>
                        <ul tabindex="0" class="dropdown-content menu bg-base-100 rounded-box z-[1] w-72 p-2 shadow border border-base-300">
                            <li class="menu-title text-xs text-primary font-semibold px-2 py-1">Tableau de bord</li>
                            <li><a href="/comptabilite/dashboard/"><i class="fas fa-chart-line mr-2 text-primary"></i>Vue d'ensemble comptable</a></li>
                            <li><hr class="my-1"></li>
                            <li class="menu-title text-xs text-info font-semibold px-2 py-1">Base DiameX</li>
                            <li><a href="/comptabilite/import/"><i class="fas fa-file-import mr-2 text-primary"></i>Import depuis Access</a></li>
                            <li><a href="/comptabilite/entries/"><i class="fas fa-book mr-2 text-info"></i>Écritures comptables (DATA)</a></li>
                            <li><a href="/comptabilite/temporaire/"><i class="fas fa-exchange-alt mr-2 text-accent"></i>Transactions temporaires</a></li>
                            <li><a href="/comptabilite/temporaire/salaires/"><i class="fas fa-money-check-alt mr-2 text-success"></i>Export Paie & Charges</a></li>
                            <li><a href="/comptabilite/diagnostic/soldes/"><i class="fas fa-search-dollar mr-2 text-success"></i>Diagnostic Soldes</a></li>
                            <li><a href="/comptabilite/comparaison-soldes/"><i class="fas fa-balance-scale mr-2 text-success"></i>Comparaison soldes</a></li>
                            <li><a href="/comptabilite/soldes-reels/"><i class="fas fa-file-invoice-dollar mr-2 text-warning"></i>Soldes Réels</a></li>
                            <li><a href="/comptabilite/controle-conversion/"><i class="fas fa-exchange-alt mr-2 text-warning"></i>Contrôle Conversion</a></li>
                            <li><a href="/comptabilite/conversion-partie-double/"><i class="fas fa-balance-scale mr-2 text-primary"></i>Conversion Partie Double</a></li>
                            <li><hr class="my-1"></li>
                            <li class="menu-title text-xs text-success font-semibold px-2 py-1">Budget & Fonds</li>
                            <li><a href="/comptabilite/budgets/"><i class="fas fa-list-alt mr-2 text-primary"></i>Budgets annuels</a></li>
                            <li><a href="/comptabilite/demandes-fonds/"><i class="fas fa-hand-holding-usd mr-2 text-success"></i>Demandes de fonds</a></li>
                            <li><hr class="my-1"></li>
                            <li class="menu-title text-xs text-info font-semibold px-2 py-1">Vérifications</li>
                            <li><a href="/comptabilite/verification-unifiee/" class="font-bold"><i class="fas fa-clipboard-check mr-2 text-primary"></i>o Vérification Unifiée</a></li>
                            <li><a href="/comptabilite/verification-scans/"><i class="fas fa-file-pdf mr-2 text-warning"></i>Vérification scans</a></li>
                            <li><a href="/verification-paiements/"><i class="fas fa-clipboard-check mr-2 text-primary"></i>Vérification Paiements Employés</a></li>
                            <li><a href="/verification-paiements-croisee/"><i class="fas fa-table mr-2 text-warning"></i>Analyse Croisée (Mois - Types)</a></li>
                            <li><a href="/comptabilite/verification-fournisseurs/"><i class="fas fa-hiking mr-2 text-success"></i>Vérification Fournisseurs</a></li>
                            <li><a href="/comptabilite/verification-avec-ouvrage/"><i class="fas fa-building mr-2 text-accent"></i>Vérification avec Ouvrage</a></li>
                            <li><a href="/comptabilite/verification-sans-ouvrage/"><i class="fas fa-file-invoice mr-2 text-info"></i>Vérification sans Ouvrage</a></li>
                            <li><hr class="my-1"></li>
                            <li class="menu-title text-xs text-success font-semibold px-2 py-1">Évaluation</li>
                            <li><a href="/comptabilite/evaluation-saisie/"><i class="fas fa-chart-line mr-2 text-success"></i>Évaluation Saisie</a></li>
                            <li><hr class="my-1"></li>
                            <li class="menu-title text-xs text-warning font-semibold px-2 py-1">Recoupements</li>
                            <li><a href="/comptabilite/recoupement/planning/"><i class="fas fa-calendar-alt mr-2 text-warning"></i>Recoupement planning</a></li>
                            <li><a href="/comptabilite/recoupement/achats/"><i class="fas fa-shopping-cart mr-2 text-success"></i>Recoupement achats</a></li>
                            <li><hr class="my-1"></li>
                            <li class="menu-title text-xs text-error font-semibold px-2 py-1">Documentation</li>
                            <li><a href="/comptabilite/documentation/saisie/"><i class="fas fa-folder-open mr-2 text-primary"></i>Saisie documents</a></li>
                            <li><a href="/comptabilite/documentation/rapport/"><i class="fas fa-chart-bar mr-2 text-info"></i>Rapport documents</a></li>
                            <li><hr class="my-1"></li>
                            <li class="menu-title text-xs text-error font-semibold px-2 py-1">Déclarations fiscales</li>
                            <li><a href="/comptabilite/declaration-communication/"><i class="fas fa-file-invoice mr-2 text-error"></i>Déclaration Communication Impôts</a></li>
                            <li><a href="/comptabilite/natures-declaration/"><i class="fas fa-tags mr-2 text-warning"></i>Configuration Natures</a></li>
                        </ul>
                    </div>
                </li>
                

                <!-- Administration (si staff) -->
                
                <li>
                    <div class="dropdown dropdown-hover dropdown-end">
                        <div tabindex="0" role="button" class="btn btn-ghost btn-sm">
                            <i class="fas fa-cogs mr-1"></i>Référentiel<i class="fas fa-chevron-down ml-1 text-xs"></i>
                        </div>
                        <ul tabindex="0" class="dropdown-content menu bg-base-100 rounded-box z-[1] w-64 p-2 shadow border border-base-300">
                            <li class="menu-title text-xs text-primary font-semibold px-2 py-1">Interface Admin</li>
                            <li><a href="/admin/"><i class="fas fa-tools mr-2"></i>Interface Django</a></li>
                            <li><a href="/fichiers/"><i class="fas fa-folder-open mr-2"></i>Gestion Fichiers</a></li>
                            <li><hr class="my-1"></li>
                            <li class="menu-title text-xs text-info font-semibold px-2 py-1">Géographie</li>
                            <li>
                                <a href="/geography/" class="tooltip tooltip-right" data-tip="Régions, Districts, Communes, Fokontanys, Villages, Parcelles">
                                    <i class="fas fa-map-marker-alt mr-2 text-info"></i>Géographie
                                </a>
                            </li>
                            <li><a href="/geography/consolidated/"><i class="fas fa-table mr-2 text-success"></i>Géographie Consolidée</a></li>
                            <li><a href="/geography/capture-donnees/"><i class="fas fa-mobile-alt mr-2 text-warning"></i>Capture Données Terrain</a></li>
                            <li>
                                <a href="/organisations/" class="tooltip tooltip-right" data-tip="Organisations, Bases, Comptes, Postes, Magasins, Journaux, Employés">
                                    <i class="fas fa-building mr-2 text-primary"></i>Organisations
                                </a>
                            </li>
                            <li><a href="/facturation/fournisseurs/"><i class="fas fa-store mr-2 text-success"></i>Fournisseurs</a></li>
                            <li><hr class="my-1"></li>
                            <li class="menu-title text-xs text-info font-semibold px-2 py-1">Ouvrages</li>
                            <li>
                                <a href="/organisations/ouvrages/" class="tooltip tooltip-right" data-tip="Ouvrages, Points d'Eau, Équipements, Compteurs, Tarifs, Modalités, Adresses, Fournisseurs, Cartes Sociales">
                                    <i class="fas fa-tools mr-2 text-warning"></i>Ouvrages
                                </a>
                            </li>
                            <li><a href="/facturation/consolidated-points-eau/"><i class="fas fa-tint mr-2 text-info"></i>Points d'Eau Consolidés</a></li>
                            <li><a href="/consolidated-equipements/"><i class="fas fa-cogs mr-2 text-accent"></i>Équipements Consolidés</a></li>
                            <li><a href="/ouvrages/types/"><i class="fas fa-cogs mr-2 text-accent"></i>Types d'Ouvrages</a></li>
                            <li><a href="/organisations/types-equipements/"><i class="fas fa-tools mr-2 text-warning"></i>Types d'Équipements</a></li>
                            <li><a href="/facturation/types-points-eau/"><i class="fas fa-tint mr-2 text-secondary"></i>Types Points d'Eau</a></li>
                            <li><hr class="my-1"></li>
                            <li class="menu-title text-xs text-accent font-semibold px-2 py-1">Planning & Activités</li>
                            <li><a href="/plannings/crud/types-activites/table/"><i class="fas fa-tasks mr-2 text-primary"></i>Types d'Activités</a></li>
                            <li><a href="/plannings/crud/types-designations/table/"><i class="fas fa-tag mr-2 text-info"></i>Types de Désignations</a></li>
                            <li><a href="/plannings/deplacements/"><i class="fas fa-route mr-2 text-warning"></i>Déplacements</a></li>
                            <li><hr class="my-1"></li>
                            <li class="menu-title text-xs text-warning font-semibold px-2 py-1">Inspections & Contrôle</li>
                            <li><a href="/inspections/gestion-checklists/"><i class="fas fa-clipboard-check mr-2 text-warning"></i>Checklists & Activités Correctives</a></li>
                            <li><a href="/inspections/points-controle/table/"><i class="fas fa-bullseye mr-2 text-info"></i>Points de Contrôle (Tableau)</a></li>
                            <li><a href="/inspections/analyses-eau/"><i class="fas fa-flask mr-2 text-info"></i>Analyses d'eau</a></li>
                            <li><hr class="my-1"></li>
                            <li class="menu-title text-xs text-primary font-semibold px-2 py-1">Documentation</li>
                            <li><a href="/systeme/manuel/"><i class="fas fa-book text-info mr-2"></i>Manuel d'utilisateur</a></li>
                            <li><a href="/documentation/architecture/"><i class="fas fa-sitemap mr-2 text-primary"></i>Architecture & Workflows</a></li>
                        </ul>
                    </div>
                </li>
                


                
                <li>
                    <div class="dropdown dropdown-hover dropdown-end">
                        <div tabindex="0" role="button" class="btn btn-ghost btn-sm">
                            <i class="fas fa-cogs mr-1"></i>Administration<i class="fas fa-chevron-down ml-1 text-xs"></i>
                        </div>
                        <ul tabindex="0" class="dropdown-content menu bg-base-100 rounded-box z-[1] w-64 p-2 shadow border border-base-300">
                            <li class="menu-title text-xs text-success font-semibold px-2 py-1">Ressources Humaines</li>
                            <li><a href="/employes/list/"><i class="fas fa-users mr-2 text-primary"></i>Employés</a></li>
                            <li><a href="/gardiens/"><i class="fas fa-shield-alt mr-2 text-primary"></i>Gestion des Gardiens</a></li>
                            <li><a href="/positions-gps/"><i class="fas fa-map-marked-alt mr-2 text-info"></i>Positions GPS Employés</a></li>
                            <li><a href="/employes-cascade/"><i class="fas fa-database mr-2 text-info"></i>Employés & Bases DiameX</a></li>
                            <li><a href="/postes/"><i class="fas fa-briefcase mr-2 text-secondary"></i>Postes</a></li>
                            <li><a href="/contrats-travail/"><i class="fas fa-file-contract mr-2 text-warning"></i>Contrats Travail & Avenants</a></li>
                            <li><a href="/grilles-salaire/"><i class="fas fa-money-check-alt mr-2 text-success"></i>Grilles de Salaire</a></li>
                            <li><a href="/fiches-paie-mensuelles/"><i class="fas fa-file-invoice mr-2 text-primary"></i>Fiches de Paie Mensuelles</a></li>
                            <li><a href="/paiements-irsa/"><i class="fas fa-receipt mr-2 text-warning"></i>Paiements IRSA</a></li>
                            <li><a href="/paiements-cnaps-fmfp/"><i class="fas fa-file-invoice-dollar mr-2 text-info"></i>Paiements CNaPS/FMFP</a></li>
                            <li><a href="/paiements-mutuelle-sante/"><i class="fas fa-hospital mr-2 text-success"></i>Paiements Mutuelle Santé</a></li>
                            <li><a href="/paiements-iri/"><i class="fas fa-percentage mr-2 text-error"></i>Paiements IRI</a></li>
                            <li><hr class="my-1"></li>
                            <li class="menu-title text-xs text-info font-semibold px-2 py-1">Recrutement</li>
                            <li><a href="/recrutement/inscription/"><i class="fas fa-user-plus mr-2 text-success"></i>Test de recrutement</a></li>
                            <li><a href="/recrutement/gestion/candidats/"><i class="fas fa-user-tie mr-2 text-success"></i>Candidats préconfigurés</a></li>
                            <li><a href="/recrutement/gestion/questions/"><i class="fas fa-question-circle mr-2 text-info"></i>Questions de test</a></li>
                            <li><a href="/recrutement/gestion/resultats/"><i class="fas fa-clipboard-check mr-2 text-primary"></i>Résultats candidats</a></li>
                            <li><hr class="my-1"></li>
                            <li class="menu-title text-xs text-secondary font-semibold px-2 py-1">Configuration</li>
                            <li><a href="/config/salaire/"><i class="fas fa-money-bill-wave mr-2 text-success"></i>Configuration Salaires</a></li>
                            <li><a href="/config/tranches-irsa/"><i class="fas fa-calculator mr-2 text-warning"></i>Tranches IRSA</a></li>
                            <li><hr class="my-1"></li>
                            <li class="menu-title text-xs text-success font-semibold px-2 py-1">Budget & Prévisions</li>
                            <li><a href="/facturation/previsions/"><i class="fas fa-chart-line mr-2 text-success"></i>Prévisions budgétaires</a></li>
                            <li><hr class="my-1"></li>
                            <li class="menu-title text-xs text-base-content/70 font-semibold px-2 py-1">Système</li>
                            <li><a href="/systeme/users/"><i class="fas fa-users-cog mr-2"></i>Gestion utilisateurs</a></li>
                            <li><a href="/systeme/parameters/"><i class="fas fa-sliders-h mr-2"></i>Paramètres système</a></li>
                            <li><a href="/systeme/logs/"><i class="fas fa-file-alt mr-2"></i>Journaux & monitoring</a></li>
                        </ul>
                    </div>
                </li>
                
                
                
                
            </ul>
        </div>
        
        <div class="navbar-end">
            <div class="flex items-center gap-2">
                <!-- Présence utilisateurs temps réel -->
                <div id="user-presence-container" class="flex items-center gap-1 mx-2" style="display: none;">
                    <div id="user-presence-avatars" class="flex -space-x-2 overflow-hidden">
                        <!-- Avatars injectés par JS -->
                    </div>
                    <span id="user-presence-count" class="text-[10px] text-base-content/70 hidden xl:inline ml-1 font-medium italic leading-tight"></span>
                </div>

                <!-- Indicateur de statut en ligne/hors ligne -->
                <div class="flex items-center gap-2" title="Statut de connexion">
                    <div class="flex items-center gap-1">
                        <div id="online-indicator" class="w-2 h-2 bg-success rounded-full animate-pulse"></div>
                        <span id="online-status" class="text-xs text-success hidden sm:block">En ligne</span>
                    </div>
                </div>

                <!-- Calculatrice globale -->
                <button type="button" class="btn btn-ghost btn-sm" onclick="openCalculatorModal()"
                    title="Calculatrice">
                    <i class="fas fa-calculator text-success"></i>
                    <span class="hidden xl:inline">Calculatrice</span>
                </button>

                <!-- Bouton de changement de langue -->
                <div class="dropdown dropdown-end">
                    <div tabindex="0" role="button" class="btn btn-ghost btn-sm"
                        title="Changer de langue / Hanova teny">
                        <div class="flex items-center justify-center text-lg" id="current-language">
                            FR
                        </div>
                    </div>
                    <ul tabindex="0"
                        class="dropdown-content menu bg-base-100 rounded-box z-[1] mt-3 w-48 p-2 shadow border border-base-300">
                        <li><a onclick="changeLanguage('fr')"
                                class="flex items-center gap-3 cursor-pointer hover:bg-base-200">
                                <span class="text-lg">FR</span>
                                <span>Français</span>
                            </a></li>
                        <li><a onclick="changeLanguage('mg')"
                                class="flex items-center gap-3 cursor-pointer hover:bg-base-200">
                                <span class="text-lg">MG</span>
                                <span>Malagasy</span>
                            </a></li>
                    </ul>
                </div>

                <!-- Bouton de bascule de thème -->
                <label class="swap swap-rotate">
                    <input type="checkbox" class="theme-controller" id="theme-toggle" />
                    <!-- Icône soleil (thème clair) -->
                    <svg class="swap-off h-6 w-6 fill-current" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">
                        <path
                            d="M5.64,17l-.71.71a1,1,0,0,0,0,1.41,1,1,0,0,0,1.41,0l.71-.71A1,1,0,0,0,5.64,17ZM5,12a1,1,0,0,0-1-1H3a1,1,0,0,0,0,2H4A1,1,0,0,0,5,12Zm7-7a1,1,0,0,0,1-1V3a1,1,0,0,0-2,0V4A1,1,0,0,0,12,5ZM5.64,7.05a1,1,0,0,0,.7.29,1,1,0,0,0,.71-.29,1,1,0,0,0,0-1.41l-.71-.71A1,1,0,0,0,4.93,6.34Zm12,.29a1,1,0,0,0,.7-.29l.71-.71a1,1,0,1,0-1.41-1.41L17,5.64a1,1,0,0,0,0,1.41A1,1,0,0,0,17.66,7.34ZM21,11H20a1,1,0,0,0,0,2h1a1,1,0,0,0,0-2Zm-9,8a1,1,0,0,0-1,1v1a1,1,0,0,0,2,0V20A1,1,0,0,0,12,19ZM18.36,17A1,1,0,0,0,17,18.36l.71.71a1,1,0,0,0,1.41,0,1,1,0,0,0,0-1.41ZM12,6.5A5.5,5.5,0,1,0,17.5,12,5.51,5.51,0,0,0,12,6.5Zm0,9A3.5,3.5,0,1,1,15.5,12,3.5,3.5,0,0,1,12,15.5Z" />
                    </svg>
                    <!-- Icône lune (thème sombre) -->
                    <svg class="swap-on h-6 w-6 fill-current" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">
                        <path
                            d="M21.64,13a1,1,0,0,0-1.05-.14,8.05,8.05,0,0,1-3.37.73A8.15,8.15,0,0,1,9.08,5.49a8.59,8.59,0,0,1,.25-2A1,1,0,0,0,8,2.36,10.14,10.14,0,1,0,22,14.05,1,1,0,0,0,21.64,13Zm-9.5,6.69A8.14,8.14,0,0,1,7.08,5.22v.27A10.15,10.15,0,0,0,17.22,15.63a9.79,9.79,0,0,0,2.1-.22A8.11,8.11,0,0,1,12.14,19.73Z" />
                    </svg>
                </label>

                
                <div class="dropdown dropdown-end">
                    <div tabindex="0" role="button" class="btn btn-ghost btn-circle avatar relative">
                        <div
                            class="w-8 h-8 rounded-full bg-accent text-accent-content flex items-center justify-center text-sm font-medium">
                            H
                        </div>
                        <!-- Badge indicateur de rôle -->
                        
                        <div class="absolute -top-1 -right-1 w-4 h-4 bg-success rounded-full border-2 border-base-100"
                            title="Administrateur"></div>
                        
                    </div>
                    <ul tabindex="0"
                        class="menu menu-sm dropdown-content bg-base-100 rounded-box z-[1] mt-3 w-80 p-2 shadow border border-base-300">
                        <!-- Informations utilisateur -->
                        <li class="menu-title px-4 py-2">
                            <div class="flex flex-col">
                                <span class="font-bold text-base">Herizo</span>
                                
                                <span class="text-xs text-base-content/70">Directeur</span>
                                
                            </div>
                        </li>
                        <li>
                            <hr class="my-1">
                        </li>

                        <!-- Informations de cloisonnement -->
                        
                        <li class="menu-title px-4 py-2">
                            <div class="flex flex-col gap-1">
                                <span class="text-xs font-semibold text-info">Accès aux données</span>
                                
                                <div class="badge badge-success badge-sm gap-1">
                                    <i class="fas fa-crown text-xs"></i>
                                    Accès complet (Admin)
                                </div>
                                <span class="text-xs text-base-content/60">Tous les ouvrages</span>
                                
                            </div>
                        </li>
                        <li>
                            <hr class="my-1">
                        </li>
                        

                        <!-- Menu actions -->
                        <li>
                            <a href="/systeme/password-change/">
                                <i class="fas fa-key mr-2 text-primary"></i> Changer de mot de passe
                            </a>
                        </li>
                        <li>
                            <hr class="my-1">
                        </li>
                        <li>
                            <form method="post" action="/accounts/logout/" style="margin: 0;">
                                <input type="hidden" name="csrfmiddlewaretoken" value="GwWUOhG9urfuOHQr9drubGglC46op3Ro6DTuTDQgpsUz9puTXg8Cwtccmk6Byq7P">
                                <button type="submit"
                                    class="w-full text-left p-0 bg-transparent border-none cursor-pointer">
                                    Déconnexion</button>
                            </form>
                        </li>
                    </ul>
                </div>
                
            </div>
        </div>
    </nav>

    <!-- Messages -->
    

    <!-- Breadcrumb -->
    

    <!-- Contenu principal -->
    <main class="container mx-auto px-4 py-6">
        
<div class="planning-agenda-shell max-w-5xl mx-auto px-3 sm:px-4 py-4 pb-28">
    <section class="agenda-hero rounded-[1.75rem] p-5 sm:p-6">
        <div class="relative z-[1] flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
            <div class="max-w-2xl">
                <div class="text-xs font-semibold uppercase tracking-[0.3em] text-base-content/60">Planning</div>
                <h1 class="mt-2 text-3xl font-semibold text-base-content">Agenda mobile</h1>
                <p class="mt-3 text-sm text-base-content/70">
                    Une vue agenda plus proche d'un calendrier mobile: calendrier repliable en haut,
                    liste des rendez-vous en dessous, navigation rapide par date et ajout direct.
                </p>
            </div>
            <div class="relative z-[1] flex flex-wrap gap-2">
                <a href="/plannings/" class="btn btn-ghost btn-sm">
                    <i class="fas fa-table-columns mr-2"></i>Vue classique
                </a>
                <a href="/plannings/calendrier/" class="btn btn-ghost btn-sm">
                    <i class="fas fa-calendar-days mr-2"></i>Vue grille
                </a>
                <a href="/plannings/form/nouveau/" id="header-add-link" class="btn btn-primary btn-sm">
                    <i class="fas fa-plus mr-2"></i>Ajouter un rendez-vous
                </a>
            </div>
        </div>
    </section>

    <section id="agenda-calendar-shell" class="agenda-sticky-shell mt-5">
        <div class="agenda-calendar-card rounded-[1.5rem] p-4 sm:p-5">
            <div class="flex flex-col gap-4">
                <div class="flex flex-col gap-3 xl:flex-row xl:items-end xl:justify-between">
                    <div class="flex flex-wrap items-center gap-2">
                        <button type="button" class="btn btn-ghost btn-sm" onclick="navigateMonth(-1)">
                            <i class="fas fa-chevron-left"></i>
                        </button>
                        <button type="button" class="btn btn-ghost btn-sm" onclick="goToToday()">Aujourd'hui</button>
                        <button type="button" class="btn btn-ghost btn-sm" onclick="navigateMonth(1)">
                            <i class="fas fa-chevron-right"></i>
                        </button>
                        <div class="ml-1">
                            <div id="current-range-label" class="text-lg font-semibold text-base-content"></div>
                            <div id="selected-date-label" class="text-sm text-base-content/65"></div>
                        </div>
                    </div>

                    <div class="grid grid-cols-1 gap-3 sm:grid-cols-3">
                        <label class="form-control">
                            <span class="label pb-1">
                                <span class="label-text text-xs uppercase tracking-[0.2em] text-base-content/50">Mois</span>
                            </span>
                            <input id="month-picker" type="month" class="input input-bordered input-sm">
                        </label>

                        <label class="form-control">
                            <span class="label pb-1">
                                <span class="label-text text-xs uppercase tracking-[0.2em] text-base-content/50">Employe</span>
                            </span>
                            <select id="filter-employe" class="select select-bordered select-sm" disabled>
                                <option value="">Chargement des employes...</option>
                            </select>
                            <span id="filter-employe-status" class="mt-1 text-xs text-base-content/55"></span>
                        </label>

                        <label class="form-control">
                            <span class="label pb-1">
                                <span class="label-text text-xs uppercase tracking-[0.2em] text-base-content/50">Validation</span>
                            </span>
                            <select id="filter-validation" class="select select-bordered select-sm">
                                <option value="">Tout afficher</option>
                                <option value="true">Valides</option>
                                <option value="false">En attente</option>
                            </select>
                        </label>
                    </div>
                </div>

                <div class="flex flex-wrap items-center justify-between gap-3">
                    <div class="join">
                        <button id="mode-week" type="button" class="btn join-item btn-sm" onclick="setCalendarMode('week')">
                            <i class="fas fa-calendar-week mr-2"></i>Semaine
                        </button>
                        <button id="mode-month" type="button" class="btn join-item btn-sm" onclick="setCalendarMode('month')">
                            <i class="fas fa-calendar mr-2"></i>Mois
                        </button>
                    </div>
                    <div id="selected-count-badge" class="agenda-summary-chip badge badge-lg">0 rendez-vous</div>
                </div>

                <div>
                    <div class="agenda-weekdays mb-3">
                        <div class="agenda-weekday">Lun</div>
                        <div class="agenda-weekday">Mar</div>
                        <div class="agenda-weekday">Mer</div>
                        <div class="agenda-weekday">Jeu</div>
                        <div class="agenda-weekday">Ven</div>
                        <div class="agenda-weekday">Sam</div>
                        <div class="agenda-weekday">Dim</div>
                    </div>
                    <div id="calendar-grid" class="agenda-calendar-grid"></div>
                </div>
            </div>
        </div>
    </section>

    <section class="mt-6">
        <div class="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between mb-4">
            <div>
                <h2 class="text-xl font-semibold text-base-content">Agenda du mois</h2>
                <p id="agenda-summary-text" class="text-sm text-base-content/65"></p>
            </div>
            <button type="button" class="btn btn-ghost btn-sm" onclick="scrollToSection(agendaState.selectedDate, 'smooth')">
                <i class="fas fa-location-arrow mr-2"></i>Aller a la date selectionnee
            </button>
        </div>

        <div id="agenda-loading" class="card border border-base-300 bg-base-100 shadow-sm">
            <div class="card-body flex-row items-center gap-3 text-base-content/70">
                <span class="loading loading-spinner loading-md"></span>
                Chargement de l'agenda...
            </div>
        </div>

        <div id="agenda-empty-state" class="hidden card border border-base-300 bg-base-100 shadow-sm">
            <div class="card-body gap-3 text-base-content/70">
                <div class="flex items-center gap-3">
                    <div class="btn btn-circle btn-ghost pointer-events-none">
                        <i class="fas fa-calendar-xmark"></i>
                    </div>
                    <div>
                        <h3 id="agenda-empty-title" class="text-base font-semibold text-base-content">Aucun rendez-vous trouve</h3>
                        <p id="agenda-empty-text" class="text-sm text-base-content/65">Essayez un autre mois ou un autre employe.</p>
                    </div>
                </div>
                <div class="flex flex-wrap gap-2">
                    <button type="button" class="btn btn-sm btn-ghost" onclick="goToToday()">Revenir a aujourd'hui</button>
                    <button type="button" class="btn btn-sm btn-outline" onclick="clearEmployeFilter()">Tous les employes</button>
                </div>
            </div>
        </div>

        <div id="agenda-list" class="hidden space-y-4"></div>
    </section>

    <a href="/plannings/form/nouveau/" id="fab-add-link" class="agenda-fab btn btn-primary btn-circle btn-lg" aria-label="Ajouter un rendez-vous">
        <i class="fas fa-plus"></i>
    </a>
</div>

<div id="agenda-toast" class="agenda-toast alert alert-info shadow-lg w-[min(92vw,26rem)] hidden"></div>

    </main>

    <!-- Footer -->
    <footer class="footer footer-center bg-base-200 text-base-content p-4 mt-auto">
        <div>
            <p>Copyright © 2026 - Hydria - Gestion des activités</p>
        </div>
    </footer>

    <!-- Bouton flottant Assistant IA - DEPLACE A LA FIN DU BODY -->
    <div class="relative">
        <!-- Badge de notification (optionnel) -->
        <div id="notification-badge"
            class="absolute -top-2 -right-2 w-5 h-5 bg-error text-error-content text-xs rounded-full flex items-center justify-center font-bold hidden">
            1
        </div>

        <!-- Bouton principal -->
        <button class="btn btn-circle btn-primary btn-lg shadow-lg hover:shadow-xl transition-all duration-300 group"
            onclick="toggleFloatingChat()">
            <svg id="chat-icon" class="w-6 h-6 group-hover:scale-110 transition-transform" fill="none"
                stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                    d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z">
                </path>
            </svg>
            <svg id="close-icon" class="w-6 h-6 group-hover:scale-110 transition-transform hidden" fill="none"
                stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path>
            </svg>
        </button>
    </div>
    </div>

    <!-- CHATBOT DEPLACE A LA FIN DU FICHIER -->

    <!-- Styles pour la navbar et les dropdown -->
    <style>
        /* Amélioration des dropdown menus */
        .dropdown-hover:hover .dropdown-content {
            display: block;
        }

        .dropdown-content {
            animation: fadeIn 0.2s ease-in-out;
        }

        @keyframes fadeIn {
            from {
                opacity: 0;
                transform: translateY(-10px);
            }

            to {
                opacity: 1;
                transform: translateY(0);
            }
        }

        /* Amélioration du hover sur les boutons de menu */
        .navbar .btn-ghost:hover {
            background-color: hsl(var(--b3) / 0.2);
            transform: translateY(-1px);
            transition: all 0.2s ease-in-out;
        }

        /* Styles pour les icônes dans les menus */
        .menu li>a>i {
            width: 1.2rem;
            text-align: center;
        }

        /* Responsive : cache les textes sur très petits écrans */
        @media (max-width: 1200px) {
            .navbar .btn-ghost span:not(.fas) {
                display: none;
            }

            .navbar .btn-ghost {
                padding: 0.5rem;
            }
        }

        /* Amélioration du z-index et positionnement pour les dropdown */
        .dropdown-content {
            z-index: 50;
        }

        /* Force les dropdowns à s'afficher correctement */
        .dropdown.dropdown-end .dropdown-content {
            position: absolute;
            top: 100% !important;
            margin-top: -8px;
            /* Écart très réduit pour un accès facile */
            right: 0;
            min-width: max-content;
        }

        /* Amélioration du hover pour maintenir le focus */
        .dropdown:hover .dropdown-content,
        .dropdown.dropdown-open .dropdown-content {
            display: block;
        }

        /* Zone de tolérance invisible pour faciliter l'accès aux dropdowns */
        .dropdown-hover {
            position: relative;
        }

        .dropdown-hover::after {
            content: '';
            position: absolute;
            top: 0;
            left: -8px;
            right: -8px;
            bottom: -8px;
            /* Zone étendue dans toutes les directions */
            background: transparent;
            z-index: 5;
            pointer-events: none;
        }

        /* Délai de fermeture et transitions fluides pour les dropdowns hover */
        .dropdown-hover .dropdown-content {
            transition: opacity 0.15s ease-in-out, transform 0.15s ease-in-out;
            opacity: 0;
            transform: translateY(-8px);
            pointer-events: none;
        }

        .dropdown-hover:hover .dropdown-content {
            opacity: 1;
            transform: translateY(0);
            pointer-events: auto;
            transition-delay: 0ms;
        }

        /* Zone de connexion continue pour éviter la fermeture */
        .dropdown-hover:hover::before {
            content: '';
            position: absolute;
            top: 100%;
            left: 0;
            right: 0;
            height: 12px;
            /* Pont invisible entre bouton et menu */
            background: transparent;
            z-index: 15;
        }

        /* Zone d'expansion pour capturer le hover entre le bouton et le menu */
        .dropdown-hover .dropdown-content::before {
            content: '';
            position: absolute;
            top: -12px;
            /* Zone encore plus large pour capturer le hover */
            left: -4px;
            right: -4px;
            height: 16px;
            /* Zone de connexion élargie */
            background: transparent;
            z-index: 1;
        }

        /* Navbar desktop principale: éviter que l'ancien menu reste ouvert */
        .desktop-main-menu .dropdown-hover::after,
        .desktop-main-menu .dropdown-hover:hover::before,
        .desktop-main-menu .dropdown-hover .dropdown-content::before {
            content: none !important;
            display: none !important;
        }

        /* Styles pour le rendu markdown dans les messages du chatbot */
        .chat-bubble table {
            border-collapse: collapse;
            width: 100%;
            margin: 1rem 0;
            font-size: 0.875rem;
        }

        .chat-bubble table th {
            background-color: hsl(var(--b3));
            font-weight: 600;
            text-align: left;
            padding: 0.75rem;
            border: 1px solid hsl(var(--bc) / 0.2);
        }

        .chat-bubble table td {
            padding: 0.75rem;
            border: 1px solid hsl(var(--bc) / 0.2);
        }

        .chat-bubble table tr:nth-child(even) {
            background-color: hsl(var(--bc) / 0.05);
        }

        .chat-bubble h1,
        .chat-bubble h2,
        .chat-bubble h3 {
            font-weight: bold;
            margin-top: 1rem;
            margin-bottom: 0.5rem;
        }

        .chat-bubble h1 {
            font-size: 1.5rem;
        }

        .chat-bubble h2 {
            font-size: 1.25rem;
        }

        .chat-bubble h3 {
            font-size: 1.1rem;
        }

        .chat-bubble ul,
        .chat-bubble ol {
            list-style-position: inside;
            margin: 0.5rem 0;
            padding-left: 1rem;
        }

        .chat-bubble ul {
            list-style-type: disc;
        }

        .chat-bubble ol {
            list-style-type: decimal;
        }

        .chat-bubble code {
            background-color: hsl(var(--bc) / 0.1);
            padding: 0.2rem 0.4rem;
            border-radius: 0.25rem;
            font-size: 0.9em;
            font-family: monospace;
        }

        .chat-bubble pre {
            background-color: hsl(var(--bc) / 0.05);
            border: 1px solid hsl(var(--bc) / 0.2);
            border-radius: 0.5rem;
            padding: 0.75rem;
            margin: 0.5rem 0;
            overflow-x: auto;
        }

        .chat-bubble pre code {
            background-color: transparent;
            padding: 0;
        }

        .chat-bubble blockquote {
            border-left: 4px solid hsl(var(--p));
            padding-left: 1rem;
            font-style: italic;
            margin: 0.5rem 0;
        }

        .chat-bubble strong {
            font-weight: bold;
        }

        .chat-bubble em {
            font-style: italic;
        }

        .chat-bubble a {
            color: hsl(var(--p));
            text-decoration: underline;
        }

        .chat-bubble a:hover {
            color: hsl(var(--pf));
        }

        /* Styles pour le chat flottant */
        #floating-chat-window {
            backdrop-filter: blur(10px);
            box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.25);
        }

        #floating-chat-window.scale-100 {
            transform: scale(1) !important;
        }

        #floating-messages {
            scrollbar-width: thin;
            scrollbar-color: hsl(var(--bc) / 0.2) transparent;
        }

        #floating-messages::-webkit-scrollbar {
            width: 6px;
        }

        #floating-messages::-webkit-scrollbar-track {
            background: transparent;
        }

        #floating-messages::-webkit-scrollbar-thumb {
            background-color: hsl(var(--bc) / 0.2);
            border-radius: 3px;
        }

        /* Animation pour les messages */
        .chat {
            animation: slideInMessage 0.3s ease-out;
        }

        @keyframes slideInMessage {
            from {
                opacity: 0;
                transform: translateY(10px);
            }

            to {
                opacity: 1;
                transform: translateY(0);
            }
        }

        /* Responsive pour le chat flottant */
        @media (max-width: 768px) {
            #floating-chat-window {
                width: calc(100vw - 2rem) !important;
                right: 1rem !important;
                left: 1rem !important;
            }

            #floating-quick-actions {
                right: 1rem !important;
            }

            #floating-chat-btn {
                bottom: 1rem !important;
                right: 1rem !important;
            }
        }

        /* Animation du bouton flottant */
        #floating-chat-btn button {
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        }

        #floating-chat-btn button:hover {
            transform: translateY(-2px) scale(1.05);
        }

        /* Actions rapides avec animation */
        #floating-quick-actions button {
            animation: slideInFromRight 0.3s ease-out;
            animation-fill-mode: both;
        }

        #floating-quick-actions button:nth-child(1) {
            animation-delay: 0.1s;
        }

        #floating-quick-actions button:nth-child(2) {
            animation-delay: 0.2s;
        }

        #floating-quick-actions button:nth-child(3) {
            animation-delay: 0.3s;
        }

        #floating-quick-actions button:nth-child(4) {
            animation-delay: 0.4s;
        }

        @keyframes slideInFromRight {
            from {
                opacity: 0;
                transform: translateX(20px);
            }

            to {
                opacity: 1;
                transform: translateX(0);
            }
        }
    </style>

    <style>
        /* Calculatrice globale */
        .hydria-calculator-scroll {
            max-height: 52vh;
            overflow: auto;
        }

        .hydria-calculator-table thead th {
            position: sticky;
            top: 0;
            background: hsl(var(--b2));
            z-index: 1;
        }

        .hydria-calculator-row-active {
            background: hsl(var(--p) / 0.08);
        }

        .hydria-calculator-result {
            font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
            white-space: nowrap;
        }
    </style>


    
<script>
const MONTH_NAMES = ['Janvier', 'Fevrier', 'Mars', 'Avril', 'Mai', 'Juin', 'Juillet', 'Aout', 'Septembre', 'Octobre', 'Novembre', 'Decembre'];
const MONTH_SHORT = ['Jan', 'Fev', 'Mar', 'Avr', 'Mai', 'Juin', 'Juil', 'Aou', 'Sep', 'Oct', 'Nov', 'Dec'];
const WEEKDAY_NAMES = ['Lundi', 'Mardi', 'Mercredi', 'Jeudi', 'Vendredi', 'Samedi', 'Dimanche'];
const TODAY_KEY = toDateKey(new Date());

const agendaState = {
    currentMonth: startOfMonth(new Date()),
    selectedDate: TODAY_KEY,
    calendarMode: window.innerWidth < 768 ? 'week' : 'month',
    plannings: [],
    eventsByDate: new Map(),
    detailsCache: new Map(),
    observer: null,
    loading: false,
    ignoreObserverUntil: 0,
    defaultEmployeId: '',
    isDirector: true
};

document.addEventListener('DOMContentLoaded', async () => {
    try {
        bindAgendaControls();
        syncMonthPicker();
        setCalendarMode(agendaState.calendarMode, false);
        await loadEmployes();

        if (agendaState.defaultEmployeId) {
            document.getElementById('filter-employe').value = agendaState.defaultEmployeId;
        }

        await loadAgendaMonth();
    } catch (error) {
        console.error('Initialisation de l agenda impossible', error);
        setLoading(false);
        renderEmptyState('Initialisation impossible', 'La page n a pas pu charger ses donnees. Rechargez la page.');
        showToast('Impossible d initialiser la page agenda.', 'error');
    }
});

function bindAgendaControls() {
    document.getElementById('month-picker').addEventListener('change', handleMonthPickerChange);
    document.getElementById('filter-employe').addEventListener('change', async () => {
        agendaState.detailsCache.clear();
        await loadAgendaMonth();
    });
    document.getElementById('filter-validation').addEventListener('change', async () => {
        agendaState.detailsCache.clear();
        await loadAgendaMonth();
    });
}

function getEmployeSelect() {
    return document.getElementById('filter-employe');
}

function setEmployeStatus(message = '') {
    const status = document.getElementById('filter-employe-status');
    if (status) {
        status.textContent = message;
    }
}

function resetEmployeSelect(message) {
    const select = getEmployeSelect();
    select.innerHTML = `<option value="">${escapeHtml(message)}</option>`;
    select.disabled = true;
}

function startOfMonth(date) {
    return new Date(date.getFullYear(), date.getMonth(), 1, 12, 0, 0, 0);
}

function parseDateKey(value) {
    const [year, month, day] = value.split('-').map(Number);
    return new Date(year, month - 1, day, 12, 0, 0, 0);
}

function toDateKey(date) {
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
}

function monthKey(date) {
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    return `${year}-${month}`;
}

function clampDateToMonth(date, monthDate) {
    const maxDay = new Date(monthDate.getFullYear(), monthDate.getMonth() + 1, 0).getDate();
    return new Date(monthDate.getFullYear(), monthDate.getMonth(), Math.min(date.getDate(), maxDay), 12, 0, 0, 0);
}

function isSameMonth(date, monthDate) {
    return date.getFullYear() === monthDate.getFullYear() && date.getMonth() === monthDate.getMonth();
}

function buildMonthGridDates() {
    const firstDay = new Date(agendaState.currentMonth.getFullYear(), agendaState.currentMonth.getMonth(), 1, 12);
    const offset = (firstDay.getDay() + 6) % 7;
    const start = new Date(firstDay);
    start.setDate(firstDay.getDate() - offset);

    return Array.from({ length: 42 }, (_, index) => {
        const date = new Date(start);
        date.setDate(start.getDate() + index);
        return date;
    });
}

function buildWeekDates() {
    const selected = parseDateKey(agendaState.selectedDate);
    const mondayOffset = (selected.getDay() + 6) % 7;
    const start = new Date(selected);
    start.setDate(selected.getDate() - mondayOffset);

    return Array.from({ length: 7 }, (_, index) => {
        const date = new Date(start);
        date.setDate(start.getDate() + index);
        return date;
    });
}

function buildCurrentMonthDates() {
    const lastDay = new Date(agendaState.currentMonth.getFullYear(), agendaState.currentMonth.getMonth() + 1, 0).getDate();

    return Array.from({ length: lastDay }, (_, index) => {
        return new Date(agendaState.currentMonth.getFullYear(), agendaState.currentMonth.getMonth(), index + 1, 12);
    });
}

function formatSelectedDate(dateKey) {
    const date = parseDateKey(dateKey);
    const weekday = WEEKDAY_NAMES[(date.getDay() + 6) % 7];
    return `${weekday} ${date.getDate()} ${MONTH_NAMES[date.getMonth()]} ${date.getFullYear()}`;
}

function formatSectionDate(dateKey) {
    const date = parseDateKey(dateKey);
    const weekday = WEEKDAY_NAMES[(date.getDay() + 6) % 7];
    return {
        weekday,
        headline: `${date.getDate()} ${MONTH_NAMES[date.getMonth()]} ${date.getFullYear()}`
    };
}

function formatStatutLabel(value) {
    if (!value) {
        return 'En cours';
    }
    return String(value)
        .replace(/_/g, ' ')
        .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function formatCount(value, noun) {
    const plural = noun.endsWith('s') || noun.endsWith('x') ? noun : `${noun}s`;
    return `${value} ${value === 1 ? noun : plural}`;
}

function formatAmount(value) {
    return new Intl.NumberFormat('fr-FR', {
        minimumFractionDigits: 0,
        maximumFractionDigits: 2
    }).format(Number(value || 0));
}

function escapeHtml(value) {
    return String(value ?? '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

async function fetchJson(url) {
    const response = await fetch(url, {
        headers: {
            'X-Requested-With': 'XMLHttpRequest'
        }
    });
    const rawBody = await response.text();

    if (!response.ok) {
        throw new Error(`HTTP ${response.status} ${rawBody.slice(0, 120)}`);
    }

    try {
        return JSON.parse(rawBody);
    } catch (error) {
        throw new Error(`Reponse JSON invalide: ${rawBody.slice(0, 120)}`);
    }
}

function getEventsForDate(dateKey) {
    return agendaState.eventsByDate.get(dateKey) || [];
}

function sortEvents(events) {
    return [...events].sort((left, right) => {
        if (left.validation !== right.validation) {
            return Number(left.validation) - Number(right.validation);
        }

        const leftName = (left.employe_surnom || left.employe_nom || '').toLowerCase();
        const rightName = (right.employe_surnom || right.employe_nom || '').toLowerCase();
        return leftName.localeCompare(rightName);
    });
}

async function loadEmployes() {
    const select = getEmployeSelect();
    resetEmployeSelect('Chargement des employes...');
    setEmployeStatus('');

    const endpoints = [
        '/plannings/api/employees/',
        '/plannings/api/employes/'
    ];

    try {
        let employes = null;

        for (const endpoint of endpoints) {
            try {
                const payload = await fetchJson(endpoint);
                if (Array.isArray(payload)) {
                    employes = payload;
                    break;
                }
            } catch (error) {
                console.warn(`Chargement employes echoue via ${endpoint}`, error);
            }
        }

        if (!Array.isArray(employes)) {
            throw new Error('Aucune reponse employees exploitable');
        }

        const defaultOption = '<option value="">Tous les employes</option>';
        select.innerHTML = defaultOption + employes.map((employe) => {
            return `<option value="${escapeHtml(employe.id)}">${escapeHtml(employe.display_name)}</option>`;
        }).join('');
        select.disabled = false;

        if (!employes.length) {
            setEmployeStatus('Aucun employe disponible dans votre perimetre.');
        } else if (employes.length === 1) {
            setEmployeStatus('1 employe disponible dans votre perimetre.');
        } else {
            setEmployeStatus(`${employes.length} employes disponibles.`);
        }
    } catch (error) {
        console.error('Impossible de charger les employes', error);
        resetEmployeSelect('Aucun employe disponible');
        setEmployeStatus('La liste des employes n a pas pu etre chargee.');
        showToast('Impossible de charger la liste des employes.', 'warning');
    }
}

async function loadAgendaMonth(options = {}) {
    setLoading(true);

    const params = new URLSearchParams({
        mois: monthKey(agendaState.currentMonth)
    });

    const employeId = document.getElementById('filter-employe').value;
    const validation = document.getElementById('filter-validation').value;

    if (employeId) {
        params.set('employe', employeId);
    }
    if (validation) {
        params.set('validation', validation);
    }

    try {
        const data = await fetchJson(`/plannings/api/data/?${params.toString()}`);
        agendaState.plannings = Array.isArray(data) ? data : [];
        agendaState.eventsByDate = new Map();

        agendaState.plannings.forEach((planning) => {
            const key = planning.date_planning;
            if (!agendaState.eventsByDate.has(key)) {
                agendaState.eventsByDate.set(key, []);
            }
            agendaState.eventsByDate.get(key).push(planning);
        });

        if (!isSameMonth(parseDateKey(agendaState.selectedDate), agendaState.currentMonth)) {
            agendaState.selectedDate = toDateKey(clampDateToMonth(parseDateKey(TODAY_KEY), agendaState.currentMonth));
        }

        renderCalendar();
        renderAgenda();
        updateSelectedUi(false);

        if (options.scrollToSelected) {
            scrollToSection(agendaState.selectedDate, options.behavior || 'smooth');
        }
    } catch (error) {
        console.error('Impossible de charger les plannings', error);
        agendaState.plannings = [];
        agendaState.eventsByDate = new Map();
        renderCalendar();
        renderAgenda();
        updateSelectedUi(false);
        showToast('Erreur lors du chargement des plannings.', 'error');
    } finally {
        setLoading(false);
    }
}

function renderCalendar() {
    const grid = document.getElementById('calendar-grid');
    const dates = agendaState.calendarMode === 'month' ? buildMonthGridDates() : buildWeekDates();

    grid.innerHTML = dates.map((date) => renderCalendarDay(date)).join('');
    document.getElementById('current-range-label').textContent = `${MONTH_NAMES[agendaState.currentMonth.getMonth()]} ${agendaState.currentMonth.getFullYear()}`;
}

function renderCalendarDay(date) {
    const dateKey = toDateKey(date);
    const events = getEventsForDate(dateKey);
    const isSelected = agendaState.selectedDate === dateKey;
    const isToday = TODAY_KEY === dateKey;
    const isOutside = !isSameMonth(date, agendaState.currentMonth);
    const modeClass = agendaState.calendarMode === 'week' ? 'week-mode' : '';
    const meta = isOutside ? MONTH_SHORT[date.getMonth()] : '&nbsp;';

    return `
        <button
            type="button"
            class="agenda-day-button ${modeClass} ${isSelected ? 'is-selected' : ''} ${isToday ? 'is-today' : ''} ${isOutside ? 'is-outside' : ''}"
            onclick="handleCalendarDayClick('${dateKey}')"
        >
            <div class="agenda-day-top">
                <span class="agenda-day-number">${date.getDate()}</span>
                ${events.length ? `<span class="agenda-day-count">${events.length}</span>` : ''}
            </div>
            <div class="agenda-day-meta">${meta}</div>
        </button>
    `;
}

function renderAgenda() {
    const list = document.getElementById('agenda-list');
    hideEmptyState();

    if (!agendaState.plannings.length) {
        list.innerHTML = '';
        list.classList.add('hidden');
        disconnectAgendaObserver();
        renderEmptyState(
            'Aucun rendez-vous trouve',
            `Aucun rendez-vous ne correspond aux filtres sur ${MONTH_NAMES[agendaState.currentMonth.getMonth()]} ${agendaState.currentMonth.getFullYear()}.`
        );
        return;
    }

    const monthDates = buildCurrentMonthDates();

    list.innerHTML = monthDates.map((date) => {
        const dateKey = toDateKey(date);
        const sectionDate = formatSectionDate(dateKey);
        const events = sortEvents(getEventsForDate(dateKey));
        const summaryLabel = events.length ? formatCount(events.length, 'rendez-vous') : 'Aucun rendez-vous';

        return `
            <section class="agenda-day-section card shadow-sm ${dateKey === agendaState.selectedDate ? 'is-active' : ''}" data-date-section="${dateKey}">
                <div class="card-body p-4 sm:p-5">
                    <div class="agenda-day-section-header">
                        <div>
                            <div class="text-xs font-semibold uppercase tracking-[0.28em] text-base-content/50">${escapeHtml(sectionDate.weekday)}</div>
                            <h3 class="mt-1 text-xl font-semibold text-base-content">${escapeHtml(sectionDate.headline)}</h3>
                        </div>
                        <button type="button" class="badge badge-outline badge-lg" onclick="handleCalendarDayClick('${dateKey}')">${escapeHtml(summaryLabel)}</button>
                    </div>

                    <div class="mt-4 space-y-3">
                        ${events.length ? events.map((planning) => renderEventCard(planning)).join('') : `
                            <div class="agenda-day-empty">
                                <i class="fas fa-calendar-day text-base-content/40"></i>
                                <span>Aucun rendez-vous programme pour cette date.</span>
                            </div>
                        `}
                    </div>
                </div>
            </section>
        `;
    }).join('');

    list.classList.remove('hidden');
    attachAgendaObserver();
}

function renderEventCard(planning) {
    const isValidated = Boolean(planning.validation);
    const employeeName = planning.employe_surnom || planning.employe_nom || 'Employe non defini';
    const ouvrageName = planning.ouvrage_nom || 'Sans ouvrage';
    const badges = [];

    badges.push(`<span class="badge ${isValidated ? 'badge-success' : 'badge-warning'}">${isValidated ? 'Valide' : 'En attente'}</span>`);
    badges.push(`<span class="badge badge-outline">${escapeHtml(formatStatutLabel(planning.statut))}</span>`);

    if (planning.type_activite_nom) {
        badges.push(`<span class="badge badge-ghost">${escapeHtml(planning.type_activite_nom)}</span>`);
    }
    if (planning.preuve_manquante) {
        badges.push('<span class="badge badge-error">Preuve manquante</span>');
    }
    if (planning.nb_details) {
        badges.push(`<span class="badge badge-warning badge-outline">${escapeHtml(formatCount(planning.nb_details, 'avance'))}</span>`);
    }
    if (planning.nb_livraisons) {
        badges.push(`<span class="badge badge-info badge-outline">${escapeHtml(formatCount(planning.nb_livraisons, 'livraison'))}</span>`);
    }
    if (planning.nb_paiements) {
        badges.push(`<span class="badge badge-secondary badge-outline">${escapeHtml(formatCount(planning.nb_paiements, 'paiement'))}</span>`);
    }

    return `
        <article class="agenda-event-card ${isValidated ? 'validated' : 'pending'}">
            <div class="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
                <div class="min-w-0 flex-1">
                    <div class="flex flex-wrap gap-2">${badges.join('')}</div>
                    <h4 class="mt-3 text-lg font-semibold text-base-content">${escapeHtml(planning.activite_display || planning.activite_nom || 'Activite')}</h4>
                    <div class="mt-2 flex flex-wrap gap-x-4 gap-y-2 text-sm text-base-content/70">
                        <span><i class="fas fa-user mr-2 text-base-content/40"></i>${escapeHtml(employeeName)}</span>
                        <span><i class="fas fa-location-dot mr-2 text-base-content/40"></i>${escapeHtml(ouvrageName)}</span>
                        ${planning.commune_name ? `<span><i class="fas fa-map mr-2 text-base-content/40"></i>${escapeHtml(planning.commune_name)}</span>` : ''}
                    </div>
                    ${planning.participants ? `
                        <div class="mt-2 text-sm text-base-content/65">
                            <i class="fas fa-users mr-2 text-base-content/40"></i>${escapeHtml(planning.participants)}
                        </div>
                    ` : ''}
                    ${planning.remarques ? `
                        <p class="mt-3 text-sm leading-6 text-base-content/75">${escapeHtml(planning.remarques)}</p>
                    ` : ''}
                </div>

                <div class="flex flex-wrap gap-2 xl:w-auto">
                    <a href="/plannings/form/${planning.id}/modifier/" class="btn btn-ghost btn-sm">
                        <i class="fas fa-pen mr-2"></i>Modifier
                    </a>
                    <button type="button" class="btn btn-outline btn-sm" onclick="togglePlanningDetails('${planning.id}')">
                        <i class="fas fa-layer-group mr-2"></i>Details
                    </button>
                </div>
            </div>

            <div id="planning-details-${planning.id}" class="agenda-detail-shell hidden"></div>
        </article>
    `;
}

function updateSelectedUi(renderCalendarToo = true) {
    const selectedDateLabel = document.getElementById('selected-date-label');
    const selectedCountBadge = document.getElementById('selected-count-badge');
    const summary = document.getElementById('agenda-summary-text');
    const selectedEvents = getEventsForDate(agendaState.selectedDate);

    selectedDateLabel.textContent = formatSelectedDate(agendaState.selectedDate);
    selectedCountBadge.textContent = formatCount(selectedEvents.length, 'rendez-vous');
    summary.textContent = agendaState.plannings.length
        ? `${formatCount(agendaState.plannings.length, 'rendez-vous')} affiches sur ${MONTH_NAMES[agendaState.currentMonth.getMonth()]} ${agendaState.currentMonth.getFullYear()}.`
        : `Aucun rendez-vous sur ${MONTH_NAMES[agendaState.currentMonth.getMonth()]} ${agendaState.currentMonth.getFullYear()} avec les filtres actuels.`;

    const employeId = document.getElementById('filter-employe').value;
    const addParams = new URLSearchParams({ date: agendaState.selectedDate });
    if (employeId) {
        addParams.set('employe', employeId);
    }

    const addUrl = `/plannings/form/nouveau/?${addParams.toString()}`;
    document.getElementById('fab-add-link').href = addUrl;
    document.getElementById('header-add-link').href = addUrl;

    document.querySelectorAll('[data-date-section]').forEach((section) => {
        section.classList.toggle('is-active', section.dataset.dateSection === agendaState.selectedDate);
    });

    if (renderCalendarToo) {
        renderCalendar();
    }
}

function disconnectAgendaObserver() {
    if (agendaState.observer) {
        agendaState.observer.disconnect();
        agendaState.observer = null;
    }
}

function attachAgendaObserver() {
    disconnectAgendaObserver();

    const sections = document.querySelectorAll('[data-date-section]');
    if (!sections.length) {
        return;
    }

    agendaState.observer = new IntersectionObserver((entries) => {
        if (Date.now() < agendaState.ignoreObserverUntil) {
            return;
        }

        const visible = entries
            .filter((entry) => entry.isIntersecting)
            .sort((left, right) => left.boundingClientRect.top - right.boundingClientRect.top);

        if (!visible.length) {
            return;
        }

        const dateKey = visible[0].target.dataset.dateSection;
        if (dateKey && dateKey !== agendaState.selectedDate) {
            agendaState.selectedDate = dateKey;
            updateSelectedUi(true);
        }
    }, {
        root: null,
        threshold: [0.2, 0.4, 0.6],
        rootMargin: '-28% 0px -55% 0px'
    });

    sections.forEach((section) => agendaState.observer.observe(section));
}

function handleCalendarDayClick(dateKey) {
    const selectedDate = parseDateKey(dateKey);

    if (!isSameMonth(selectedDate, agendaState.currentMonth)) {
        agendaState.currentMonth = startOfMonth(selectedDate);
        agendaState.selectedDate = dateKey;
        syncMonthPicker();
        loadAgendaMonth({ scrollToSelected: true, behavior: 'smooth' });
        return;
    }

    agendaState.selectedDate = dateKey;
    updateSelectedUi(true);
    scrollToSection(dateKey, 'smooth');
}

function scrollToSection(dateKey, behavior = 'smooth') {
    const target = document.querySelector(`[data-date-section="${dateKey}"]`);
    if (!target) {
        return;
    }

    const stickyShell = document.getElementById('agenda-calendar-shell');
    const offset = stickyShell ? stickyShell.getBoundingClientRect().height + 24 : 180;
    const top = target.getBoundingClientRect().top + window.scrollY - offset;
    agendaState.ignoreObserverUntil = Date.now() + (behavior === 'smooth' ? 900 : 250);

    window.scrollTo({
        top: Math.max(top, 0),
        behavior
    });
}

function syncMonthPicker() {
    document.getElementById('month-picker').value = monthKey(agendaState.currentMonth);
}

function clearEmployeFilter() {
    const select = getEmployeSelect();
    if (!select || select.disabled) {
        return;
    }
    select.value = '';
    agendaState.detailsCache.clear();
    loadAgendaMonth();
}

function handleMonthPickerChange(event) {
    const value = event.target.value;
    if (!value) {
        return;
    }

    const [year, month] = value.split('-').map(Number);
    const nextMonth = new Date(year, month - 1, 1, 12);
    agendaState.currentMonth = nextMonth;
    agendaState.selectedDate = toDateKey(clampDateToMonth(parseDateKey(agendaState.selectedDate), nextMonth));
    agendaState.detailsCache.clear();
    loadAgendaMonth({ scrollToSelected: true, behavior: 'auto' });
}

function navigateMonth(offset) {
    const nextMonth = new Date(agendaState.currentMonth.getFullYear(), agendaState.currentMonth.getMonth() + offset, 1, 12);
    agendaState.currentMonth = nextMonth;
    agendaState.selectedDate = toDateKey(clampDateToMonth(parseDateKey(agendaState.selectedDate), nextMonth));
    agendaState.detailsCache.clear();
    syncMonthPicker();
    loadAgendaMonth({ scrollToSelected: true, behavior: 'auto' });
}

function goToToday() {
    const today = parseDateKey(TODAY_KEY);
    agendaState.currentMonth = startOfMonth(today);
    agendaState.selectedDate = TODAY_KEY;
    agendaState.detailsCache.clear();
    syncMonthPicker();
    loadAgendaMonth({ scrollToSelected: true, behavior: 'smooth' });
}

function setCalendarMode(mode, updateCalendar = true) {
    agendaState.calendarMode = mode;
    document.getElementById('mode-week').classList.toggle('btn-active', mode === 'week');
    document.getElementById('mode-month').classList.toggle('btn-active', mode === 'month');

    if (updateCalendar) {
        renderCalendar();
    }
}

function setLoading(isLoading) {
    agendaState.loading = isLoading;
    document.getElementById('agenda-loading').classList.toggle('hidden', !isLoading);
    document.getElementById('agenda-list').classList.toggle('hidden', isLoading && !agendaState.plannings.length);
    document.getElementById('agenda-empty-state').classList.toggle('hidden', isLoading);
}

function renderEmptyState(title, text) {
    const emptyState = document.getElementById('agenda-empty-state');
    document.getElementById('agenda-empty-title').textContent = title;
    document.getElementById('agenda-empty-text').textContent = text;
    emptyState.classList.remove('hidden');
}

function hideEmptyState() {
    document.getElementById('agenda-empty-state').classList.add('hidden');
}

async function togglePlanningDetails(planningId) {
    const container = document.getElementById(`planning-details-${planningId}`);
    if (!container) {
        return;
    }

    if (!container.classList.contains('hidden')) {
        container.classList.add('hidden');
        container.innerHTML = '';
        return;
    }

    container.classList.remove('hidden');

    if (agendaState.detailsCache.has(planningId)) {
        container.innerHTML = renderPlanningDetails(agendaState.detailsCache.get(planningId));
        return;
    }

    container.innerHTML = `
        <div class="flex items-center gap-3 text-sm text-base-content/65">
            <span class="loading loading-spinner loading-sm"></span>
            Chargement des details...
        </div>
    `;

    try {
        const response = await fetch(`/plannings/api/details/${planningId}/`);
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }

        const data = await response.json();
        agendaState.detailsCache.set(planningId, data);
        container.innerHTML = renderPlanningDetails(data);
    } catch (error) {
        console.error('Impossible de charger les details du planning', error);
        container.innerHTML = `
            <div class="alert alert-error">
                Impossible de charger les details de ce rendez-vous.
            </div>
        `;
    }
}

function renderPlanningDetails(data) {
    const avances = data.avances || [];
    const livraisons = data.livraisons || [];
    const paiements = data.paiements || [];
    const blocks = [];

    if (avances.length) {
        blocks.push(`
            <div class="agenda-detail-block">
                <h5 class="mb-3 text-sm font-semibold uppercase tracking-[0.24em] text-base-content/55">Avances</h5>
                <div class="space-y-2">
                    ${avances.map((avance) => `
                        <div class="agenda-detail-item">
                            <div class="font-semibold text-base-content">${escapeHtml(avance.designation || 'Designation')}</div>
                            <div class="mt-1 text-sm text-base-content/70">
                                ${escapeHtml(formatAmount(avance.quantity || 0))} x ${escapeHtml(formatAmount(avance.pu || 0))} = ${escapeHtml(formatAmount(avance.montant || 0))}
                            </div>
                            <div class="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-base-content/65">
                                ${avance.acheteur ? `<span>Acheteur: ${escapeHtml(avance.acheteur)}</span>` : ''}
                                ${avance.equipement_nom ? `<span>Equipement: ${escapeHtml(avance.equipement_nom)}</span>` : ''}
                                ${avance.point_eau_idxlsx ? `<span>Point d'eau: ${escapeHtml(avance.point_eau_idxlsx)}</span>` : ''}
                                ${avance.trajet ? `<span>Trajet: ${escapeHtml(avance.point_a_nom || '')} -> ${escapeHtml(avance.point_b_nom || '')}</span>` : ''}
                            </div>
                        </div>
                    `).join('')}
                </div>
            </div>
        `);
    }

    if (livraisons.length) {
        blocks.push(`
            <div class="agenda-detail-block">
                <h5 class="mb-3 text-sm font-semibold uppercase tracking-[0.24em] text-base-content/55">Livraisons</h5>
                <div class="space-y-2">
                    ${livraisons.map((livraison) => `
                        <div class="agenda-detail-item">
                            <div class="font-semibold text-base-content">${escapeHtml(livraison.designation || 'Designation')}</div>
                            <div class="mt-1 text-sm text-base-content/70">${escapeHtml(formatAmount(livraison.quantite || 0))} unite(s)</div>
                            <div class="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-base-content/65">
                                ${livraison.magasin ? `<span>Magasin: ${escapeHtml(livraison.magasin)}</span>` : ''}
                                ${livraison.equipement_nom ? `<span>Equipement: ${escapeHtml(livraison.equipement_nom)}</span>` : ''}
                                ${livraison.point_eau_idxlsx ? `<span>Point d'eau: ${escapeHtml(livraison.point_eau_idxlsx)}</span>` : ''}
                            </div>
                        </div>
                    `).join('')}
                </div>
            </div>
        `);
    }

    if (paiements.length) {
        blocks.push(`
            <div class="agenda-detail-block">
                <h5 class="mb-3 text-sm font-semibold uppercase tracking-[0.24em] text-base-content/55">Paiements</h5>
                <div class="space-y-2">
                    ${paiements.map((paiement) => `
                        <div class="agenda-detail-item">
                            <div class="font-semibold text-base-content">${escapeHtml(paiement.point_eau_label || 'Point d'eau')}</div>
                            <div class="mt-1 text-sm text-base-content/70">
                                ${escapeHtml(formatAmount(paiement.quantite || 0))} x ${escapeHtml(formatAmount(paiement.prix_unitaire || 0))} = ${escapeHtml(formatAmount(paiement.montant || 0))}
                            </div>
                            <div class="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-base-content/65">
                                <span>${paiement.paye ? 'Paye' : 'Non paye'}</span>
                                ${paiement.date_facture ? `<span>Facture: ${escapeHtml(paiement.date_facture)}</span>` : ''}
                                ${paiement.date_paiement ? `<span>Paiement: ${escapeHtml(paiement.date_paiement)}</span>` : ''}
                                ${paiement.numero_diamex ? `<span>DiameX: ${escapeHtml(paiement.numero_diamex)}</span>` : ''}
                            </div>
                        </div>
                    `).join('')}
                </div>
            </div>
        `);
    }

    if (!blocks.length) {
        return `
            <div class="agenda-day-empty">
                <i class="fas fa-circle-info text-base-content/40"></i>
                <span>Aucun detail complementaire pour ce rendez-vous.</span>
            </div>
        `;
    }

    return blocks.join('');
}

function showToast(message, tone = 'info') {
    const toast = document.getElementById('agenda-toast');
    toast.className = `agenda-toast alert alert-${tone} shadow-lg w-[min(92vw,26rem)]`;
    toast.textContent = message;
    toast.classList.remove('hidden');
    requestAnimationFrame(() => toast.classList.add('is-visible'));

    window.clearTimeout(showToast._timeout);
    showToast._timeout = window.setTimeout(() => {
        toast.classList.remove('is-visible');
        window.setTimeout(() => toast.classList.add('hidden'), 240);
    }, 2600);
}
</script>


    <!-- Script pour la gestion du thème et de la langue -->
    <script>
        // Gestion du changement de langue
        function changeLanguage(language) {
            // Appel AJAX pour changer la langue cote serveur
            const formData = new FormData();
            formData.append('language', language);

            fetch('/api/set-language/', {
                method: 'POST',
                body: formData,
                headers: {
                    'X-CSRFToken': getCookie('csrftoken')
                }
            })
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        // Sauvegarder la preference en localStorage
                        localStorage.setItem('hydria-language', language);

                        // Recharger la page pour appliquer les traductions
                        location.reload();
                    } else {
                        console.error('Erreur lors du changement de langue');
                    }
                })
                .catch(error => {
                    console.error('Erreur reseau:', error);
                    // Fallback: recharger quand meme
                    localStorage.setItem('hydria-language', language);
                    location.reload();
                });
        }

        // Fonction helper pour recuperer le CSRF token
        function getCookie(name) {
            let cookieValue = null;
            if (document.cookie && document.cookie !== '') {
                const cookies = document.cookie.split(';');
                for (let i = 0; i < cookies.length; i++) {
                    const cookie = cookies[i].trim();
                    if (cookie.substring(0, name.length + 1) === (name + '=')) {
                        cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                        break;
                    }
                }
            }
            return cookieValue;
        }

        // Gestion du theme clair/sombre pour Django
        const initTheme = () => {
            const savedTheme = localStorage.getItem('hydria-theme') || 'hydriaDark';
            const htmlElement = document.documentElement;
            const themeToggle = document.getElementById('theme-toggle');

            // Appliquer le theme (normalement deja fait par le script du head)
            htmlElement.setAttribute('data-theme', savedTheme);

            // Activer les transitions apres le chargement initial
            htmlElement.classList.add('loaded');

            // Synchroniser l'etat du bouton
            if (themeToggle) {
                themeToggle.checked = savedTheme === 'winter';
            }
        };

        const toggleTheme = () => {
            const htmlElement = document.documentElement;
            const currentTheme = htmlElement.getAttribute('data-theme');
            const newTheme = currentTheme === 'hydriaDark' ? 'winter' : 'hydriaDark';

            // Appliquer le nouveau theme
            htmlElement.setAttribute('data-theme', newTheme);
            localStorage.setItem('hydria-theme', newTheme);
        };

        // Initialiser le theme au chargement de la page
        document.addEventListener('DOMContentLoaded', initTheme);

        // Ajouter l'evenement au bouton de theme
        document.addEventListener('DOMContentLoaded', () => {
            const themeToggle = document.getElementById('theme-toggle');
            if (themeToggle) {
                themeToggle.addEventListener('change', toggleTheme);
            }

            // Initialiser la langue
            initLanguage();

            // Initialiser le statut en ligne/hors ligne
            initOnlineStatus();
        });

        // Gestion du changement de langue
        const initLanguage = () => {
            const savedLanguage = localStorage.getItem('hydria-language') || 'fr';
            const currentLanguageEl = document.getElementById('current-language');

            if (currentLanguageEl) {
                currentLanguageEl.textContent = savedLanguage === 'fr' ? 'FR' : 'MG';
            }

            // Appliquer la langue a l'element HTML
            document.documentElement.lang = savedLanguage;
        };

        // Gestion du statut en ligne/hors ligne
        const initOnlineStatus = () => {
            const onlineIndicator = document.getElementById('online-indicator');
            const onlineStatus = document.getElementById('online-status');

            // Fonction pour mettre a jour le statut
            const updateOnlineStatus = () => {
                if (navigator.onLine) {
                    onlineIndicator.className = 'w-2 h-2 bg-success rounded-full animate-pulse';
                    onlineStatus.textContent = 'En ligne';
                    onlineStatus.className = 'text-xs text-success hidden sm:block';
                } else {
                    onlineIndicator.className = 'w-2 h-2 bg-error rounded-full';
                    onlineStatus.textContent = 'Hors ligne';
                    onlineStatus.className = 'text-xs text-error hidden sm:block';
                }
            };

            // Mettre a jour le statut initial
            updateOnlineStatus();

            // Ecouter les changements de statut de connexion
            window.addEventListener('online', updateOnlineStatus);
            window.addEventListener('offline', updateOnlineStatus);

            // Verification periodique de la connexion (optionnel)
            setInterval(async () => {
                try {
                    const response = await fetch('/static/favicon.ico', {
                        method: 'HEAD',
                        cache: 'no-cache'
                    });
                    if (!response.ok && navigator.onLine) {
                        // Simuler un evenement offline si la requete echoue
                        window.dispatchEvent(new Event('offline'));
                    }
                } catch (error) {
                    if (navigator.onLine) {
                        window.dispatchEvent(new Event('offline'));
                    }
                }
            }, 30000); // Verification toutes les 30 secondes
        };

        // Prevenir le flash lors de la navigation interne
        document.addEventListener('visibilitychange', () => {
            if (!document.hidden) {
                const savedTheme = localStorage.getItem('hydria-theme') || 'hydriaDark';
                document.documentElement.setAttribute('data-theme', savedTheme);
            }
        });

    </script>

    <!-- Modals pour Assistant IA -->

    <!-- Modal Requête Rapide -->
    <input type="checkbox" id="quickQueryModal" class="modal-toggle" />
    <div class="modal">
        <div class="modal-box max-w-2xl">
            <label for="quickQueryModal" class="btn btn-sm btn-circle absolute right-2 top-2">o.</label>
            <h3 class="font-bold text-lg mb-4">Requête Rapide</h3>
            <p class="text-sm mb-4">Posez une question à l'Assistant IA pour obtenir une réponse instantanée</p>

            <textarea id="quickQueryInput" class="textarea textarea-bordered w-full h-24 mb-4"
                placeholder="Ex: Combien d'habitants à Ankazondandy ?"></textarea>

            <div class="flex gap-2 mb-4">
                <button onclick="sendQuickQuery()" class="btn btn-primary">
                    <i class="fas fa-paper-plane mr-2"></i>Envoyer
                </button>
                <button
                    onclick="document.getElementById('quickQueryInput').value=''; document.getElementById('quickQueryResponse').innerHTML=''"
                    class="btn btn-ghost">
                    <i class="fas fa-eraser mr-2"></i>Effacer
                </button>
            </div>

            <div id="quickQueryResponse" class="bg-base-200 p-4 rounded-lg min-h-24"></div>
        </div>
    </div>

    <!-- Modal Analyse de Données -->
    <input type="checkbox" id="dataAnalysisModal" class="modal-toggle" />
    <div class="modal">
        <div class="modal-box max-w-4xl">
            <label for="dataAnalysisModal" class="btn btn-sm btn-circle absolute right-2 top-2">o.</label>
            <h3 class="font-bold text-lg mb-4">Analyse de Données</h3>

            <div class="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
                <div class="card bg-base-200">
                    <div class="card-body">
                        <h4 class="card-title text-sm">Statistiques Globales</h4>
                        <div id="globalStats" class="text-sm">
                            <div class="loading loading-spinner"></div> Chargement...
                        </div>
                    </div>
                </div>

                <div class="card bg-base-200">
                    <div class="card-body">
                        <h4 class="card-title text-sm">Tendances</h4>
                        <div id="trends" class="text-sm">
                            <div class="loading loading-spinner"></div> Chargement...
                        </div>
                    </div>
                </div>
            </div>

            <div class="form-control">
                <label class="label"><span class="label-text">Analyse personnalisée</span></label>
                <select id="analysisType" class="select select-bordered mb-4">
                    <option value="population">Analyse par population</option>
                    <option value="infrastructure">Analyse des infrastructures</option>
                    <option value="financier">Analyse financière</option>
                    <option value="activite">Analyse des activités</option>
                </select>
            </div>

            <button onclick="runAnalysis()" class="btn btn-primary">
                <i class="fas fa-chart-line mr-2"></i>Lancer l'analyse
            </button>
        </div>
    </div>

    <!-- Modal Génération de Rapport -->
    <input type="checkbox" id="reportModal" class="modal-toggle" />
    <div class="modal">
        <div class="modal-box max-w-3xl">
            <label for="reportModal" class="btn btn-sm btn-circle absolute right-2 top-2">o.</label>
            <h3 class="font-bold text-lg mb-4">Génération de Rapport</h3>

            <div class="form-control mb-4">
                <label class="label"><span class="label-text">Type de rapport</span></label>
                <select id="reportType" class="select select-bordered">
                    <option value="mensuel">Rapport mensuel</option>
                    <option value="trimestriel">Rapport trimestriel</option>
                    <option value="annuel">Rapport annuel</option>
                    <option value="custom">Rapport personnalisé</option>
                </select>
            </div>

            <div class="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
                <div class="form-control">
                    <label class="label"><span class="label-text">Période de début</span></label>
                    <input type="date" id="reportStartDate" class="input input-bordered">
                </div>
                <div class="form-control">
                    <label class="label"><span class="label-text">Période de fin</span></label>
                    <input type="date" id="reportEndDate" class="input input-bordered">
                </div>
            </div>

            <div class="form-control mb-4">
                <label class="label"><span class="label-text">Sections à inclure</span></label>
                <div class="flex flex-wrap gap-2">
                    <label class="label cursor-pointer gap-2">
                        <input type="checkbox" class="checkbox checkbox-sm" value="stats" checked>
                        <span class="label-text text-sm">Statistiques</span>
                    </label>
                    <label class="label cursor-pointer gap-2">
                        <input type="checkbox" class="checkbox checkbox-sm" value="plannings" checked>
                        <span class="label-text text-sm">Plannings</span>
                    </label>
                    <label class="label cursor-pointer gap-2">
                        <input type="checkbox" class="checkbox checkbox-sm" value="finances" checked>
                        <span class="label-text text-sm">Finances</span>
                    </label>
                    <label class="label cursor-pointer gap-2">
                        <input type="checkbox" class="checkbox checkbox-sm" value="infrastructure" checked>
                        <span class="label-text text-sm">Infrastructure</span>
                    </label>
                </div>
            </div>

            <button onclick="generateReport()" class="btn btn-primary">
                <i class="fas fa-file-pdf mr-2"></i>Générer le rapport PDF
            </button>
        </div>
    </div>

    <!-- Modal Plannings Semaine -->
    <input type="checkbox" id="weekPlanningsModal" class="modal-toggle" />
    <div class="modal">
        <div class="modal-box max-w-4xl">
            <label for="weekPlanningsModal" class="btn btn-sm btn-circle absolute right-2 top-2">o.</label>
            <h3 class="font-bold text-lg mb-4">Plannings de la Semaine</h3>
            <div id="weekPlanningsContent" class="space-y-4">
                <div class="loading loading-spinner"></div> Chargement des plannings...
            </div>
        </div>
    </div>

    <!-- Modal Factures Impayées -->
    <input type="checkbox" id="unpaidInvoicesModal" class="modal-toggle" />
    <div class="modal">
        <div class="modal-box max-w-4xl">
            <label for="unpaidInvoicesModal" class="btn btn-sm btn-circle absolute right-2 top-2">o.</label>
            <h3 class="font-bold text-lg mb-4">Factures Impayées</h3>
            <div id="unpaidInvoicesContent" class="space-y-4">
                <div class="loading loading-spinner"></div> Chargement des factures...
            </div>
        </div>
    </div>

    <!-- Modal Calculatrice -->
    <dialog id="globalCalculatorModal" class="modal">
        <div class="modal-box max-w-7xl w-11/12">
            <h3 class="font-bold text-lg mb-2 flex items-center gap-2">
                <i class="fas fa-calculator text-success"></i>
                Calculatrice avancee
            </h3>
            <p class="text-sm text-base-content/70 mb-4">
                Mode calcul a lignes memorisees (references L1, L2, ...), mode devis (quantite, prix unitaire, montant), mode total et cahier de caisse.
            </p>

            <div role="tablist" class="tabs tabs-boxed mb-4">
                <button type="button" id="calculatorModeCalcTab" class="tab tab-active"
                    onclick="switchCalculatorMode('calc')">
                    Calculs
                </button>
                <button type="button" id="calculatorModeQuoteTab" class="tab" onclick="switchCalculatorMode('quote')">
                    Mode devis
                </button>
                <button type="button" id="calculatorModeTotalTab" class="tab" onclick="switchCalculatorMode('total')">
                    Mode total
                </button>
                <button type="button" id="calculatorModeCashTab" class="tab" onclick="switchCalculatorMode('cash')">
                    Cahier de caisse
                </button>
            </div>

            <div id="calculatorCalcPanel">
                <div class="flex flex-wrap items-center gap-2 mb-3">
                    <button type="button" class="btn btn-sm btn-primary" onclick="addCalcLine()">
                        <i class="fas fa-plus mr-1"></i>Ligne
                    </button>
                    <button type="button" class="btn btn-sm btn-ghost" onclick="recalculateCalculatorLines()">
                        <i class="fas fa-sync-alt mr-1"></i>Recalculer
                    </button>
                    <button type="button" class="btn btn-sm btn-ghost" onclick="clearCalcLines()">
                        <i class="fas fa-eraser mr-1"></i>Vider calculs
                    </button>
                    <span id="calcMemoryInfo" class="badge badge-outline"></span>
                    <span id="calcActiveLineInfo" class="badge badge-outline badge-success"></span>
                    <span class="text-xs text-base-content/60">Astuce: Entrez une expression puis utilisez des references
                        comme L1 + L2.</span>
                </div>

                <div class="hydria-calculator-scroll border border-base-300 rounded-lg">
                    <table class="table table-sm hydria-calculator-table">
                        <thead>
                            <tr>
                                <th>Ligne</th>
                                <th>Libelle</th>
                                <th>Calcul</th>
                                <th>Resultat</th>
                                <th class="text-right">Actions</th>
                            </tr>
                        </thead>
                        <tbody id="calcRowsBody"></tbody>
                    </table>
                </div>
            </div>

            <div id="calculatorQuotePanel" class="hidden">
                <div class="flex flex-wrap items-center gap-2 mb-3">
                    <button type="button" class="btn btn-sm btn-primary" onclick="addQuoteRow()">
                        <i class="fas fa-plus mr-1"></i>Ligne devis
                    </button>
                    <button type="button" class="btn btn-sm btn-ghost" onclick="clearQuoteRows()">
                        <i class="fas fa-eraser mr-1"></i>Vider devis
                    </button>
                    <span id="quoteMemoryInfo" class="badge badge-outline"></span>
                </div>

                <div class="hydria-calculator-scroll border border-base-300 rounded-lg">
                    <table class="table table-sm hydria-calculator-table">
                        <thead>
                            <tr>
                                <th>#</th>
                                <th>Designation</th>
                                <th>Quantite</th>
                                <th>Prix unitaire</th>
                                <th>Montant</th>
                                <th class="text-right">Actions</th>
                            </tr>
                        </thead>
                        <tbody id="quoteRowsBody"></tbody>
                    </table>
                </div>

                <div class="mt-4 flex justify-end">
                    <div class="stats shadow bg-base-200">
                        <div class="stat py-3 px-4">
                            <div class="stat-title">Total devis</div>
                            <div id="quoteGrandTotal" class="stat-value text-success text-2xl">0,00 Ar</div>
                        </div>
                    </div>
                </div>
            </div>

            <div id="calculatorTotalPanel" class="hidden">
                <div class="flex flex-wrap items-center gap-2 mb-3">
                    <button type="button" class="btn btn-sm btn-primary" onclick="addTotalRow()">
                        <i class="fas fa-plus mr-1"></i>Ligne total
                    </button>
                    <button type="button" class="btn btn-sm btn-ghost" onclick="clearTotalRows()">
                        <i class="fas fa-eraser mr-1"></i>Vider total
                    </button>
                    <span id="totalMemoryInfo" class="badge badge-outline"></span>
                </div>

                <div class="hydria-calculator-scroll border border-base-300 rounded-lg">
                    <table class="table table-sm hydria-calculator-table">
                        <thead>
                            <tr>
                                <th>#</th>
                                <th>Designation</th>
                                <th>Prix unitaire</th>
                                <th class="text-right">Actions</th>
                            </tr>
                        </thead>
                        <tbody id="totalRowsBody"></tbody>
                    </table>
                </div>

                <div class="mt-4 flex justify-end">
                    <div class="stats shadow bg-base-200">
                        <div class="stat py-3 px-4">
                            <div class="stat-title">Total</div>
                            <div id="totalGrandTotal" class="stat-value text-success text-2xl">0,00 Ar</div>
                        </div>
                    </div>
                </div>
            </div>

            <div id="calculatorCashPanel" class="hidden">
                <div class="flex flex-wrap items-center gap-2 mb-3">
                    <button type="button" class="btn btn-sm btn-primary" onclick="addCashRow()">
                        <i class="fas fa-plus mr-1"></i>Ligne caisse
                    </button>
                    <button type="button" class="btn btn-sm btn-ghost" onclick="clearCashRows()">
                        <i class="fas fa-eraser mr-1"></i>Vider caisse
                    </button>
                    <span id="cashMemoryInfo" class="badge badge-outline"></span>
                    <input id="cashBookNameInput" type="text" class="input input-bordered input-xs w-40"
                        placeholder="Nom du cahier">
                    <button type="button" class="btn btn-sm btn-ghost" onclick="saveCurrentCashBook()">
                        <i class="fas fa-save mr-1"></i>Enregistrer
                    </button>
                    <select id="cashBookSelect" class="select select-bordered select-xs w-52"
                        onchange="onCashBookSelectionChange(this.value)">
                        <option value="">Cahiers enregistres</option>
                    </select>
                    <button type="button" class="btn btn-sm btn-ghost" onclick="loadSelectedCashBook()">
                        <i class="fas fa-folder-open mr-1"></i>Charger
                    </button>
                    <button type="button" class="btn btn-sm btn-ghost" onclick="deleteSelectedCashBook()">
                        <i class="fas fa-trash-alt mr-1"></i>Supprimer
                    </button>
                </div>

                <div class="hydria-calculator-scroll border border-base-300 rounded-lg">
                    <table class="table table-sm hydria-calculator-table">
                        <thead>
                            <tr>
                                <th>#</th>
                                <th>Libelle (facultatif)</th>
                                <th>Entree</th>
                                <th>Sortie</th>
                                <th>Solde cumule</th>
                                <th>Pointage (N facture)</th>
                                <th class="text-right">Actions</th>
                            </tr>
                        </thead>
                        <tbody id="cashRowsBody"></tbody>
                    </table>
                </div>

                <div class="mt-4 flex justify-end">
                    <div class="stats shadow bg-base-200">
                        <div class="stat py-3 px-4">
                            <div class="stat-title">Solde caisse</div>
                            <div id="cashGrandBalance" class="stat-value text-success text-2xl">0,00 Ar</div>
                        </div>
                    </div>
                </div>
            </div>

            <div class="modal-action">
                <button type="button" class="btn btn-ghost" onclick="clearCalculatorStorage()">
                    <i class="fas fa-trash-alt mr-1"></i>Effacer memoire
                </button>
                <button type="button" class="btn btn-primary" onclick="closeCalculatorModal()">
                    Fermer
                </button>
            </div>
        </div>
        <form method="dialog" class="modal-backdrop">
            <button>close</button>
        </form>
    </dialog>

    <!-- Bouton flottant Assistant IA - POSITIONNE EN FIXED POUR RESTER VISIBLE -->
    <div id="floating-chat-container"
        style="position: fixed; bottom: 1.5rem; right: 1.5rem; z-index: 99999; pointer-events: none;">
        <!-- Bouton principal -->
        <div id="floating-chat-btn" style="pointer-events: auto;">
            <button
                class="btn btn-circle btn-primary btn-lg shadow-lg hover:shadow-xl transition-all duration-300 group"
                onclick="toggleFloatingChat()">
                <svg id="chat-icon" class="w-6 h-6 group-hover:scale-110 transition-transform" fill="none"
                    stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                        d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z">
                    </path>
                </svg>
                <svg id="close-icon" class="w-6 h-6 hidden" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12">
                    </path>
                </svg>
            </button>
        </div>

        <!-- Fenêtre de chat -->
        <div id="floating-chat-window" class="hidden"
            style="position: fixed; bottom: 6rem; right: 1.5rem; width: 24rem; height: 28rem; background: var(--fallback-b1,oklch(var(--b1))); border-radius: 1rem; box-shadow: 0 25px 50px -12px rgba(0,0,0,0.25); border: 1px solid var(--fallback-bc,oklch(var(--bc)/0.2)); pointer-events: auto; transform: scale(0.95); opacity: 0; transition: all 0.3s;">
            <!-- En-tête -->
            <div
                style="display: flex; align-items: center; justify-content: space-between; padding: 1rem; border-bottom: 1px solid var(--fallback-bc,oklch(var(--bc)/0.2)); background: var(--fallback-p,oklch(var(--p))); color: var(--fallback-pc,oklch(var(--pc))); border-radius: 1rem 1rem 0 0;">
                <div style="display: flex; align-items: center; gap: 0.5rem;">
                    <div
                        style="width: 2rem; height: 2rem; background: rgba(255,255,255,0.2); border-radius: 50%; display: flex; align-items: center; justify-content: center;">
                        <i class="fas fa-robot"></i></div>
                    <div>
                        <div style="font-weight: 600; font-size: 0.875rem;">Assistant Hydria</div>
                        <div style="font-size: 0.75rem; opacity: 0.75;">En ligne</div>
                    </div>
                </div>
                <button onclick="toggleFloatingChat()" class="btn btn-ghost btn-xs" style="color: inherit;">
                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12">
                        </path>
                    </svg>
                </button>
            </div>

            <!-- Messages -->
            <div id="floating-messages" style="height: 18rem; overflow-y: auto; padding: 1rem;">
                <div class="chat chat-start">
                    <div class="chat-image avatar">
                        <div
                            style="width: 2rem; border-radius: 50%; background: var(--fallback-p,oklch(var(--p))); color: var(--fallback-pc,oklch(var(--pc))); display: flex; align-items: center; justify-content: center; font-size: 0.875rem;">
                            <i class="fas fa-robot"></i></div>
                    </div>
                    <div class="chat-bubble chat-bubble-primary" style="font-size: 0.875rem;">
                        Bonjour ! Comment puis-je vous aider avec vos données Hydria ?
                    </div>
                </div>
            </div>

            <!-- Input -->
            <div style="padding: 0.75rem; border-top: 1px solid var(--fallback-bc,oklch(var(--bc)/0.2));">
                <form id="floating-chat-form" class="flex gap-2" onsubmit="handleChatSubmit(event);">
                    <input type="text" id="chat-input" placeholder="Tapez votre message..."
                        class="input input-bordered input-sm flex-1" style="font-size: 0.875rem;">
                    <button type="submit" class="btn btn-primary btn-sm">
                        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                                d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8"></path>
                        </svg>
                    </button>
                </form>
            </div>
        </div>
    </div>

    <script>
        // Animation de rebond au chargement
        document.addEventListener('DOMContentLoaded', function () {
            const btnContainer = document.getElementById('floating-chat-btn');
            if (btnContainer) {
                const btn = btnContainer.querySelector('button');
                if (btn) {
                    setTimeout(() => {
                        btn.classList.add('animate-bounce');
                        setTimeout(() => btn.classList.remove('animate-bounce'), 3000);
                    }, 1000);
                }
            }
        });

        // Toggle du chat
        let chatOpen = false;
        function toggleFloatingChat() {
            const chatWindow = document.getElementById('floating-chat-window');
            const chatIcon = document.getElementById('chat-icon');
            const closeIcon = document.getElementById('close-icon');

            chatOpen = !chatOpen;

            if (chatOpen) {
                chatWindow.classList.remove('hidden');
                setTimeout(() => {
                    chatWindow.style.transform = 'scale(1)';
                    chatWindow.style.opacity = '1';
                }, 10);
                chatIcon.classList.add('hidden');
                closeIcon.classList.remove('hidden');
            } else {
                chatWindow.style.transform = 'scale(0.95)';
                chatWindow.style.opacity = '0';
                setTimeout(() => {
                    chatWindow.classList.add('hidden');
                }, 300);
                chatIcon.classList.remove('hidden');
                closeIcon.classList.add('hidden');
            }
        }

        // Fonction pour convertir le markdown en HTML
        function formatMarkdown(content) {
            // Convertir le markdown en HTML si marked est disponible
            if (typeof marked !== 'undefined') {
                // Configurer marked pour supporter les tableaux et les sauts de ligne
                marked.setOptions({
                    breaks: true,         // Convertir \n en <br>
                    gfm: true,           // GitHub Flavored Markdown (tableaux)
                    tables: true         // Support explicite des tableaux
                });

                // Utiliser marked() ou marked.parse() selon la version
                try {
                    return typeof marked.parse === 'function' ? marked.parse(content) : marked(content);
                } catch (e) {
                    console.error('Erreur lors de la conversion markdown:', e);
                    // Fallback sur formatage basique
                }
            }

            // Formatage basique (si marked n'est pas charge)
            return content
                .replace(/\n/g, '<br>')
                .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
                .replace(/\*(.*?)\*/g, '<em>$1</em>');
        }

        // Fonction pour appeler l'API chatbot
        async function queryChatbotAPI(question) {
            try {
                const response = await fetch('/api/chatbot/', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]').value
                    },
                    body: JSON.stringify({ question: question })
                });

                const data = await response.json();
                return data;
            } catch (error) {
                console.error('Erreur API:', error);
                return {
                    success: false,
                    answer: "Erreur de connexion a la base de donnees."
                };
            }
        }

        // Base de connaissances du chatbot
        function getChatbotResponse(userMessage) {
            const msg = userMessage.toLowerCase();

            // Detection des questions necessitant l'API (statistiques)
            const needsAPI = msg.match(/combien|nombre|habitant|population|point.*eau.*dans|ouvrage.*dans|commune/i);

            if (needsAPI) {
                // Retourner une promesse pour les questions API
                return queryChatbotAPI(userMessage);
            }

            // Salutations
            if (msg.match(/bonjour|salut|hello|hey|bonsoir/i)) {
                return Promise.resolve({ success: true, answer: "Bonjour ! Je suis l'assistant Hydria. Comment puis-je vous aider aujourd'hui ? " });
            }

            // Navigation
            if (msg.match(/planning|calendrier/i)) {
                return Promise.resolve({ success: true, answer: "Pour gerer vos plannings, utilisez le menu 'Plannings' en haut. Vous y trouverez :\n- Vue d'ensemble\n- Vue calendrier\n- Saisie planning\n- Gestion des livraisons et avances" });
            }

            if (msg.match(/point.*eau|branchement|abonne/i) && !needsAPI) {
                return Promise.resolve({ success: true, answer: "Pour gerer les points d'eau, allez dans 'Organisations' > 'Points d'eau'. Vous pouvez creer, modifier et suivre tous les branchements et abonnes." });
            }

            if (msg.match(/equipement|infrastructure|ouvrage/i) && !needsAPI) {
                return Promise.resolve({ success: true, answer: "Pour gerer les equipements et infrastructures :\n- Menu 'Organisations' > 'Equipements'\n- Menu 'Organisations' > 'Ouvrages'\nVous pouvez ajouter des photos, coordonnees GPS et points de controle." });
            }

            if (msg.match(/inspection|controle|visite/i)) {
                return Promise.resolve({ success: true, answer: "Pour les inspections, allez dans 'Inspections' > 'Calendrier des inspections'. Vous pouvez planifier et effectuer des controles avec photos et points de controle." });
            }

            if (msg.match(/employe|personnel|staff/i)) {
                return Promise.resolve({ success: true, answer: "Pour gerer les employes, utilisez le menu 'Employes'. Vous pouvez gerer les profils, postes et affectations du personnel." });
            }

            if (msg.match(/stock|inventaire|produit/i)) {
                return Promise.resolve({ success: true, answer: "Pour gerer les stocks, allez dans 'Gestion des stocks'. Vous pouvez suivre les mouvements, faire des inventaires et gerer les produits." });
            }

            if (msg.match(/facture|paiement|tarif|compteur/i)) {
                return Promise.resolve({ success: true, answer: "Pour la facturation :\n- 'Facturation' > 'Releves des compteurs'\n- 'Facturation' > 'Tarifs volumetriques'\n- 'Facturation' > 'Compteurs de tete'" });
            }

            if (msg.match(/rapport|statistique|dashboard/i)) {
                return Promise.resolve({ success: true, answer: "Pour les rapports et statistiques, consultez :\n- 'Dashboard' pour une vue d'ensemble\n- 'Rapports' pour des analyses detaillees\n? Chaque module a ses propres statistiques" });
            }

            if (msg.match(/carte|geolocalisation|gps|map/i)) {
                return Promise.resolve({ success: true, answer: "Pour voir la carte geographique des infrastructures, allez dans 'Dashboard' > 'Carte geographique'. Vous pouvez visualiser tous vos ouvrages et points d'eau sur la carte." });
            }

            if (msg.match(/photo|image|camera/i)) {
                return Promise.resolve({ success: true, answer: "Vous pouvez ajouter des photos aux points d'eau et equipements via leurs formulaires de creation/modification. Utilisez le bouton 'Prendre photo' pour la camera ou 'Choisir fichier' pour l'explorateur." });
            }

            // Questions generales
            if (msg.match(/aide|help|\?/i)) {
                return Promise.resolve({ success: true, answer: "Je peux vous aider avec :\n- Navigation dans l'application\n- Gestion des plannings et inspections\n- Points d'eau et equipements\n- Facturation et stocks\n- Rapports et statistiques\n- Statistiques (ex: nombre d'habitants, de points d'eau)\n\nPosez-moi une question specifique !" });
            }

            if (msg.match(/merci|thanks/i)) {
                return Promise.resolve({ success: true, answer: "De rien ! N'hesitez pas si vous avez d'autres questions. " });
            }

            // Reponse par defaut
            return Promise.resolve({ success: true, answer: "Je n'ai pas bien compris votre question. Essayez de me demander :\n- Combien d'habitants a [commune] ?\n- Nombre de points d'eau dans [commune]\n- Comment gerer les plannings ?\n- Ou trouver les rapports ?\n\nOu tapez 'aide' pour plus d'informations." });
        }

        // Gestion de la soumission du formulaire chat
        async function handleChatSubmit(event) {
            event.preventDefault();
            const input = document.getElementById('chat-input');
            const message = input.value.trim();

            if (message) {
                const messagesContainer = document.getElementById('floating-messages');

                // Ajouter le message de l'utilisateur
                const userMessage = document.createElement('div');
                userMessage.className = 'chat chat-end mb-2';
                userMessage.innerHTML = `
                    <div class="chat-bubble chat-bubble-accent" style="font-size: 0.875rem;">
                        ${message}
                    </div>
                `;
                messagesContainer.appendChild(userMessage);

                // Reinitialiser l'input
                input.value = '';

                // Scroller vers le bas
                messagesContainer.scrollTop = messagesContainer.scrollHeight;

                // Obtenir et afficher la reponse du bot (async)
                setTimeout(async () => {
                    try {
                        const responseData = await getChatbotResponse(message);
                        const answer = responseData.answer || responseData;

                        const botMessage = document.createElement('div');
                        botMessage.className = 'chat chat-start';
                        botMessage.innerHTML = `
                            <div class="chat-image avatar">
                                <div style="width: 2rem; border-radius: 50%; background: var(--fallback-p,oklch(var(--p))); color: var(--fallback-pc,oklch(var(--pc))); display: flex; align-items: center; justify-content: center; font-size: 0.875rem;"><i class="fas fa-robot"></i></div>
                            </div>
                            <div class="chat-bubble chat-bubble-primary" style="font-size: 0.875rem;">
                                ${formatMarkdown(answer)}
                            </div>
                        `;
                        messagesContainer.appendChild(botMessage);
                        messagesContainer.scrollTop = messagesContainer.scrollHeight;
                    } catch (error) {
                        console.error('Erreur chatbot:', error);
                        const errorMessage = document.createElement('div');
                        errorMessage.className = 'chat chat-start';
                        errorMessage.innerHTML = `
                            <div class="chat-image avatar">
                                <div style="width: 2rem; border-radius: 50%; background: var(--fallback-p,oklch(var(--p))); color: var(--fallback-pc,oklch(var(--pc))); display: flex; align-items: center; justify-content: center; font-size: 0.875rem;"><i class="fas fa-robot"></i></div>
                            </div>
                            <div class="chat-bubble chat-bubble-error" style="font-size: 0.875rem;">
                                Desole, une erreur s'est produite. Veuillez reessayer.
                            </div>
                        `;
                        messagesContainer.appendChild(errorMessage);
                        messagesContainer.scrollTop = messagesContainer.scrollHeight;
                    }
                }, 500);
            }

            return false;
        }

        // Fonctions pour les modals Assistant IA

        // Requete Rapide
        function openQuickQuery() {
            document.getElementById('quickQueryModal').checked = true;
        }

        async function sendQuickQuery() {
            const input = document.getElementById('quickQueryInput');
            const responseDiv = document.getElementById('quickQueryResponse');
            const question = input.value.trim();

            if (!question) {
                alert('Veuillez saisir une question');
                return;
            }

            responseDiv.innerHTML = '<div class="loading loading-spinner"></div> Traitement...';

            try {
                const response = await fetch('/api/chatbot/', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]').value
                    },
                    body: JSON.stringify({ question: question })
                });

                const data = await response.json();

                if (data.success) {
                    responseDiv.innerHTML = `
                        <div class="alert alert-success">
                            <i class="fas fa-check-circle"></i>
                            <span style="white-space: pre-line;">${data.answer}</span>
                        </div>
                    `;
                } else {
                    responseDiv.innerHTML = `
                        <div class="alert alert-error">
                            <i class="fas fa-exclamation-circle"></i>
                            <span>${data.answer || 'Erreur lors du traitement'}</span>
                        </div>
                    `;
                }
            } catch (error) {
                responseDiv.innerHTML = `
                    <div class="alert alert-error">
                        <i class="fas fa-times-circle"></i>
                        <span>Erreur de connexion</span>
                    </div>
                `;
            }
        }

        // Analyse de Donnees
        function openDataAnalysis() {
            document.getElementById('dataAnalysisModal').checked = true;
            loadGlobalStats();
        }

        async function loadGlobalStats() {
            const statsDiv = document.getElementById('globalStats');
            const trendsDiv = document.getElementById('trends');

            try {
                statsDiv.innerHTML = '<span class="loading loading-spinner loading-md"></span>';
                trendsDiv.innerHTML = '<span class="loading loading-spinner loading-md"></span>';

                const response = await fetch('/api/stats/');
                const data = await response.json();

                if (data.success) {
                    const stats = data.stats;
                    const trends = data.trends;

                    statsDiv.innerHTML = `
                        <div class="space-y-2">
                            <div><i class="fas fa-tint text-info"></i> <strong>Points d'eau:</strong> <span class="badge badge-info">${stats.total_points_eau}</span></div>
                            <div><i class="fas fa-check-circle text-success"></i> <strong>Actifs:</strong> <span class="badge badge-success">${stats.active_points}</span></div>
                            <div><i class="fas fa-times-circle text-error"></i> <strong>Inactifs:</strong> <span class="badge badge-error">${stats.inactive_points}</span></div>
                            <div><i class="fas fa-building text-primary"></i> <strong>Ouvrages:</strong> <span class="badge badge-primary">${stats.total_ouvrages}</span></div>
                            <div><i class="fas fa-users text-accent"></i> <strong>Employes:</strong> <span class="badge badge-accent">${stats.total_employes}</span></div>
                            <div><i class="fas fa-box text-warning"></i> <strong>Valeur stock:</strong> <span class="badge badge-warning">${stats.total_stock_value.toFixed(0)} Ar</span></div>
                        </div>
                    `;

                    trendsDiv.innerHTML = `
                        <div class="space-y-2">
                            <div class="flex items-center gap-2">
                                <i class="fas fa-arrow-up text-success"></i>
                                <span class="text-sm">${trends.points_eau} nouveaux points d'eau cette semaine</span>
                            </div>
                            <div class="flex items-center gap-2">
                                <i class="fas fa-info-circle text-info"></i>
                                <span class="text-sm">${stats.new_points_eau_week} branchements recents</span>
                            </div>
                        </div>
                    `;
                } else {
                    statsDiv.innerHTML = '<span class="text-error">Erreur de chargement</span>';
                    trendsDiv.innerHTML = '';
                }
            } catch (error) {
                console.error('Erreur stats:', error);
                statsDiv.innerHTML = '<span class="text-error">Erreur de chargement</span>';
                trendsDiv.innerHTML = '';
            }
        }

        function runAnalysis() {
            const type = document.getElementById('analysisType').value;
            alert(`Analyse "${type}" lancee. Fonctionnalite en developpement.`);
        }

        // Generation de Rapport
        function openReportGeneration() {
            document.getElementById('reportModal').checked = true;
            // Definir les dates par defaut
            const today = new Date();
            const firstDay = new Date(today.getFullYear(), today.getMonth(), 1);
            document.getElementById('reportStartDate').valueAsDate = firstDay;
            document.getElementById('reportEndDate').valueAsDate = today;
        }

        function generateReport() {
            const type = document.getElementById('reportType').value;
            const startDate = document.getElementById('reportStartDate').value;
            const endDate = document.getElementById('reportEndDate').value;

            if (!startDate || !endDate) {
                alert('Veuillez selectionner les dates');
                return;
            }

            alert(`Generation du rapport "${type}" de ${startDate} a ${endDate}.\n\nFonctionnalite en developpement.`);
        }

        // Plannings de la Semaine
        async function showWeekPlannings() {
            document.getElementById('weekPlanningsModal').checked = true;
            const content = document.getElementById('weekPlanningsContent');

            try {
                content.innerHTML = '<div class="text-center py-4"><span class="loading loading-spinner loading-lg"></span></div>';

                const response = await fetch('/api/plannings/week/');
                const data = await response.json();

                if (data.success) {
                    if (data.plannings.length === 0) {
                        content.innerHTML = `
                            <div class="alert alert-info">
                                <i class="fas fa-info-circle"></i>
                                <span>Aucun planning pour cette semaine (${data.week_range.start} - ${data.week_range.end})</span>
                            </div>
                        `;
                    } else {
                        const planningsHTML = data.plannings.map(planning => `
                            <div class="card bg-base-200">
                                <div class="card-body p-4">
                                    <div class="flex justify-between items-center">
                                        <div>
                                            <h4 class="font-bold">${planning.day_name} ${planning.date_display} - ${planning.ouvrage}</h4>
                                            <p class="text-sm text-base-content/70">${planning.commune}</p>
                                        </div>
                                        <span class="badge badge-primary">${planning.status}</span>
                                    </div>
                                </div>
                            </div>
                        `).join('');

                        content.innerHTML = `
                            <div class="mb-4">
                                <p class="text-sm text-base-content/70">Semaine du ${data.week_range.start} au ${data.week_range.end}</p>
                                <p class="font-semibold">${data.total} planning(s) trouve(s)</p>
                            </div>
                            <div class="space-y-3">${planningsHTML}</div>
                        `;
                    }
                } else {
                    content.innerHTML = '<div class="alert alert-error">Erreur de chargement</div>';
                }
            } catch (error) {
                console.error('Erreur plannings:', error);
                content.innerHTML = '<div class="alert alert-error">Erreur de chargement</div>';
            }
        }

        // Factures Impayees
        async function showUnpaidInvoices() {
            document.getElementById('unpaidInvoicesModal').checked = true;
            const content = document.getElementById('unpaidInvoicesContent');

            try {
                content.innerHTML = '<div class="text-center py-4"><span class="loading loading-spinner loading-lg"></span></div>';

                const response = await fetch('/api/invoices/unpaid/');
                const data = await response.json();

                if (data.success) {
                    if (data.invoices.length === 0) {
                        content.innerHTML = `
                            <div class="alert alert-success">
                                <i class="fas fa-check-circle"></i>
                                <span>Aucune facture impayee!</span>
                            </div>
                        `;
                    } else {
                        const invoicesRows = data.invoices.map(invoice => {
                            const badgeClass = invoice.jours_retard > 30 ? 'badge-error' :
                                invoice.jours_retard > 15 ? 'badge-warning' : 'badge-info';
                            return `
                                <tr>
                                    <td>${invoice.numero}</td>
                                    <td>${invoice.client}</td>
                                    <td>${invoice.commune}</td>
                                    <td><strong>${invoice.montant.toLocaleString()} Ar</strong></td>
                                    <td>${invoice.date_facture}</td>
                                    <td><span class="badge ${badgeClass}">${invoice.jours_retard} jours</span></td>
                                </tr>
                            `;
                        }).join('');

                        content.innerHTML = `
                            <div class="overflow-x-auto">
                                <table class="table table-zebra table-sm">
                                    <thead>
                                        <tr>
                                            <th>N Facture</th>
                                            <th>Client</th>
                                            <th>Commune</th>
                                            <th>Montant</th>
                                            <th>Date</th>
                                            <th>Retard</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        ${invoicesRows}
                                    </tbody>
                                </table>
                                <div class="mt-4 p-4 bg-warning/10 rounded-lg">
                                    <p class="text-sm"><i class="fas fa-info-circle mr-2"></i><strong>Total impaye:</strong> ${data.total_amount.toLocaleString()} Ar (${data.total} facture(s))</p>
                                    ${data.note ? `<p class="text-xs text-base-content/70 mt-2">${data.note}</p>` : ''}
                                </div>
                            </div>
                        `;
                    }
                } else {
                    content.innerHTML = '<div class="alert alert-error">Erreur de chargement</div>';
                }
            } catch (error) {
                console.error('Erreur factures:', error);
                content.innerHTML = '<div class="alert alert-error">Erreur de chargement</div>';
            }
        }

        // GPS - Capturer la position automatiquement apres connexion
        function captureGPSPosition() {
            if ("geolocation" in navigator) {
                navigator.geolocation.getCurrentPosition(
                    function (position) {
                        const accuracy = position.coords.accuracy;

                        // Log de la precision pour diagnostic
                        console.log('GPS obtenu avec precision:', accuracy.toFixed(0) + 'm');

                        // Mettre a jour l'indicateur GPS dans le bandeau
                        updateGPSIndicator(accuracy, null, null);

                        // Avertir si la precision est mauvaise (>100m)
                        if (accuracy > 100) {
                            console.warn('s ATTENTION: Precision GPS faible (' + accuracy.toFixed(0) + 'm). Le village detecte peut etre incorrect.');
                        }

                        // Envoyer la position au serveur
                        fetch('/api/capture-gps/', {
                            method: 'POST',
                            headers: {
                                'Content-Type': 'application/json',
                                'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]')?.value || getCookie('csrftoken')
                            },
                            body: JSON.stringify({
                                latitude: position.coords.latitude,
                                longitude: position.coords.longitude,
                                altitude: position.coords.altitude,
                                precision: accuracy
                            })
                        })
                            .then(response => response.json())
                            .then(data => {
                                if (data.success) {
                                    console.log('Position GPS enregistree:', data);
                                    if (data.village_proche) {
                                        const distanceKm = parseFloat(data.distance);
                                        const emoji = distanceKm < 0.5 ? 'o.' : (distanceKm < 2 ? 's' : 'O');
                                        console.log(emoji + ' Village proche:', data.village_proche, '(' + data.distance + ' km)');

                                        // Mettre a jour l'indicateur avec les infos du village
                                        updateGPSIndicator(accuracy, data.village_proche, distanceKm);

                                        // Avertir si le village est loin
                                        if (distanceKm > 2) {
                                            console.warn('s ATTENTION: Le village detecte est loin (' + data.distance + 'km). Verifiez votre position GPS.');
                                        }
                                    }
                                }
                            })
                            .catch(error => {
                                console.error('Erreur GPS:', error);
                                updateGPSIndicator(null, null, null, true);
                            });
                    },
                    function (error) {
                        console.warn('Impossible de capturer la position GPS:', error.message);
                        updateGPSIndicator(null, null, null, true);
                    },
                    {
                        enableHighAccuracy: true,
                        timeout: 30000,  // Augmente a 30 secondes pour permettre au GPS de se stabiliser
                        maximumAge: 0
                    }
                );
            }
        }

        // Mettre a jour l'indicateur GPS dans le bandeau
        function updateGPSIndicator(accuracy, villageName, distanceKm, hasError = false) {
            const icon = document.getElementById('gps-icon');
            const text = document.getElementById('gps-text');
            const badge = document.getElementById('gps-precision-badge');

            if (!icon || !text || !badge) return;

            if (hasError) {
                // GPS desactive ou erreur
                icon.className = 'fas fa-map-marker-alt text-base-content/30';
                text.innerHTML = 'GPS desactive';
                badge.style.display = 'none';
                return;
            }

            if (accuracy !== null) {
                // Determiner la qualite du signal GPS
                let iconClass, badgeClass, badgeText;

                if (accuracy < 50) {
                    // Excellente precision
                    iconClass = 'fas fa-map-marker-alt text-success';
                    badgeClass = 'badge badge-success';
                    badgeText = 'Excellent';
                } else if (accuracy < 100) {
                    // Precision moyenne
                    iconClass = 'fas fa-map-marker-alt text-warning';
                    badgeClass = 'badge badge-warning';
                    badgeText = 'Moyen';
                } else {
                    // Mauvaise precision
                    iconClass = 'fas fa-map-marker-alt text-error';
                    badgeClass = 'badge badge-error';
                    badgeText = 'Faible';
                }

                icon.className = iconClass;
                badge.className = badgeClass;
                badge.textContent = badgeText + ' (' + accuracy.toFixed(0) + 'm)';
                badge.style.display = 'inline-block';

                // Mettre a jour le texte avec le village si disponible
                if (villageName && distanceKm !== null) {
                    text.innerHTML = '<strong>' + villageName + '</strong> (' + distanceKm.toFixed(1) + ' km)';
                } else {
                    text.innerHTML = 'Position GPS acquise';
                }
            }
        }

        // Helper pour recuperer le CSRF token
        function getCookie(name) {
            let cookieValue = null;
            if (document.cookie && document.cookie !== '') {
                const cookies = document.cookie.split(';');
                for (let i = 0; i < cookies.length; i++) {
                    const cookie = cookies[i].trim();
                    if (cookie.substring(0, name.length + 1) === (name + '=')) {
                        cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                        break;
                    }
                }
            }
            return cookieValue;
        }

        // Capturer la position GPS automatiquement
        document.addEventListener('DOMContentLoaded', function () {
            // Capture initiale au chargement
            setTimeout(captureGPSPosition, 2000);

            // Capturer toutes les heures (3600000 ms = 1 heure)
            setInterval(captureGPSPosition, 3600000);
        });
    </script>

    <script>
        (function () {
            const STORAGE_KEY = 'hydria.calculator.memory.v1';
            const CASH_BOOKS_KEY = 'hydria.calculator.cashbooks.v1';
            const MAX_CALC_ROWS = 1000;
            const MAX_QUOTE_ROWS = 500;
            const MAX_TOTAL_ROWS = 500;
            const MAX_CASH_ROWS = 1000;
            const MAX_CASH_BOOKS = 200;

            const calcResultFormatter = new Intl.NumberFormat('fr-FR', {
                minimumFractionDigits: 0,
                maximumFractionDigits: 6
            });
            const moneyFormatter = new Intl.NumberFormat('fr-FR', {
                minimumFractionDigits: 2,
                maximumFractionDigits: 2
            });

            const calculatorState = {
                mode: 'calc',
                activeCalcRow: 0,
                calcRows: [],
                quoteRows: [],
                totalRows: [],
                cashRows: []
            };
            let cashBooksRegistry = {};

            function defaultCalcRow() {
                return { label: '', expr: '', result: null, error: '' };
            }

            function defaultQuoteRow() {
                return { designation: '', quantity: '', unitPrice: '', amount: 0 };
            }

            function defaultTotalRow() {
                return { designation: '', unitPrice: '', value: 0 };
            }

            function defaultCashRow() {
                return { label: '', entry: '', output: '', balance: 0, pointage: '' };
            }

            function escapeHtml(value) {
                return String(value ?? '')
                    .replace(/&/g, '&amp;')
                    .replace(/</g, '&lt;')
                    .replace(/>/g, '&gt;')
                    .replace(/"/g, '&quot;')
                    .replace(/'/g, '&#39;');
            }

            function parseNumericInput(value) {
                if (value === null || value === undefined) return null;
                const normalized = String(value).replace(/\s+/g, '').replace(',', '.');
                if (!normalized) return null;
                const parsed = Number(normalized);
                return Number.isFinite(parsed) ? parsed : null;
            }

            function formatResult(value) {
                if (!Number.isFinite(value)) return '-';
                return calcResultFormatter.format(value);
            }

            function formatMoney(value) {
                if (!Number.isFinite(value)) return '0,00 Ar';
                return moneyFormatter.format(value) + ' Ar';
            }

            function normalizeCashBookName(value) {
                const normalized = String(value ?? '').replace(/\s+/g, ' ').trim();
                if (!normalized) return '';
                return normalized.slice(0, 80);
            }

            function projectCashRow(row) {
                return {
                    label: typeof row.label === 'string' ? row.label : '',
                    entry: typeof row.entry === 'string' ? row.entry : '',
                    output: typeof row.output === 'string' ? row.output : '',
                    pointage: typeof row.pointage === 'string' ? row.pointage : ''
                };
            }

            function normalizeCashRows(rows) {
                if (!Array.isArray(rows)) return [defaultCashRow()];
                const normalized = rows.slice(0, MAX_CASH_ROWS).map((row) => ({
                    label: typeof row.label === 'string' ? row.label : '',
                    entry: typeof row.entry === 'string' ? row.entry : '',
                    output: typeof row.output === 'string' ? row.output : '',
                    balance: 0,
                    pointage: typeof row.pointage === 'string' ? row.pointage : ''
                }));
                return normalized.length ? normalized : [defaultCashRow()];
            }

            function loadCashBooksRegistry() {
                try {
                    const raw = localStorage.getItem(CASH_BOOKS_KEY);
                    if (!raw) {
                        cashBooksRegistry = {};
                        return;
                    }
                    const parsed = JSON.parse(raw);
                    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
                        cashBooksRegistry = {};
                        return;
                    }

                    const entries = Object.entries(parsed).slice(0, MAX_CASH_BOOKS);
                    cashBooksRegistry = entries.reduce((acc, [name, item]) => {
                        const normalizedName = normalizeCashBookName(name);
                        if (!normalizedName) return acc;
                        if (!item || typeof item !== 'object') return acc;
                        acc[normalizedName] = {
                            rows: normalizeCashRows(item.rows).map(projectCashRow),
                            updatedAt: typeof item.updatedAt === 'string' ? item.updatedAt : new Date().toISOString()
                        };
                        return acc;
                    }, {});
                } catch (error) {
                    cashBooksRegistry = {};
                }
            }

            function persistCashBooksRegistry() {
                try {
                    localStorage.setItem(CASH_BOOKS_KEY, JSON.stringify(cashBooksRegistry));
                } catch (error) {
                    // Silencieux: quota localStorage ou mode prive
                }
            }

            function formatCashBookDate(value) {
                const date = new Date(value);
                if (Number.isNaN(date.getTime())) return '';
                return date.toLocaleString('fr-FR', {
                    day: '2-digit',
                    month: '2-digit',
                    year: '2-digit',
                    hour: '2-digit',
                    minute: '2-digit'
                });
            }

            function updateCashBookSelector(selectedName) {
                const select = document.getElementById('cashBookSelect');
                if (!select) return;

                const fallbackSelected = typeof selectedName === 'string' ? selectedName : select.value;
                const names = Object.keys(cashBooksRegistry).sort((a, b) => a.localeCompare(b, 'fr'));
                const options = ['<option value="">Cahiers enregistres</option>'];

                names.forEach((name) => {
                    const meta = cashBooksRegistry[name];
                    const dateLabel = meta ? formatCashBookDate(meta.updatedAt) : '';
                    const text = dateLabel ? `${name} (${dateLabel})` : name;
                    options.push(`<option value="${escapeHtml(name)}">${escapeHtml(text)}</option>`);
                });

                select.innerHTML = options.join('');
                if (fallbackSelected && cashBooksRegistry[fallbackSelected]) {
                    select.value = fallbackSelected;
                }
            }

            function onCashBookSelectionChange(value) {
                const input = document.getElementById('cashBookNameInput');
                const name = normalizeCashBookName(value);
                if (!input || !name) return;
                input.value = name;
            }

            function saveCurrentCashBook() {
                const input = document.getElementById('cashBookNameInput');
                const prompted = input ? input.value : '';
                const name = normalizeCashBookName(prompted || prompt('Nom du cahier de caisse :', ''));
                if (!name) {
                    alert('Veuillez saisir un nom de cahier.');
                    return;
                }

                const exists = Boolean(cashBooksRegistry[name]);
                if (exists && !confirm('Un cahier avec ce nom existe deja. Ecraser ?')) return;

                if (!exists && Object.keys(cashBooksRegistry).length >= MAX_CASH_BOOKS) {
                    alert('Limite atteinte: ' + MAX_CASH_BOOKS + ' cahiers maximum.');
                    return;
                }

                cashBooksRegistry[name] = {
                    rows: calculatorState.cashRows.map(projectCashRow),
                    updatedAt: new Date().toISOString()
                };
                persistCashBooksRegistry();
                updateCashBookSelector(name);
                if (input) input.value = name;
            }

            function loadSelectedCashBook() {
                const select = document.getElementById('cashBookSelect');
                const input = document.getElementById('cashBookNameInput');
                const selectedName = normalizeCashBookName(select ? select.value : '');
                const inputName = normalizeCashBookName(input ? input.value : '');
                const name = selectedName || inputName;
                if (!name) {
                    alert('Choisissez un cahier a charger.');
                    return;
                }
                const item = cashBooksRegistry[name];
                if (!item) {
                    alert('Cahier introuvable.');
                    return;
                }

                calculatorState.cashRows = normalizeCashRows(item.rows);
                renderCashRows();
                persistCalculatorState();
                updateCashBookSelector(name);
                if (input) input.value = name;
            }

            function deleteSelectedCashBook() {
                const select = document.getElementById('cashBookSelect');
                const input = document.getElementById('cashBookNameInput');
                const selectedName = normalizeCashBookName(select ? select.value : '');
                const inputName = normalizeCashBookName(input ? input.value : '');
                const name = selectedName || inputName;
                if (!name) {
                    alert('Choisissez un cahier a supprimer.');
                    return;
                }
                if (!cashBooksRegistry[name]) {
                    alert('Cahier introuvable.');
                    return;
                }
                if (!confirm('Supprimer le cahier "' + name + '" ?')) return;

                delete cashBooksRegistry[name];
                persistCashBooksRegistry();
                updateCashBookSelector('');
                if (input && input.value === name) input.value = '';
            }

            function ensureStateDefaults() {
                if (!Array.isArray(calculatorState.calcRows)) calculatorState.calcRows = [];
                if (!Array.isArray(calculatorState.quoteRows)) calculatorState.quoteRows = [];
                if (!Array.isArray(calculatorState.totalRows)) calculatorState.totalRows = [];
                if (!Array.isArray(calculatorState.cashRows)) calculatorState.cashRows = [];

                calculatorState.calcRows = calculatorState.calcRows.slice(0, MAX_CALC_ROWS).map((row) => ({
                    label: typeof row.label === 'string' ? row.label : '',
                    expr: typeof row.expr === 'string' ? row.expr : '',
                    result: Number.isFinite(Number(row.result)) ? Number(row.result) : null,
                    error: typeof row.error === 'string' ? row.error : ''
                }));
                calculatorState.quoteRows = calculatorState.quoteRows.slice(0, MAX_QUOTE_ROWS).map((row) => ({
                    designation: typeof row.designation === 'string' ? row.designation : '',
                    quantity: typeof row.quantity === 'string' ? row.quantity : '',
                    unitPrice: typeof row.unitPrice === 'string' ? row.unitPrice : '',
                    amount: Number.isFinite(Number(row.amount)) ? Number(row.amount) : 0
                }));
                calculatorState.totalRows = calculatorState.totalRows.slice(0, MAX_TOTAL_ROWS).map((row) => ({
                    designation: typeof row.designation === 'string' ? row.designation : '',
                    unitPrice: typeof row.unitPrice === 'string' ? row.unitPrice : '',
                    value: Number.isFinite(Number(row.value)) ? Number(row.value) : 0
                }));
                calculatorState.cashRows = calculatorState.cashRows.slice(0, MAX_CASH_ROWS).map((row) => ({
                    label: typeof row.label === 'string' ? row.label : '',
                    entry: typeof row.entry === 'string' ? row.entry : '',
                    output: typeof row.output === 'string' ? row.output : '',
                    balance: Number.isFinite(Number(row.balance)) ? Number(row.balance) : 0,
                    pointage: typeof row.pointage === 'string' ? row.pointage : ''
                }));

                if (!calculatorState.calcRows.length) calculatorState.calcRows.push(defaultCalcRow());
                if (!calculatorState.quoteRows.length) calculatorState.quoteRows.push(defaultQuoteRow());
                if (!calculatorState.totalRows.length) calculatorState.totalRows.push(defaultTotalRow());
                if (!calculatorState.cashRows.length) calculatorState.cashRows.push(defaultCashRow());

                if (!Number.isInteger(calculatorState.activeCalcRow)) calculatorState.activeCalcRow = 0;
                if (calculatorState.activeCalcRow < 0) calculatorState.activeCalcRow = 0;
                if (calculatorState.activeCalcRow >= calculatorState.calcRows.length) {
                    calculatorState.activeCalcRow = calculatorState.calcRows.length - 1;
                }

                calculatorState.mode = ['calc', 'quote', 'total', 'cash'].includes(calculatorState.mode) ? calculatorState.mode : 'calc';
            }

            function loadCalculatorState() {
                try {
                    const raw = localStorage.getItem(STORAGE_KEY);
                    if (!raw) {
                        ensureStateDefaults();
                        return;
                    }
                    const parsed = JSON.parse(raw);
                    if (parsed && typeof parsed === 'object') {
                        calculatorState.mode = parsed.mode;
                        calculatorState.activeCalcRow = parsed.activeCalcRow;
                        calculatorState.calcRows = parsed.calcRows;
                        calculatorState.quoteRows = parsed.quoteRows;
                        calculatorState.totalRows = parsed.totalRows;
                        calculatorState.cashRows = parsed.cashRows;
                    }
                } catch (error) {
                    console.warn('Impossible de charger la memoire calculatrice:', error);
                }
                ensureStateDefaults();
            }

            function persistCalculatorState() {
                try {
                    localStorage.setItem(STORAGE_KEY, JSON.stringify(calculatorState));
                } catch (error) {
                    // Silencieux: quota localStorage ou mode prive
                }
            }

            function evaluateCalcExpression(expression, rowIndex) {
                let expr = String(expression ?? '').trim();
                if (!expr) return { value: null, error: '' };

                if (expr.startsWith('=')) expr = expr.substring(1);
                expr = expr.replace(/,/g, '.');
                expr = expr.replace(/(\d+(?:\.\d+)?)\s*%/g, '($1/100)');

                try {
                    expr = expr.replace(/L(\d+)/gi, function (_, lineText) {
                        const lineNumber = Number(lineText);
                        const lineIndex = lineNumber - 1;
                        if (!Number.isInteger(lineNumber) || lineIndex < 0) {
                            throw new Error('Reference de ligne invalide');
                        }
                        if (lineIndex >= rowIndex) {
                            throw new Error('Reference vers une ligne future (L' + lineNumber + ')');
                        }
                        const refValue = calculatorState.calcRows[lineIndex]?.result;
                        if (!Number.isFinite(refValue)) {
                            throw new Error('Ligne L' + lineNumber + ' non calculee');
                        }
                        return '(' + refValue + ')';
                    });

                    if (!/^[0-9+\-*/().\s]+$/.test(expr)) {
                        throw new Error('Caracteres non autorises');
                    }

                    const result = Function('"use strict"; return (' + expr + ');')();
                    if (!Number.isFinite(result)) {
                        throw new Error('Resultat non numerique');
                    }
                    return { value: Number(result), error: '' };
                } catch (error) {
                    return {
                        value: null,
                        error: error && error.message ? error.message : 'Expression invalide'
                    };
                }
            }

            function recalculateCalculatorLines() {
                ensureStateDefaults();
                calculatorState.calcRows.forEach((row, index) => {
                    const output = evaluateCalcExpression(row.expr, index);
                    row.result = output.value;
                    row.error = output.error;
                });
                refreshCalcResults();
                persistCalculatorState();
            }

            function recalculateQuoteRows() {
                ensureStateDefaults();
                calculatorState.quoteRows.forEach((row) => {
                    const qty = parseNumericInput(row.quantity);
                    const unit = parseNumericInput(row.unitPrice);
                    row.amount = Number.isFinite(qty) && Number.isFinite(unit) ? qty * unit : 0;
                });
                refreshQuoteAmounts();
                persistCalculatorState();
            }

            function recalculateTotalRows() {
                ensureStateDefaults();
                calculatorState.totalRows.forEach((row) => {
                    const unit = parseNumericInput(row.unitPrice);
                    row.value = Number.isFinite(unit) ? unit : 0;
                });
                refreshTotalAmounts();
                persistCalculatorState();
            }

            function recalculateCashRows() {
                ensureStateDefaults();
                let runningBalance = 0;
                calculatorState.cashRows.forEach((row) => {
                    const entry = parseNumericInput(row.entry);
                    const output = parseNumericInput(row.output);
                    runningBalance += (Number.isFinite(entry) ? entry : 0) - (Number.isFinite(output) ? output : 0);
                    row.balance = runningBalance;
                });
                refreshCashAmounts();
                persistCalculatorState();
            }

            function refreshCalcResults() {
                const memoryInfo = document.getElementById('calcMemoryInfo');
                const activeInfo = document.getElementById('calcActiveLineInfo');
                if (memoryInfo) {
                    memoryInfo.textContent = calculatorState.calcRows.length + ' ligne(s) memorisees';
                }
                if (activeInfo) {
                    activeInfo.textContent = 'Ligne active: L' + (calculatorState.activeCalcRow + 1);
                }

                calculatorState.calcRows.forEach((row, index) => {
                    const resultEl = document.getElementById('calc-result-' + index);
                    const rowEl = document.getElementById('calc-row-' + index);
                    if (rowEl) {
                        rowEl.classList.toggle('hydria-calculator-row-active', index === calculatorState.activeCalcRow);
                    }
                    if (!resultEl) return;

                    if (row.error) {
                        resultEl.className = 'hydria-calculator-result text-error text-xs';
                        resultEl.textContent = row.error;
                    } else if (Number.isFinite(row.result)) {
                        resultEl.className = 'hydria-calculator-result text-success';
                        resultEl.textContent = formatResult(row.result);
                    } else {
                        resultEl.className = 'hydria-calculator-result text-base-content/40';
                        resultEl.textContent = '-';
                    }
                });
            }

            function refreshQuoteAmounts() {
                let total = 0;
                calculatorState.quoteRows.forEach((row, index) => {
                    const amount = Number.isFinite(row.amount) ? row.amount : 0;
                    total += amount;
                    const amountEl = document.getElementById('quote-amount-' + index);
                    if (amountEl) amountEl.textContent = formatMoney(amount);
                });

                const totalEl = document.getElementById('quoteGrandTotal');
                if (totalEl) totalEl.textContent = formatMoney(total);

                const memoryInfo = document.getElementById('quoteMemoryInfo');
                if (memoryInfo) memoryInfo.textContent = calculatorState.quoteRows.length + ' ligne(s) devis';
            }

            function refreshTotalAmounts() {
                let total = 0;
                calculatorState.totalRows.forEach((row) => {
                    const value = Number.isFinite(row.value) ? row.value : 0;
                    total += value;
                });

                const totalEl = document.getElementById('totalGrandTotal');
                if (totalEl) totalEl.textContent = formatMoney(total);

                const memoryInfo = document.getElementById('totalMemoryInfo');
                if (memoryInfo) memoryInfo.textContent = calculatorState.totalRows.length + ' ligne(s) total';
            }

            function refreshCashAmounts() {
                let finalBalance = 0;
                calculatorState.cashRows.forEach((row, index) => {
                    const balance = Number.isFinite(row.balance) ? row.balance : 0;
                    finalBalance = balance;
                    const balanceEl = document.getElementById('cash-balance-' + index);
                    if (balanceEl) balanceEl.textContent = formatMoney(balance);
                });

                const totalEl = document.getElementById('cashGrandBalance');
                if (totalEl) totalEl.textContent = formatMoney(finalBalance);

                const memoryInfo = document.getElementById('cashMemoryInfo');
                if (memoryInfo) memoryInfo.textContent = calculatorState.cashRows.length + ' ligne(s) caisse';
            }

            function renderCalcRows() {
                const tbody = document.getElementById('calcRowsBody');
                if (!tbody) return;

                const html = calculatorState.calcRows.map((row, index) => {
                    const canDelete = calculatorState.calcRows.length > 1;
                    return `
                        <tr id="calc-row-${index}">
                            <td class="w-20">
                                <button type="button" class="btn btn-ghost btn-xs" onclick="setCalcActiveRow(${index})">L${index + 1}</button>
                            </td>
                            <td class="min-w-[11rem]">
                                <input id="calc-label-${index}" type="text" class="input input-bordered input-xs w-full"
                                    value="${escapeHtml(row.label)}"
                                    placeholder="Libelle"
                                    onfocus="setCalcActiveRow(${index})"
                                    oninput="updateCalcLabel(${index}, this.value)">
                            </td>
                            <td class="min-w-[15rem]">
                                <input id="calc-expr-${index}" type="text" class="input input-bordered input-xs w-full"
                                    value="${escapeHtml(row.expr)}"
                                    placeholder="Ex: (12500*3)+L2"
                                    onfocus="setCalcActiveRow(${index})"
                                    oninput="updateCalcExpr(${index}, this.value)"
                                    onkeydown="handleCalcKeyDown(event, ${index})">
                            </td>
                            <td class="min-w-[10rem]">
                                <div id="calc-result-${index}" class="hydria-calculator-result">-</div>
                            </td>
                            <td class="text-right w-28">
                                <div class="flex justify-end gap-1">
                                    <button type="button" class="btn btn-ghost btn-xs" title="Inserer reference L${index + 1}" onclick="insertCalcReference(${index})">
                                        Ref
                                    </button>
                                    <button type="button" class="btn btn-ghost btn-xs ${canDelete ? '' : 'btn-disabled'}" ${canDelete ? '' : 'disabled'}
                                        onclick="deleteCalcLine(${index})" title="Supprimer ligne">
                                        <i class="fas fa-trash-alt"></i>
                                    </button>
                                </div>
                            </td>
                        </tr>
                    `;
                }).join('');

                tbody.innerHTML = html;
                recalculateCalculatorLines();
            }

            function renderQuoteRows() {
                const tbody = document.getElementById('quoteRowsBody');
                if (!tbody) return;

                const html = calculatorState.quoteRows.map((row, index) => {
                    const canDelete = calculatorState.quoteRows.length > 1;
                    return `
                        <tr id="quote-row-${index}">
                            <td class="w-12">
                                <span class="badge badge-ghost badge-sm">${index + 1}</span>
                            </td>
                            <td class="min-w-[14rem]">
                                <input id="quote-designation-${index}" type="text" class="input input-bordered input-xs w-full"
                                    value="${escapeHtml(row.designation)}"
                                    placeholder="Designation"
                                    oninput="updateQuoteField(${index}, 'designation', this.value)"
                                    onkeydown="handleQuoteKeyDown(event, ${index}, 'designation')">
                            </td>
                            <td class="min-w-[8rem]">
                                <input id="quote-quantity-${index}" type="text" class="input input-bordered input-xs w-full text-right"
                                    value="${escapeHtml(row.quantity)}"
                                    placeholder="0"
                                    oninput="updateQuoteField(${index}, 'quantity', this.value)"
                                    onkeydown="handleQuoteKeyDown(event, ${index}, 'quantity')">
                            </td>
                            <td class="min-w-[9rem]">
                                <input id="quote-unitPrice-${index}" type="text" class="input input-bordered input-xs w-full text-right"
                                    value="${escapeHtml(row.unitPrice)}"
                                    placeholder="0"
                                    oninput="updateQuoteField(${index}, 'unitPrice', this.value)"
                                    onkeydown="handleQuoteKeyDown(event, ${index}, 'unitPrice')">
                            </td>
                            <td class="min-w-[9rem] text-right">
                                <span id="quote-amount-${index}" class="font-semibold">0,00 Ar</span>
                            </td>
                            <td class="text-right w-20">
                                <button type="button" class="btn btn-ghost btn-xs ${canDelete ? '' : 'btn-disabled'}" ${canDelete ? '' : 'disabled'}
                                    onclick="deleteQuoteRow(${index})" title="Supprimer ligne">
                                    <i class="fas fa-trash-alt"></i>
                                </button>
                            </td>
                        </tr>
                    `;
                }).join('');

                tbody.innerHTML = html;
                recalculateQuoteRows();
            }

            function renderTotalRows() {
                const tbody = document.getElementById('totalRowsBody');
                if (!tbody) return;

                const html = calculatorState.totalRows.map((row, index) => {
                    const canDelete = calculatorState.totalRows.length > 1;
                    return `
                        <tr id="total-row-${index}">
                            <td class="w-12">
                                <span class="badge badge-ghost badge-sm">${index + 1}</span>
                            </td>
                            <td class="min-w-[14rem]">
                                <input id="total-designation-${index}" type="text" class="input input-bordered input-xs w-full"
                                    value="${escapeHtml(row.designation)}"
                                    placeholder="Designation"
                                    oninput="updateTotalField(${index}, 'designation', this.value)"
                                    onkeydown="handleTotalKeyDown(event, ${index}, 'designation')">
                            </td>
                            <td class="min-w-[9rem]">
                                <input id="total-unitPrice-${index}" type="text" class="input input-bordered input-xs w-full text-right"
                                    value="${escapeHtml(row.unitPrice)}"
                                    placeholder="0"
                                    oninput="updateTotalField(${index}, 'unitPrice', this.value)"
                                    onkeydown="handleTotalKeyDown(event, ${index}, 'unitPrice')">
                            </td>
                            <td class="text-right w-20">
                                <button type="button" class="btn btn-ghost btn-xs ${canDelete ? '' : 'btn-disabled'}" ${canDelete ? '' : 'disabled'}
                                    onclick="deleteTotalRow(${index})" title="Supprimer ligne">
                                    <i class="fas fa-trash-alt"></i>
                                </button>
                            </td>
                        </tr>
                    `;
                }).join('');

                tbody.innerHTML = html;
                recalculateTotalRows();
            }

            function renderCashRows() {
                const tbody = document.getElementById('cashRowsBody');
                if (!tbody) return;

                const html = calculatorState.cashRows.map((row, index) => {
                    const canDelete = calculatorState.cashRows.length > 1;
                    return `
                        <tr id="cash-row-${index}">
                            <td class="w-12">
                                <span class="badge badge-ghost badge-sm">${index + 1}</span>
                            </td>
                            <td class="min-w-[12rem]">
                                <input id="cash-label-${index}" type="text" class="input input-bordered input-xs w-full"
                                    value="${escapeHtml(row.label)}"
                                    placeholder="Libelle (optionnel)"
                                    oninput="updateCashField(${index}, 'label', this.value)"
                                    onkeydown="handleCashKeyDown(event, ${index}, 'label')">
                            </td>
                            <td class="min-w-[8rem]">
                                <input id="cash-entry-${index}" type="text" class="input input-bordered input-xs w-full text-right"
                                    value="${escapeHtml(row.entry)}"
                                    placeholder="0"
                                    oninput="updateCashField(${index}, 'entry', this.value)"
                                    onkeydown="handleCashKeyDown(event, ${index}, 'entry')">
                            </td>
                            <td class="min-w-[8rem]">
                                <input id="cash-output-${index}" type="text" class="input input-bordered input-xs w-full text-right"
                                    value="${escapeHtml(row.output)}"
                                    placeholder="0"
                                    oninput="updateCashField(${index}, 'output', this.value)"
                                    onkeydown="handleCashKeyDown(event, ${index}, 'output')">
                            </td>
                            <td class="min-w-[10rem] text-right">
                                <span id="cash-balance-${index}" class="font-semibold">0,00 Ar</span>
                            </td>
                            <td class="min-w-[12rem]">
                                <input id="cash-pointage-${index}" type="text" class="input input-bordered input-xs w-full"
                                    value="${escapeHtml(row.pointage)}"
                                    placeholder="Ex: FAC-00125"
                                    oninput="updateCashField(${index}, 'pointage', this.value)"
                                    onkeydown="handleCashKeyDown(event, ${index}, 'pointage')">
                            </td>
                            <td class="text-right w-20">
                                <button type="button" class="btn btn-ghost btn-xs ${canDelete ? '' : 'btn-disabled'}" ${canDelete ? '' : 'disabled'}
                                    onclick="deleteCashRow(${index})" title="Supprimer ligne">
                                    <i class="fas fa-trash-alt"></i>
                                </button>
                            </td>
                        </tr>
                    `;
                }).join('');

                tbody.innerHTML = html;
                recalculateCashRows();
            }

            function setCalcActiveRow(index) {
                if (!Number.isInteger(index)) return;
                if (index < 0 || index >= calculatorState.calcRows.length) return;
                calculatorState.activeCalcRow = index;
                refreshCalcResults();
                persistCalculatorState();
            }

            function addCalcLine() {
                if (calculatorState.calcRows.length >= MAX_CALC_ROWS) {
                    alert('Limite atteinte: ' + MAX_CALC_ROWS + ' lignes max.');
                    return;
                }
                calculatorState.calcRows.push(defaultCalcRow());
                calculatorState.activeCalcRow = calculatorState.calcRows.length - 1;
                renderCalcRows();
                persistCalculatorState();

                const input = document.getElementById('calc-expr-' + calculatorState.activeCalcRow);
                if (input) input.focus();
            }

            function deleteCalcLine(index) {
                if (calculatorState.calcRows.length <= 1) {
                    calculatorState.calcRows[0] = defaultCalcRow();
                    calculatorState.activeCalcRow = 0;
                    renderCalcRows();
                    persistCalculatorState();
                    return;
                }
                calculatorState.calcRows.splice(index, 1);
                if (calculatorState.activeCalcRow >= calculatorState.calcRows.length) {
                    calculatorState.activeCalcRow = calculatorState.calcRows.length - 1;
                }
                renderCalcRows();
                persistCalculatorState();
            }

            function clearCalcLines() {
                if (!confirm('Vider toutes les lignes de calcul ?')) return;
                calculatorState.calcRows = [defaultCalcRow()];
                calculatorState.activeCalcRow = 0;
                renderCalcRows();
                persistCalculatorState();
            }

            function updateCalcLabel(index, value) {
                const row = calculatorState.calcRows[index];
                if (!row) return;
                row.label = value;
                persistCalculatorState();
            }

            function updateCalcExpr(index, value) {
                const row = calculatorState.calcRows[index];
                if (!row) return;
                row.expr = value;
                calculatorState.activeCalcRow = index;
                recalculateCalculatorLines();
            }

            function moveToCalcLine(targetIndex, createIfMissing) {
                let nextIndex = targetIndex;
                if (createIfMissing && nextIndex >= calculatorState.calcRows.length) {
                    if (calculatorState.calcRows.length >= MAX_CALC_ROWS) return;
                    calculatorState.calcRows.push(defaultCalcRow());
                    renderCalcRows();
                }
                if (nextIndex < 0) nextIndex = 0;
                if (nextIndex >= calculatorState.calcRows.length) {
                    nextIndex = calculatorState.calcRows.length - 1;
                }
                setCalcActiveRow(nextIndex);
                const input = document.getElementById('calc-expr-' + nextIndex);
                if (input) {
                    input.focus();
                    input.select();
                }
            }

            function handleCalcKeyDown(event, index) {
                if (event.key === 'Enter') {
                    event.preventDefault();
                    moveToCalcLine(index + 1, true);
                    return;
                }
                if (event.ctrlKey && event.key === 'ArrowUp') {
                    event.preventDefault();
                    moveToCalcLine(index - 1, false);
                    return;
                }
                if (event.ctrlKey && event.key === 'ArrowDown') {
                    event.preventDefault();
                    moveToCalcLine(index + 1, false);
                }
            }

            function insertCalcReference(fromIndex) {
                if (!Number.isInteger(fromIndex)) return;
                if (fromIndex < 0 || fromIndex >= calculatorState.calcRows.length) return;

                let targetIndex = calculatorState.activeCalcRow;
                if (targetIndex <= fromIndex) {
                    targetIndex = fromIndex + 1;
                    while (targetIndex >= calculatorState.calcRows.length && calculatorState.calcRows.length < MAX_CALC_ROWS) {
                        calculatorState.calcRows.push(defaultCalcRow());
                    }
                    renderCalcRows();
                }

                if (targetIndex >= calculatorState.calcRows.length) return;
                calculatorState.activeCalcRow = targetIndex;

                const token = 'L' + (fromIndex + 1);
                const row = calculatorState.calcRows[targetIndex];
                const currentExpr = row.expr || '';
                const trimmed = currentExpr.trim();
                const needJoin = trimmed.length > 0 && /[0-9).]$/.test(trimmed);
                row.expr = currentExpr + (needJoin ? ' + ' : '') + token;

                const input = document.getElementById('calc-expr-' + targetIndex);
                if (input) {
                    input.value = row.expr;
                    input.focus();
                    const cursor = input.value.length;
                    input.setSelectionRange(cursor, cursor);
                }

                recalculateCalculatorLines();
            }

            function addQuoteRow() {
                if (calculatorState.quoteRows.length >= MAX_QUOTE_ROWS) {
                    alert('Limite atteinte: ' + MAX_QUOTE_ROWS + ' lignes devis max.');
                    return;
                }
                calculatorState.quoteRows.push(defaultQuoteRow());
                renderQuoteRows();
                persistCalculatorState();

                const index = calculatorState.quoteRows.length - 1;
                const input = document.getElementById('quote-designation-' + index);
                if (input) input.focus();
            }

            function deleteQuoteRow(index) {
                if (calculatorState.quoteRows.length <= 1) {
                    calculatorState.quoteRows[0] = defaultQuoteRow();
                    renderQuoteRows();
                    persistCalculatorState();
                    return;
                }
                calculatorState.quoteRows.splice(index, 1);
                renderQuoteRows();
                persistCalculatorState();
            }

            function clearQuoteRows() {
                if (!confirm('Vider toutes les lignes du devis ?')) return;
                calculatorState.quoteRows = [defaultQuoteRow()];
                renderQuoteRows();
                persistCalculatorState();
            }

            function updateQuoteField(index, field, value) {
                const row = calculatorState.quoteRows[index];
                if (!row) return;
                row[field] = value;
                recalculateQuoteRows();
            }

            function handleQuoteKeyDown(event, index, field) {
                if (event.key !== 'Enter') return;
                event.preventDefault();

                const order = ['designation', 'quantity', 'unitPrice'];
                const position = order.indexOf(field);
                if (position === -1) return;

                if (position < order.length - 1) {
                    const nextField = order[position + 1];
                    const nextInput = document.getElementById('quote-' + nextField + '-' + index);
                    if (nextInput) nextInput.focus();
                    return;
                }

                if (index === calculatorState.quoteRows.length - 1) {
                    addQuoteRow();
                } else {
                    const nextDesignation = document.getElementById('quote-designation-' + (index + 1));
                    if (nextDesignation) nextDesignation.focus();
                }
            }

            function addTotalRow() {
                if (calculatorState.totalRows.length >= MAX_TOTAL_ROWS) {
                    alert('Limite atteinte: ' + MAX_TOTAL_ROWS + ' lignes total max.');
                    return;
                }
                calculatorState.totalRows.push(defaultTotalRow());
                renderTotalRows();
                persistCalculatorState();

                const index = calculatorState.totalRows.length - 1;
                const input = document.getElementById('total-designation-' + index);
                if (input) input.focus();
            }

            function deleteTotalRow(index) {
                if (calculatorState.totalRows.length <= 1) {
                    calculatorState.totalRows[0] = defaultTotalRow();
                    renderTotalRows();
                    persistCalculatorState();
                    return;
                }
                calculatorState.totalRows.splice(index, 1);
                renderTotalRows();
                persistCalculatorState();
            }

            function clearTotalRows() {
                if (!confirm('Vider toutes les lignes du mode total ?')) return;
                calculatorState.totalRows = [defaultTotalRow()];
                renderTotalRows();
                persistCalculatorState();
            }

            function updateTotalField(index, field, value) {
                const row = calculatorState.totalRows[index];
                if (!row) return;
                row[field] = value;
                recalculateTotalRows();
            }

            function handleTotalKeyDown(event, index, field) {
                if (event.key !== 'Enter') return;
                event.preventDefault();

                if (field === 'designation') {
                    const nextInput = document.getElementById('total-unitPrice-' + index);
                    if (nextInput) nextInput.focus();
                    return;
                }

                if (index === calculatorState.totalRows.length - 1) {
                    addTotalRow();
                } else {
                    const nextDesignation = document.getElementById('total-designation-' + (index + 1));
                    if (nextDesignation) nextDesignation.focus();
                }
            }

            function addCashRow() {
                if (calculatorState.cashRows.length >= MAX_CASH_ROWS) {
                    alert('Limite atteinte: ' + MAX_CASH_ROWS + ' lignes caisse max.');
                    return;
                }
                calculatorState.cashRows.push(defaultCashRow());
                renderCashRows();
                persistCalculatorState();

                const index = calculatorState.cashRows.length - 1;
                const input = document.getElementById('cash-label-' + index);
                if (input) input.focus();
            }

            function deleteCashRow(index) {
                if (calculatorState.cashRows.length <= 1) {
                    calculatorState.cashRows[0] = defaultCashRow();
                    renderCashRows();
                    persistCalculatorState();
                    return;
                }
                calculatorState.cashRows.splice(index, 1);
                renderCashRows();
                persistCalculatorState();
            }

            function clearCashRows() {
                if (!confirm('Vider toutes les lignes du cahier de caisse ?')) return;
                calculatorState.cashRows = [defaultCashRow()];
                renderCashRows();
                persistCalculatorState();
            }

            function updateCashField(index, field, value) {
                const row = calculatorState.cashRows[index];
                if (!row) return;
                row[field] = value;
                recalculateCashRows();
            }

            function handleCashKeyDown(event, index, field) {
                if (event.key !== 'Enter') return;
                event.preventDefault();

                const order = ['label', 'entry', 'output', 'pointage'];
                const position = order.indexOf(field);
                if (position === -1) return;

                if (position < order.length - 1) {
                    const nextField = order[position + 1];
                    const nextInput = document.getElementById('cash-' + nextField + '-' + index);
                    if (nextInput) nextInput.focus();
                    return;
                }

                if (index === calculatorState.cashRows.length - 1) {
                    addCashRow();
                } else {
                    const nextLabel = document.getElementById('cash-label-' + (index + 1));
                    if (nextLabel) nextLabel.focus();
                }
            }

            function switchCalculatorMode(mode) {
                calculatorState.mode = mode === 'quote' || mode === 'total' || mode === 'cash' ? mode : 'calc';
                const calcTab = document.getElementById('calculatorModeCalcTab');
                const quoteTab = document.getElementById('calculatorModeQuoteTab');
                const totalTab = document.getElementById('calculatorModeTotalTab');
                const cashTab = document.getElementById('calculatorModeCashTab');
                const calcPanel = document.getElementById('calculatorCalcPanel');
                const quotePanel = document.getElementById('calculatorQuotePanel');
                const totalPanel = document.getElementById('calculatorTotalPanel');
                const cashPanel = document.getElementById('calculatorCashPanel');

                if (calcTab) calcTab.classList.toggle('tab-active', calculatorState.mode === 'calc');
                if (quoteTab) quoteTab.classList.toggle('tab-active', calculatorState.mode === 'quote');
                if (totalTab) totalTab.classList.toggle('tab-active', calculatorState.mode === 'total');
                if (cashTab) cashTab.classList.toggle('tab-active', calculatorState.mode === 'cash');
                if (calcPanel) calcPanel.classList.toggle('hidden', calculatorState.mode !== 'calc');
                if (quotePanel) quotePanel.classList.toggle('hidden', calculatorState.mode !== 'quote');
                if (totalPanel) totalPanel.classList.toggle('hidden', calculatorState.mode !== 'total');
                if (cashPanel) cashPanel.classList.toggle('hidden', calculatorState.mode !== 'cash');

                persistCalculatorState();
            }

            function openCalculatorModal() {
                ensureStateDefaults();
                switchCalculatorMode(calculatorState.mode);
                renderCalcRows();
                renderQuoteRows();
                renderTotalRows();
                renderCashRows();
                updateCashBookSelector();

                const modal = document.getElementById('globalCalculatorModal');
                if (!modal) return;
                if (typeof modal.showModal === 'function') {
                    modal.showModal();
                } else {
                    modal.setAttribute('open', 'open');
                }

                const focusEl = calculatorState.mode === 'quote'
                    ? document.getElementById('quote-designation-0')
                    : calculatorState.mode === 'total'
                        ? document.getElementById('total-designation-0')
                        : calculatorState.mode === 'cash'
                            ? document.getElementById('cash-entry-0')
                        : document.getElementById('calc-expr-' + calculatorState.activeCalcRow);
                if (focusEl) focusEl.focus();
            }

            function closeCalculatorModal() {
                const modal = document.getElementById('globalCalculatorModal');
                if (!modal) return;
                if (typeof modal.close === 'function') {
                    modal.close();
                } else {
                    modal.removeAttribute('open');
                }
            }

            function clearCalculatorStorage() {
                if (!confirm('Supprimer toute la memoire de la calculatrice (calculs, devis, total, cahier de caisse) ?')) return;
                localStorage.removeItem(STORAGE_KEY);
                localStorage.removeItem(CASH_BOOKS_KEY);
                calculatorState.mode = 'calc';
                calculatorState.activeCalcRow = 0;
                calculatorState.calcRows = [defaultCalcRow()];
                calculatorState.quoteRows = [defaultQuoteRow()];
                calculatorState.totalRows = [defaultTotalRow()];
                calculatorState.cashRows = [defaultCashRow()];
                cashBooksRegistry = {};
                switchCalculatorMode('calc');
                renderCalcRows();
                renderQuoteRows();
                renderTotalRows();
                renderCashRows();
                updateCashBookSelector();

                const input = document.getElementById('cashBookNameInput');
                if (input) input.value = '';
            }

            function initCalculator() {
                loadCalculatorState();
                loadCashBooksRegistry();
                switchCalculatorMode(calculatorState.mode);
                renderCalcRows();
                renderQuoteRows();
                renderTotalRows();
                renderCashRows();
                updateCashBookSelector();
            }

            document.addEventListener('DOMContentLoaded', initCalculator);
            document.addEventListener('keydown', function (event) {
                if (event.ctrlKey && event.shiftKey && event.key.toLowerCase() === 'k') {
                    event.preventDefault();
                    openCalculatorModal();
                }
            });

            window.openCalculatorModal = openCalculatorModal;
            window.closeCalculatorModal = closeCalculatorModal;
            window.switchCalculatorMode = switchCalculatorMode;
            window.recalculateCalculatorLines = recalculateCalculatorLines;
            window.setCalcActiveRow = setCalcActiveRow;
            window.addCalcLine = addCalcLine;
            window.deleteCalcLine = deleteCalcLine;
            window.clearCalcLines = clearCalcLines;
            window.updateCalcLabel = updateCalcLabel;
            window.updateCalcExpr = updateCalcExpr;
            window.handleCalcKeyDown = handleCalcKeyDown;
            window.insertCalcReference = insertCalcReference;
            window.addQuoteRow = addQuoteRow;
            window.deleteQuoteRow = deleteQuoteRow;
            window.clearQuoteRows = clearQuoteRows;
            window.updateQuoteField = updateQuoteField;
            window.handleQuoteKeyDown = handleQuoteKeyDown;
            window.recalculateTotalRows = recalculateTotalRows;
            window.addTotalRow = addTotalRow;
            window.deleteTotalRow = deleteTotalRow;
            window.clearTotalRows = clearTotalRows;
            window.updateTotalField = updateTotalField;
            window.handleTotalKeyDown = handleTotalKeyDown;
            window.recalculateCashRows = recalculateCashRows;
            window.addCashRow = addCashRow;
            window.deleteCashRow = deleteCashRow;
            window.clearCashRows = clearCashRows;
            window.updateCashField = updateCashField;
            window.handleCashKeyDown = handleCashKeyDown;
            window.onCashBookSelectionChange = onCashBookSelectionChange;
            window.saveCurrentCashBook = saveCurrentCashBook;
            window.loadSelectedCashBook = loadSelectedCashBook;
            window.deleteSelectedCashBook = deleteSelectedCashBook;
            window.clearCalculatorStorage = clearCalculatorStorage;
        })();
    </script>

    <!-- Modal de bienvenue - Planning 7 prochains jours -->
    <dialog id="modalBienvenue" class="modal">
        <div class="modal-box max-w-3xl">
            <h3 class="font-bold text-lg mb-4">
                <i class="fas fa-calendar-alt mr-2 text-primary"></i>
                Votre planning pour les 7 prochains jours
            </h3>

            <div id="bienvenueContent">
                <!-- Période -->
                <div class="alert alert-info mb-4">
                    <i class="fas fa-info-circle"></i>
                    <div>
                        <div class="font-semibold" id="bienvenueEmploye"></div>
                        <div class="text-sm" id="bienvenuePeriode"></div>
                    </div>
                </div>

                <!-- Tableau des plannings -->
                <div class="overflow-x-auto">
                    <table class="table table-zebra">
                        <thead>
                            <tr>
                                <th>Date</th>
                                <th>Jour</th>
                                <th>Activité</th>
                                <th>Remarque</th>
                            </tr>
                        </thead>
                        <tbody id="bienvenuePlanningsBody">
                            <!-- Lignes remplies par JavaScript -->
                        </tbody>
                    </table>
                </div>

                <!-- Message si aucun planning -->
                <div id="bienvenueAucunPlanning" class="alert alert-warning hidden">
                    <i class="fas fa-exclamation-triangle"></i>
                    <span>Aucun planning trouvé pour les 7 prochains jours</span>
                </div>

                <!-- Section Réparations à venir -->
                <div id="bienvenueReparationsSection" class="hidden mt-6">
                    <h4 class="font-bold text-md mb-3 flex items-center">
                        <i class="fas fa-wrench mr-2 text-error"></i>
                        Réparations à venir sur vos ouvrages
                        <span class="badge badge-error badge-sm ml-2" id="bienvenueNbReparations">0</span>
                    </h4>

                    <div class="overflow-x-auto">
                        <table class="table table-zebra table-sm">
                            <thead>
                                <tr>
                                    <th>Date prévue</th>
                                    <th>Ouvrage</th>
                                    <th>Titre</th>
                                    <th>Priorité</th>
                                    <th>Statut</th>
                                    <th>Assigné à</th>
                                </tr>
                            </thead>
                            <tbody id="bienvenueReparationsBody">
                                <!-- Lignes remplies par JavaScript -->
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>

            <div class="modal-action">
                <button onclick="document.getElementById('modalBienvenue').close()" class="btn btn-primary">
                    <i class="fas fa-check mr-2"></i>Compris
                </button>
            </div>
        </div>
        <form method="dialog" class="modal-backdrop">
            <button>Fermer</button>
        </form>
    </dialog>

    <script>
        // Fonction pour charger et afficher le modal de bienvenue
        async function afficherModalBienvenue() {
            // Verifier si le modal a deja ete affiche dans cette session
            if (sessionStorage.getItem('welcomeModalShown') === 'true') {
                return; // Ne pas afficher si deja montre
            }

            try {
                // Appeler l'API pour recuperer le planning des 7 prochains jours
                const response = await fetch('/plannings/api/planning-7-jours/');
                const data = await response.json();

                if (data.success && data.plannings && data.plannings.length > 0) {
                    // Remplir les informations d'en-tete
                    document.getElementById('bienvenueEmploye').textContent = data.employe_nom;
                    document.getElementById('bienvenuePeriode').textContent = `Periode: ${data.periode}`;

                    // Remplir le tableau
                    const tbody = document.getElementById('bienvenuePlanningsBody');
                    tbody.innerHTML = '';

                    data.plannings.forEach(planning => {
                        const tr = document.createElement('tr');
                        tr.innerHTML = `
                            <td>${planning.date_display}</td>
                            <td><strong>${planning.jour_semaine}</strong></td>
                            <td>
                                <span class="badge ${planning.badge_class}">
                                    ${planning.activite}
                                </span>
                            </td>
                            <td class="text-sm">${planning.remarque || '-'}</td>
                        `;
                        tbody.appendChild(tr);
                    });

                    // Masquer le message "aucun planning"
                    document.getElementById('bienvenueAucunPlanning').classList.add('hidden');

                    // Afficher les reparations a venir si presentes
                    if (data.reparations && data.reparations.length > 0) {
                        document.getElementById('bienvenueReparationsSection').classList.remove('hidden');
                        document.getElementById('bienvenueNbReparations').textContent = data.nb_reparations;

                        const tbodyReparations = document.getElementById('bienvenueReparationsBody');
                        tbodyReparations.innerHTML = '';

                        data.reparations.forEach(reparation => {
                            const trRep = document.createElement('tr');
                            trRep.innerHTML = `
                                <td><strong>${reparation.date_prevue}</strong></td>
                                <td class="text-sm">${reparation.ouvrage}</td>
                                <td class="text-sm">${reparation.titre}</td>
                                <td>
                                    <span class="badge ${reparation.priorite_badge} badge-sm">
                                        ${reparation.priorite}
                                    </span>
                                </td>
                                <td>
                                    <span class="badge ${reparation.statut_badge} badge-sm">
                                        ${reparation.statut}
                                    </span>
                                </td>
                                <td class="text-sm">${reparation.assigne_a}</td>
                            `;
                            tbodyReparations.appendChild(trRep);
                        });
                    }

                    // Ouvrir le modal
                    document.getElementById('modalBienvenue').showModal();

                    // Marquer comme affiche dans sessionStorage
                    sessionStorage.setItem('welcomeModalShown', 'true');
                } else if (data.success && data.plannings && data.plannings.length === 0) {
                    // Afficher message si aucun planning
                    document.getElementById('bienvenuePlanningsBody').innerHTML = '';
                    document.getElementById('bienvenueAucunPlanning').classList.remove('hidden');

                    // Ouvrir quand meme le modal
                    document.getElementById('modalBienvenue').showModal();
                    sessionStorage.setItem('welcomeModalShown', 'true');
                }
            } catch (error) {
                console.error('Erreur lors du chargement du planning de bienvenue:', error);
                // Ne pas afficher le modal en cas d'erreur
            }
        }

        // Afficher le modal au chargement de la page (seulement si utilisateur connecte)
        
        document.addEventListener('DOMContentLoaded', function () {
            // Petite temporisation pour laisser la page se charger completement
            setTimeout(afficherModalBienvenue, 500);
        });
        

        document.addEventListener('DOMContentLoaded', function () {
            const banner = document.getElementById('user-info-banner');
            const toggle = document.getElementById('toggle-user-info-banner');
            if (!banner || !toggle) return;
            const icon = toggle.querySelector('i');
            const storageKey = 'user_info_banner_collapsed';
            const stored = localStorage.getItem(storageKey);
            const initialCollapsed = stored === null ? true : stored === 'true';

            const setCollapsed = (collapsed) => {
                banner.classList.toggle('user-info-banner-collapsed', collapsed);
                if (icon) {
                    icon.classList.toggle('fa-chevron-down', collapsed);
                    icon.classList.toggle('fa-chevron-up', !collapsed);
                }
            };

            setCollapsed(initialCollapsed);

            toggle.addEventListener('click', function () {
                const isCollapsed = banner.classList.contains('user-info-banner-collapsed');
                setCollapsed(!isCollapsed);
                localStorage.setItem(storageKey, String(!isCollapsed));
            });
        });

        // Fallback global pour l'edition vehicule si le script de gestion ne charge pas
        window.openEditVehiculeModal = window.openEditVehiculeModal || async function (button) {
            try {
                const form = document.getElementById('formEditVehicule');
                const modal = document.getElementById('editVehiculeModal');
                if (!form || !modal) return;
                form.reset();
                const dataset = button && button.dataset ? button.dataset : {};
                const get = (selector) => form.querySelector(selector);
                const setVal = (selector, value) => {
                    const el = get(selector);
                    if (el) el.value = value || '';
                };

                document.getElementById('edit-vehicule-id').value = dataset.id || '';
                setVal('select[name="type_vehicule"]', dataset.type || 'moto');
                setVal('input[name="immatriculation"]', dataset.immatriculation || '');
                setVal('select[name="marque"]', dataset.marque || '');
                setVal('select[name="modele"]', dataset.modele || '');
                setVal('input[name="date_mise_circulation"]', dataset.date || '');
                setVal('input[name="numero_chassis"]', dataset.numeroChassis || '');
                setVal('select[name="couleur"]', dataset.couleur || '');
                setVal('input[name="annee_fabrication"]', dataset.anneeFabrication || '');

                const compteur = get('input[name="compteur_fonctionnel"]');
                if (compteur) compteur.checked = dataset.compteurFonctionnel === '1';
                const actif = get('input[name="actif"]');
                if (actif) actif.checked = dataset.actif === '1';
                const notes = get('textarea[name="notes"]');
                if (notes) notes.value = dataset.notes || '';

                modal.showModal();
            } catch (e) {
                console.error('openEditVehiculeModal fallback failed:', e);
            }
        };

        // Tracking de presence utilisateur (Temps reel)
        
        const currentUserPresenceTip = (
            'Herizo'
            + ' (HERIZO)'
            + ' | Poste: Directeur'
            + ' | Base: Vavatenina SK | Organisation: Soakoja'
            + ' | Vous (connecté)'
        );
        const currentUserInitial = 'H';

        const updateUserPresence = async () => {
            try {
                const response = await fetch('/systeme/api/presence/update/', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': 'GwWUOhG9urfuOHQr9drubGglC46op3Ro6DTuTDQgpsUz9puTXg8Cwtccmk6Byq7P'
                    },
                    body: JSON.stringify({ path: window.location.pathname + window.location.search })
                });
                
                const data = await response.json();
                if (data.success && data.active_users) {
                    const container = document.getElementById('user-presence-container');
                    const avatarsList = document.getElementById('user-presence-avatars');
                    const countSpan = document.getElementById('user-presence-count');
                    
                    if (!container || !avatarsList) return;
                    
                    if (data.active_users.length > 0) {
                        container.style.display = 'flex';
                        avatarsList.innerHTML = '';

                        // Afficher l'utilisateur connecte en premier avec ses infos au survol
                        const selfAvatar = document.createElement('div');
                        selfAvatar.className = 'tooltip tooltip-bottom';
                        selfAvatar.setAttribute('data-tip', currentUserPresenceTip);
                        selfAvatar.innerHTML = `
                            <div class="inline-block h-8 w-8 rounded-full ring-2 ring-success/70 bg-success text-success-content flex items-center justify-center text-xs font-medium uppercase border border-base-100 shadow-sm">
                                ${currentUserInitial || 'U'}
                            </div>
                        `;
                        avatarsList.appendChild(selfAvatar);
                        
                        const maxDisplay = 3;
                        data.active_users.slice(0, maxDisplay).forEach(u => {
                            const avatar = document.createElement('div');
                            avatar.className = 'tooltip tooltip-bottom';
                            avatar.setAttribute('data-tip', u.full_name + (u.surnom ? ' (' + u.surnom + ')' : ''));
                            avatar.innerHTML = `
                                <div class="inline-block h-8 w-8 rounded-full ring-2 ring-base-100 bg-primary text-primary-content flex items-center justify-center text-xs font-medium uppercase border border-base-300 shadow-sm">
                                    ${u.full_name.charAt(0)}
                                </div>
                            `;
                            avatarsList.appendChild(avatar);
                        });
                        
                        if (data.active_users.length > maxDisplay) {
                            const more = document.createElement('div');
                            more.className = 'inline-block h-8 w-8 rounded-full ring-2 ring-base-100 bg-base-300 text-base-content flex items-center justify-center text-xs font-medium border border-base-300 shadow-sm';
                            more.innerText = '+' + (data.active_users.length - maxDisplay);
                            avatarsList.appendChild(more);
                        }
                        
                        if (countSpan) {
                            countSpan.innerText = data.active_users.length + ' utilisateur' + (data.active_users.length > 1 ? 's' : '') + ' actif(s)';
                        }
                    } else {
                        container.style.display = 'none';
                    }
                }
            } catch (error) {
                // Silently fail
            }
        };

        const updateUnreadBadge = (count) => {
            const badge = document.getElementById('global-unread-badge');
            const badgeMobile = document.getElementById('global-unread-badge-mobile');
            const hasUnread = Number(count || 0) > 0;
            const label = Number(count || 0) > 99 ? '99+' : String(Number(count || 0));

            if (badge) {
                badge.textContent = label;
                badge.classList.toggle('hidden', !hasUnread);
            }
            if (badgeMobile) {
                badgeMobile.textContent = label;
                badgeMobile.classList.toggle('hidden', !hasUnread);
            }
        };

        const fetchUnreadCount = async () => {
            try {
                const response = await fetch('/conversations/unread-count/', { credentials: 'same-origin' });
                if (!response.ok) return;
                const data = await response.json();
                updateUnreadBadge(data.unread_count || 0);
            } catch (error) {
                // Silently fail
            }
        };

        document.addEventListener('DOMContentLoaded', () => {
            updateUserPresence();
            setInterval(updateUserPresence, 20000);
            fetchUnreadCount();
            setInterval(fetchUnreadCount, 10000);
        });
        
    </script>

    <script>
        // Force layout horizontal du menu desktop principal (anti-conflit CSS)
        document.addEventListener('DOMContentLoaded', function () {
            const menu = document.querySelector('.desktop-main-menu');
            if (!menu) return;

            menu.style.display = 'flex';
            menu.style.flexDirection = 'row';
            menu.style.flexWrap = 'wrap';
            menu.style.justifyContent = 'center';
            menu.style.alignItems = 'center';
            menu.style.gap = '0.3rem';
            menu.style.width = '100%';

            Array.from(menu.children).forEach((li) => {
                li.style.display = 'inline-flex';
                li.style.width = 'auto';
                li.style.flex = '0 0 auto';
                const first = li.firstElementChild;
                if (first) first.style.width = 'auto';
            });

            // Dropdown desktop exclusif: au survol d'un menu, fermer les autres.
            const desktopDropdowns = Array.from(menu.querySelectorAll('.dropdown.dropdown-hover'));
            if (!desktopDropdowns.length) return;

            const closeAllDesktopMenus = (except = null) => {
                desktopDropdowns.forEach((dropdown) => {
                    if (dropdown === except) return;
                    dropdown.classList.remove('dropdown-open');
                    dropdown.querySelectorAll('[tabindex="0"]').forEach((el) => el.blur());
                });
            };

            desktopDropdowns.forEach((dropdown) => {
                dropdown.addEventListener('mouseenter', () => {
                    closeAllDesktopMenus(dropdown);
                    dropdown.classList.add('dropdown-open');
                });

                dropdown.addEventListener('mouseleave', () => {
                    dropdown.classList.remove('dropdown-open');
                });

                const trigger = dropdown.querySelector('[role="button"]');
                if (trigger) {
                    trigger.addEventListener('focus', () => {
                        closeAllDesktopMenus(dropdown);
                        dropdown.classList.add('dropdown-open');
                    });
                }
            });

            menu.addEventListener('mouseleave', () => closeAllDesktopMenus());
            document.addEventListener('click', (event) => {
                if (!menu.contains(event.target)) closeAllDesktopMenus();
            });
        });
    