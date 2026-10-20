/**
 * Fonction pour imprimer le ticket de caisse pour les paiements BP
 * Format 80mm pour imprimante thermique
 * Inspiré de print_all_tickets.js
 */
function imprimerTicketBP(ticketData, organisationData) {
    const printWindow = window.open('', '_blank', 'width=800,height=600');

    // Générer le HTML du ticket
    const ticketHTML = `
        <div class="ticket">
            <div class="header" style="text-align: center; border-bottom: 2px solid #000; padding-bottom: 10px; margin-bottom: 10px;">
                ${organisationData.logo_url ? `<img src="${organisationData.logo_url}" style="max-width: 150px; margin-bottom: 10px;">` : `<h2 style="margin: 10px 0;">${organisationData.nom}</h2>`}
                <p style="margin: 3px 0; font-size: 10px;">${organisationData.adresse || ''}</p>
                <p style="margin: 3px 0; font-size: 10px;">NIF: ${organisationData.nif || 'N/A'} | STAT: ${organisationData.stat || 'N/A'}</p>
                <p style="margin: 3px 0; font-size: 10px; font-weight: bold;">Base: ${organisationData.base || ''}</p>
            </div>

            <h2 style="text-align: center; font-size: 18px; margin: 15px 0; font-weight: bold;">FACTURE</h2>

            <div style="text-align: center; margin-bottom: 15px;">
                <div id="qr-code" style="display: inline-block;"></div>
                <p style="font-size: 11px; margin-top: 5px; font-weight: bold;">${ticketData.numero_ticket}</p>
            </div>

            <div style="margin: 10px 0; font-size: 12px;">
                <div style="display: flex; justify-content: space-between; margin: 5px 0;">
                    <span style="font-weight: bold;">Daty / Date:</span>
                    <span>${ticketData.date}</span>
                </div>
                <div style="display: flex; justify-content: space-between; margin: 5px 0;">
                    <span style="font-weight: bold;">Ora / Heure:</span>
                    <span>${ticketData.heure}</span>
                </div>
                <div style="display: flex; justify-content: space-between; margin: 5px 0;">
                    <span style="font-weight: bold;">Ouvrage:</span>
                    <span>${ticketData.ouvrage}</span>
                </div>
                <div style="display: flex; justify-content: space-between; margin: 5px 0;">
                    <span style="font-weight: bold;">Village:</span>
                    <span>${ticketData.village}</span>
                </div>
                <div style="display: flex; justify-content: space-between; margin: 5px 0;">
                    <span style="font-weight: bold;">Abonné / Mpanjifa:</span>
                    <span>${ticketData.abonne}</span>
                </div>
            </div>

            <div style="border-top: 1px dashed #000; border-bottom: 1px dashed #000; margin: 10px 0;"></div>

            <div style="margin: 15px 0; padding: 10px; background-color: #f5f5f5; border-radius: 5px;">
                <div style="font-weight: bold; font-size: 13px; margin-bottom: 5px; text-align: center;">
                    ${ticketData.type}
                </div>
                <div style="font-size: 11px; margin: 5px 0;">
                    <strong>Type BP:</strong> ${ticketData.type_bp}
                </div>
                ${ticketData.point_eau_code ? `
                <div style="font-size: 11px; margin: 5px 0;">
                    <strong>Code:</strong> ${ticketData.point_eau_code}
                </div>` : ''}
                ${ticketData.distance !== undefined ? `
                <div style="font-size: 11px; margin: 5px 0;">
                    <strong>Distance:</strong> ${ticketData.distance.toFixed(2)} m
                </div>` : ''}
            </div>

            ${ticketData.distance !== undefined && ticketData.distance > 0 ? `
            <div style="margin: 10px 0; font-size: 10px; border: 1px solid #ccc; padding: 8px; background-color: #fafafa;">
                <div style="font-weight: bold; margin-bottom: 5px; text-align: center;">Calcul du montant</div>
                <div style="display: flex; justify-content: space-between; margin: 3px 0;">
                    <span>Tarif devis base:</span>
                    <span>${ticketData.tarif_devis_base ? ticketData.tarif_devis_base.toLocaleString('fr-FR') : '0'} Ar</span>
                </div>
                ${ticketData.distance > 12 ? `
                <div style="display: flex; justify-content: space-between; margin: 3px 0;">
                    <span>Mètres supplémentaires:</span>
                    <span>${(ticketData.distance - 12).toFixed(2)} m × ${ticketData.tarif_metre_supp ? ticketData.tarif_metre_supp.toLocaleString('fr-FR') : '0'} Ar</span>
                </div>
                <div style="display: flex; justify-content: space-between; margin: 3px 0;">
                    <span>Supplément distance:</span>
                    <span>${((ticketData.distance - 12) * (ticketData.tarif_metre_supp || 0)).toLocaleString('fr-FR')} Ar</span>
                </div>` : ''}
                ${ticketData.promotion && ticketData.promotion > 0 ? `
                <div style="display: flex; justify-content: space-between; margin: 3px 0; color: #28a745;">
                    <span>Promotion:</span>
                    <span>- ${ticketData.promotion.toLocaleString('fr-FR')} Ar</span>
                </div>` : ''}
            </div>` : ''}

            <div style="border-top: 2px solid #000; border-bottom: 2px solid #000; margin: 15px 0; padding: 10px 0;">
                <div style="display: flex; justify-content: space-between; margin: 8px 0; font-size: 16px; font-weight: bold;">
                    <span>VOLA ALOHA / MONTANT:</span>
                    <span>${ticketData.montant.toLocaleString('fr-FR')} Ar</span>
                </div>
            </div>

            <div style="margin: 15px 0; font-size: 10px; padding-top: 10px; border-top: 1px dashed #000;">
                <p style="margin: 5px 0;"><strong>Sonian'ny Mpanjifa:</strong></p>
                <p style="margin: 3px 0; color: #666; font-style: italic;">Signature de l'abonné</p>
                <div style="border-top: 1px solid #000; width: 100%; margin-top: 30px;"></div>
            </div>

            <div style="margin: 15px 0; font-size: 10px;">
                <p style="margin: 5px 0;"><strong>Agent-mpandray / Agent:</strong></p>
                <div style="border-top: 1px solid #000; width: 100%; margin-top: 30px;"></div>
            </div>

            <p style="text-align: center; margin-top: 20px; font-size: 9px;">Misaotra tompoko / Merci beaucoup!</p>
            <p style="text-align: center; font-size: 8px; color: #666; margin-top: 5px;">
                ${ticketData.description}
            </p>
        </div>
    `;

    // Document HTML complet avec styles
    const fullHTML = `
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <title>Ticket BP - ${ticketData.numero_ticket}</title>
            <script src="https://cdnjs.cloudflare.com/ajax/libs/qrcodejs/1.0.0/qrcode.min.js"></script>
            <style>
                @media print {
                    @page {
                        size: 80mm auto;
                        margin: 5mm;
                    }
                    .ticket {
                        width: 80mm;
                    }
                }

                body {
                    font-family: 'Courier New', monospace;
                    margin: 0;
                    padding: 10px;
                }

                .ticket {
                    width: 80mm;
                    margin: 0 auto;
                }

                h1, h2, h3, h4, h5, h6 {
                    margin: 0;
                    padding: 0;
                }
            </style>
        </head>
        <body>
            ${ticketHTML}

            <script>
                // Générer le QR Code
                setTimeout(function() {
                    const qrDiv = document.getElementById('qr-code');
                    if (qrDiv) {
                        new QRCode(qrDiv, {
                            text: '${ticketData.numero_ticket}',
                            width: 100,
                            height: 100
                        });
                    }

                    // Imprimer automatiquement après génération du QR code
                    setTimeout(function() {
                        window.print();
                    }, 500);
                }, 100);
            </script>
        </body>
        </html>
    `;

    printWindow.document.write(fullHTML);
    printWindow.document.close();
}
