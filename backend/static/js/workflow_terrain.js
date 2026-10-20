// Gestion du workflow terrain - Sélection et traitement des livraisons/avances/paiements

console.log('workflow_terrain.js chargé');

// Fonction d'impression de ticket de caisse (globale)
window.imprimerTicket = function(data) {
    console.log('🖨️ imprimerTicket() démarrée avec data:', data);

    // Si un ticket est déjà en cours d'impression, ignorer
    if (window.ticketEnCours) {
        console.log('⚠️ Un ticket est déjà en cours d\'impression, ignorer cet appel');
        return;
    }
    window.ticketEnCours = true;

    // Si on a un QR Code, pré-charger l'image avant d'ouvrir la fenêtre
    if (data.numero_bon) {
        console.log('🔄 Pré-chargement du QR Code pour', data.numero_bon);
        const qrcodeUrl = `https://api.qrserver.com/v1/create-qr-code/?size=150x150&data=${encodeURIComponent(data.numero_bon)}`;
        const img = new Image();

        img.onload = function() {
            console.log('✅ QR Code pré-chargé, ouverture du ticket...');
            ouvrirTicket(data);

            // Retirer le message de chargement
            setTimeout(() => {
                document.getElementById('loading-ticket')?.remove();
            }, 500);

            window.ticketEnCours = false;
        };

        img.onerror = function() {
            console.warn('⚠️ Erreur de chargement du QR Code, ouverture sans QR Code...');
            ouvrirTicket(data);

            // Retirer le message de chargement
            setTimeout(() => {
                document.getElementById('loading-ticket')?.remove();
            }, 500);

            window.ticketEnCours = false;
        };

        img.src = qrcodeUrl;

        // Timeout de sécurité de 3 secondes (réduit de 5s)
        setTimeout(() => {
            if (window.ticketEnCours) {
                console.warn('⏰ Timeout QR Code, ouverture du ticket quand même...');
                ouvrirTicket(data);

                // Retirer le message de chargement
                setTimeout(() => {
                    document.getElementById('loading-ticket')?.remove();
                }, 500);

                window.ticketEnCours = false;
            }
        }, 3000);  // Réduit de 5000 à 3000
    } else {
        // Pas de QR Code, ouvrir directement
        ouvrirTicket(data);

        // Retirer le message de chargement
        setTimeout(() => {
            document.getElementById('loading-ticket')?.remove();
        }, 500);

        window.ticketEnCours = false;
    }
};

// Fonction auxiliaire pour ouvrir le ticket (séparée pour réutilisation)
function ouvrirTicket(data) {
    console.log('📄 Ouverture du ticket...');

    // Créer le HTML du ticket
    const ticketHtml = `
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <title>Ticket - ${data.type}</title>
            <style>
                @media print {
                    body { margin: 0; }
                    @page { size: 80mm auto; margin: 5mm; }
                }
                body {
                    font-family: 'Courier New', monospace;
                    font-size: 12px;
                    width: 80mm;
                    margin: 0 auto;
                    padding: 10px;
                }
                .header {
                    text-align: center;
                    border-bottom: 2px dashed #000;
                    padding-bottom: 10px;
                    margin-bottom: 10px;
                }
                .header img {
                    max-width: 60mm;
                    max-height: 30mm;
                    margin: 0 auto 5px;
                    display: block;
                }
                .header h1 {
                    margin: 0;
                    font-size: 16px;
                    font-weight: bold;
                }
                .header p {
                    margin: 2px 0;
                    font-size: 10px;
                }
                .content {
                    margin: 10px 0;
                }
                .line {
                    display: flex;
                    justify-content: space-between;
                    margin: 5px 0;
                }
                .label {
                    font-weight: bold;
                }
                .separator {
                    border-top: 1px dashed #000;
                    margin: 10px 0;
                }
                .total {
                    font-size: 14px;
                    font-weight: bold;
                    text-align: center;
                    margin: 10px 0;
                    padding: 5px;
                    border: 2px solid #000;
                }
                .footer {
                    text-align: center;
                    font-size: 10px;
                    margin-top: 15px;
                    border-top: 2px dashed #000;
                    padding-top: 10px;
                }
            </style>
        </head>
        <body>
            <div class="header">
                ${data.logo_url ? `<img src="${data.logo_url}" alt="${data.organisation || 'HYDRIA'}">` : `<h1>${data.organisation || 'HYDRIA'}</h1>`}
                ${data.nif ? `<p style="font-size: 9px;">NIF: ${data.nif}</p>` : ''}
                ${data.stat ? `<p style="font-size: 9px;">STAT: ${data.stat}</p>` : ''}
                ${data.base ? `<p style="font-size: 10px; font-weight: bold;">Base: ${data.base}</p>` : ''}
                ${(data.base_telephone || data.telephone) ? `<p style="font-size: 9px;">Tel: ${data.base_telephone || data.telephone}</p>` : ''}
                <p>================================</p>
            </div>

            <h2 style="text-align: center; font-size: 18px; font-weight: bold; margin: 10px 0;">
                ${data.isBonLivraison ? 'BON DE LIVRAISON' : data.isBonAvance ? "FACTURE" : data.isBonPaiement ? 'FAKTIORA' : 'FACTURE'}
            </h2>

            ${data.numero_bon ? `
            <p style="text-align: center; font-size: 12px; font-weight: bold; margin: 5px 0;">
                N° ${data.numero_bon}
            </p>
            <div style="text-align: center; margin: 10px 0;">
                <img src="https://api.qrserver.com/v1/create-qr-code/?size=150x150&data=${encodeURIComponent(data.numero_bon)}"
                     alt="QR Code ${data.numero_bon}"
                     style="width: 120px; height: 120px; margin: 0 auto; display: block; border: 2px solid #000; padding: 5px;">
                <p style="font-size: 9px; margin-top: 5px;">Scannez pour vérifier</p>
            </div>
            ` : ''}

            <div class="content">
                <div class="line">
                    <span class="label">${data.isBonPaiement ? 'Daty:' : 'Date:'}</span>
                    <span>${data.date}</span>
                </div>
                <div class="line">
                    <span class="label">${data.isBonPaiement ? 'Mpiasa:' : 'Agent:'}</span>
                    <span>${data.employe}</span>
                </div>
                <div class="line">
                    <span class="label">${data.isBonPaiement ? 'Fotodrafitrasa:' : 'Ouvrage:'}</span>
                    <span>${data.ouvrage}</span>
                </div>
                ${data.point_eau ? `
                <div class="line">
                    <span class="label">${data.isBonPaiement ? 'Toeram-patsakana:' : 'Point d\'eau:'}</span>
                    <span>${data.point_eau}</span>
                </div>
                ` : ''}
                ${data.nom_abonne && data.isBonPaiement ? `
                <div class="line">
                    <span class="label">RBF:</span>
                    <span>${data.nom_abonne}</span>
                </div>
                ` : ''}

                ${data.fournisseur ? `
                <div class="line">
                    <span class="label">RBF:</span>
                    <span>${data.fournisseur}</span>
                </div>
                ` : ''}
                ${data.compte ? `
                <div class="line">
                    <span class="label">Compte:</span>
                    <span>${data.compte}</span>
                </div>
                ` : ''}

                <div class="separator"></div>

                ${data.lignes && data.lignes.length > 0 ? `
                    <table style="width: 100%; font-size: ${data.isBonAvance || data.isBonPaiement ? '10px' : '12px'}; border-collapse: collapse; margin: 10px 0;">
                        <thead>
                            <tr style="border-bottom: 1px solid #000;">
                                <th style="text-align: left; padding: 5px;">${data.isBonPaiement ? 'Karazana' : 'Désignation'}</th>
                                <th style="text-align: center; padding: 5px; width: 60px;">${data.isBonPaiement ? 'Isa' : 'Qté'}</th>
                                ${data.isBonAvance || data.isBonPaiement ? `
                                    <th style="text-align: right; padding: 5px; width: 70px;">${data.isBonPaiement ? 'Vidin-tsirairay' : 'P.U.'}</th>
                                    <th style="text-align: right; padding: 5px; width: 80px;">${data.isBonPaiement ? 'Vidy' : 'Montant'}</th>
                                ` : ''}
                            </tr>
                        </thead>
                        <tbody>
                            ${data.lignes.map(ligne => `
                                <tr style="border-bottom: 1px dashed #ccc;">
                                    <td style="padding: 5px;">${ligne.designation}</td>
                                    <td style="text-align: center; padding: 5px;">${ligne.quantity || '-'}</td>
                                    ${data.isBonAvance || data.isBonPaiement ? `
                                        <td style="text-align: right; padding: 5px;">${(ligne.pu || 0).toLocaleString('fr-FR')} Ar</td>
                                        <td style="text-align: right; padding: 5px; font-weight: bold;">${(ligne.montant || 0).toLocaleString('fr-FR')} Ar</td>
                                    ` : ''}
                                </tr>
                            `).join('')}
                        </tbody>
                        ${data.isBonAvance || data.isBonPaiement ? `
                            <tfoot>
                                <tr style="border-top: 2px solid #000; font-weight: bold;">
                                    <td colspan="3" style="text-align: right; padding: 8px 5px;">${data.isBonPaiement ? 'TOTALIN\'NY VOLA:' : 'TOTAL:'}</td>
                                    <td style="text-align: right; padding: 8px 5px;">${data.montant ? data.montant.toLocaleString('fr-FR') : '0'} Ar</td>
                                </tr>
                            </tfoot>
                        ` : ''}
                    </table>
                ` : `
                    <div class="line">
                        <span class="label">${data.isBonPaiement ? 'Karazana:' : 'Désignation:'}</span>
                        <span>${data.designation}</span>
                    </div>
                    ${data.quantity ? `
                    <div class="line">
                        <span class="label">${data.isBonPaiement ? 'Isa:' : 'Quantité:'}</span>
                        <span>${data.quantity}</span>
                    </div>
                    ` : ''}
                    ${data.pu ? `
                    <div class="line">
                        <span class="label">${data.isBonPaiement ? 'Vidin-tsirairay:' : 'Prix unitaire:'}</span>
                        <span>${parseFloat(data.pu).toLocaleString('fr-FR')} Ar</span>
                    </div>
                    ` : ''}
                    ${data.montant ? `
                    <div class="line">
                        <span class="label">${data.isBonPaiement ? 'VOLA ALOA:' : 'MONTANT TOTAL:'}</span>
                        <span style="font-weight: bold; font-size: 14px;">${parseFloat(data.montant).toLocaleString('fr-FR')} Ar</span>
                    </div>
                    ` : ''}
                `}
            </div>

            <div class="footer">
                <p>================================</p>

                ${data.isBonPaiement ? `
                    <!-- Espaces pour écriture manuelle (paiements uniquement) -->
                    <div style="margin: 15px 0; padding: 10px; border: 1px dashed #666;">
                        <p style="font-weight: bold; margin-bottom: 8px;">Fandoavam-bola manaraka:</p>
                        <div style="display: flex; justify-content: space-between; margin-bottom: 5px;">
                            <span>Daty / Date:</span>
                            <span style="border-bottom: 1px solid #000; width: 150px;"></span>
                        </div>
                        <div style="display: flex; justify-content: space-between;">
                            <span>Vola / Montant:</span>
                            <span style="border-bottom: 1px solid #000; width: 150px;"></span>
                        </div>
                    </div>
                ` : ''}

                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-top: 20px;">
                    <div style="text-align: center;">
                        <p style="font-weight: bold; margin-bottom: 30px;">${data.isBonPaiement ? 'Sonian\'ny mpiasa' : 'Signature Employé'}</p>
                        <div style="border-top: 1px solid #000; width: 80%; margin: 0 auto;"></div>
                        <p style="font-size: 9px; margin-top: 5px;">Date: ___/___/_____</p>
                    </div>
                    <div style="text-align: center;">
                        <p style="font-weight: bold; margin-bottom: 30px;">${data.isBonPaiement ? 'Sonian\'ny RBF' : 'Signature Fournisseur'}</p>
                        <div style="border-top: 1px solid #000; width: 80%; margin: 0 auto;"></div>
                        ${data.nom_abonne && data.isBonPaiement ? `<p style="font-size: 9px; margin-top: 2px;">${data.nom_abonne}</p>` : ''}
                        <p style="font-size: 9px; margin-top: 5px;">Date: ___/___/_____</p>
                    </div>
                </div>
                <p style="text-align: center; font-size: 9px; margin-top: 15px; font-style: italic;">${data.isBonPaiement ? '' : 'Merci de votre confiance'}</p>
            </div>

            <script>
                window.onload = function() {
                    document.body.innerHTML += \`
                        <div style="text-align: center; margin-top: 20px; page-break-before: always;">
                            <button onclick="imprimerExemplaires()" style="
                                background: #4CAF50;
                                color: white;
                                border: none;
                                padding: 15px 30px;
                                font-size: 16px;
                                border-radius: 5px;
                                cursor: pointer;
                                margin: 10px;
                            ">
                                📄 Imprimer 3 exemplaires
                            </button>
                            <button onclick="window.close()" style="
                                background: #f44336;
                                color: white;
                                border: none;
                                padding: 15px 30px;
                                font-size: 16px;
                                border-radius: 5px;
                                cursor: pointer;
                                margin: 10px;
                            ">
                                ✖ Fermer
                            </button>
                        </div>
                    \`;
                };

                function imprimerExemplaires() {
                    const buttons = document.querySelectorAll('button');
                    buttons.forEach(btn => btn.style.display = 'none');
                    for (let i = 0; i < 3; i++) {
                        setTimeout(() => window.print(), i * 500);
                    }
                    setTimeout(() => {
                        buttons.forEach(btn => btn.style.display = 'inline-block');
                    }, 2000);
                }
            </script>
        </body>
        </html>
    `;

    // Ouvrir dans un nouvel onglet
    const ticketWindow = window.open('', '_blank');

    // Écrire le contenu immédiatement
    ticketWindow.document.open();
    ticketWindow.document.write(ticketHtml);
    ticketWindow.document.close();

    console.log('✅ Ticket ouvert dans un nouvel onglet');
}

console.log('✅ window.imprimerTicket définie');

// Initialiser les événements au chargement de la page
document.addEventListener('DOMContentLoaded', function() {
    console.log('DOM chargé, initialisation workflow terrain...');

    // Note: La gestion des boutons Utiliser livraisons et Collecter paiements
    // est maintenant dans traiter_activite.html pour éviter les problèmes
    // de chargement de fonction

    // ========== AVANCES ==========
    const btnAvances = document.getElementById('btn-traiter-avances');
    if (btnAvances) {
        btnAvances.addEventListener('click', function() {
            console.log('Bouton Traiter avances cliqué');
            const checkboxesCochees = document.querySelectorAll('.avance-select:checked');

            if (checkboxesCochees.length === 0) {
                alert('Veuillez sélectionner au moins une avance');
                return;
            }

            alert('Fonctionnalité avances en développement. ' + checkboxesCochees.length + ' ligne(s) sélectionnée(s).');
        });
    }
});
