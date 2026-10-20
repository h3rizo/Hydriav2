/**
 * Workflow Facturation Volumétrique - Impression des tickets
 */

// Fonction pour imprimer un ticket volumétrique (format thermal 80mm)
function imprimerTicketVolumetrique(data) {
    console.log('🖨️ Impression ticket volumétrique:', data);

    // Créer le HTML du ticket
    const ticketHtml = `
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <title>Facture Volumétrique - ${data.numero_bon}</title>
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
                table {
                    width: 100%;
                    font-size: 10px;
                    border-collapse: collapse;
                    margin: 10px 0;
                }
                th {
                    text-align: left;
                    padding: 5px;
                    border-bottom: 1px solid #000;
                }
                td {
                    padding: 5px;
                    border-bottom: 1px dashed #ccc;
                }
            </style>
        </head>
        <body>
            <div class="header">
                ${data.logo_url ? `<img src="${data.logo_url}" alt="${data.organisation}">` : `<h1>${data.organisation}</h1>`}
                ${data.nif ? `<p style="font-size: 9px;">NIF: ${data.nif}</p>` : ''}
                ${data.stat ? `<p style="font-size: 9px;">STAT: ${data.stat}</p>` : ''}
                ${data.base ? `<p style="font-size: 10px; font-weight: bold;">Base: ${data.base}</p>` : ''}
                <p>================================</p>
            </div>

            <h2 style="text-align: center; font-size: 18px; font-weight: bold; margin: 10px 0;">
                FAKTIORA
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
                    <span class="label">Daty:</span>
                    <span>${data.date}</span>
                </div>
                <div class="line">
                    <span class="label">Mpiasa:</span>
                    <span>${data.employe}</span>
                </div>
                <div class="line">
                    <span class="label">Fotodrafitrasa:</span>
                    <span>${data.ouvrage}</span>
                </div>
                <div class="line">
                    <span class="label">Toeram-patsakana:</span>
                    <span>${data.point_eau}</span>
                </div>
                <div class="line">
                    <span class="label">Kiosque:</span>
                    <span>${data.nom_abonne}</span>
                </div>

                <div class="separator"></div>

                <table>
                    <thead>
                        <tr>
                            <th>Karazana</th>
                            <th style="text-align: center; width: 60px;">Isa</th>
                            <th style="text-align: right; width: 70px;">Vidin-tsirairay</th>
                            <th style="text-align: right; width: 80px;">Vidy</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${data.lignes.map(ligne => `
                            <tr>
                                <td>${ligne.designation}</td>
                                <td style="text-align: center;">${ligne.quantity}</td>
                                <td style="text-align: right;">${parseFloat(ligne.pu).toLocaleString('fr-FR')} Ar</td>
                                <td style="text-align: right; font-weight: bold;">${parseFloat(ligne.montant).toLocaleString('fr-FR')} Ar</td>
                            </tr>
                        `).join('')}
                    </tbody>
                    <tfoot>
                        <tr style="border-top: 1px solid #000;">
                            <td colspan="3" style="text-align: right; padding: 5px; font-weight: bold;">Totalina HT:</td>
                            <td style="text-align: right; padding: 5px; font-weight: bold;">${data.montant_ht.toLocaleString('fr-FR')} Ar</td>
                        </tr>
                        <tr>
                            <td colspan="3" style="text-align: right; padding: 5px; font-size: 9px; font-style: italic;">
                                <i class="fas fa-info-circle"></i> Hetra kaominina 7% (tsy ampiana):
                            </td>
                            <td style="text-align: right; padding: 5px; font-size: 9px; font-style: italic;">${data.taxe_communale.toLocaleString('fr-FR')} Ar</td>
                        </tr>
                        <tr style="border-top: 2px solid #000; font-weight: bold;">
                            <td colspan="3" style="text-align: right; padding: 8px 5px;">TOTALIN'NY VOLA:</td>
                            <td style="text-align: right; padding: 8px 5px;">${data.montant.toLocaleString('fr-FR')} Ar</td>
                        </tr>
                    </tfoot>
                </table>

                <p style="font-size: 9px; font-style: italic; text-align: center; margin: 10px 0; color: #666;">
                    * Montant arrondi à 100 Ar près (arrondi supérieur)<br>
                    * Taxe communale affichée à titre indicatif uniquement
                </p>
            </div>

            <div class="footer">
                <p>================================</p>

                <!-- Espaces pour paiements suivants -->
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

                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-top: 20px;">
                    <div style="text-align: center;">
                        <p style="font-weight: bold; margin-bottom: 30px;">Sonian'ny mpandoa vola</p>
                        <div style="border-top: 1px solid #000; width: 80%; margin: 0 auto;"></div>
                        <p style="font-size: 9px; margin-top: 5px;">Date: ___/___/_____</p>
                    </div>
                    <div style="text-align: center;">
                        <p style="font-weight: bold; margin-bottom: 30px;">Sonian'ny Kiosque</p>
                        <div style="border-top: 1px solid #000; width: 80%; margin: 0 auto;"></div>
                        <p style="font-size: 9px; margin-top: 2px;">${data.nom_abonne}</p>
                        <p style="font-size: 9px; margin-top: 5px;">Date: ___/___/_____</p>
                    </div>
                </div>
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
            <\/script>
        </body>
        </html>
    `;

    // Ouvrir dans un nouvel onglet
    const ticketWindow = window.open('', '_blank');
    ticketWindow.document.open();
    ticketWindow.document.write(ticketHtml);
    ticketWindow.document.close();

    console.log('✅ Ticket volumétrique ouvert dans un nouvel onglet');
}

console.log('✅ workflow_facturation.js chargé');
