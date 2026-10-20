/**
 * Fonction pour imprimer UNIQUEMENT les tickets de caisse (format 80mm)
 * Imprimante thermique 80mm
 */
function imprimerTickets80mm(relevesCalcules, ouvrageNom, organisationData) {
  const printWindow = window.open("", "_blank", "width=800,height=600");

  // Générer le HTML pour tous les tickets
  let ticketsHTML = "";

  relevesTries.forEach((releve) => {
    const detail = releve.detail_calcul;

    // Valeurs par défaut pour éviter undefined
    const volume_consomme = detail.volume_consomme || 0;
    const volume_carte_sociale = detail.volume_carte_sociale || 0;
    const volume_non_facture = detail.volume_non_facture || 0;

    const montantArrondi = parseFloat(detail.montant_arrondi);

    // Ticket de caisse (format 80mm)
    ticketsHTML += `
            <div class="ticket" style="page-break-after: always;">
                <div class="header" style="text-align: center; border-bottom: 2px solid #000; padding-bottom: 10px; margin-bottom: 10px;">
                    ${organisationData.logo_url ? `<img src="${organisationData.logo_url}" style="max-width: 150px; margin-bottom: 10px;">` : `<h2 style="margin: 10px 0;">${organisationData.nom}</h2>`}
                    <p style="margin: 3px 0; font-size: 10px;">${organisationData.adresse || ""}</p>
                    <p style="margin: 3px 0; font-size: 10px;">NIF: ${organisationData.nif || "N/A"} | STAT: ${organisationData.stat || "N/A"}</p>
                    ${organisationData.directeur_telephone ? `<p style="margin: 3px 0; font-size: 10px;">Tel Directeur: ${organisationData.directeur_telephone}</p>` : ""}
                    <p style="margin: 3px 0; font-size: 10px; font-weight: bold;">Base: ${organisationData.base || ""}</p>
                </div>

                <h2 style="text-align: center; font-size: 18px; margin: 15px 0; font-weight: bold;">FAKTIORA</h2>

                <div style="text-align: center; margin-bottom: 15px;">
                    <div id="qr-${index}" style="display: inline-block;"></div>
                    <p style="font-size: 11px; margin-top: 5px; font-weight: bold;">${numeroFacture}</p>
                </div>

                <div style="margin: 10px 0; font-size: 12px;">
                    <div style="display: flex; justify-content: space-between; margin: 5px 0;">
                        <span style="font-weight: bold;">Daty / Date:</span>
                        <span>${new Date().toLocaleDateString("fr-FR")}</span>
                    </div>
                    <div style="display: flex; justify-content: space-between; margin: 5px 0;">
                        <span style="font-weight: bold;">Ouvrage:</span>
                        <span>${ouvrageNom}</span>
                    </div>
                    <div style="display: flex; justify-content: space-between; margin: 5px 0;">
                        <span style="font-weight: bold;">Toeram-patsakana:</span>
                        <span>${releve.point_eau}</span>
                    </div>
                    <div style="display: flex; justify-content: space-between; margin: 5px 0;">
                        <span style="font-weight: bold;">Kiosque:</span>
                        <span>${releve.abonne}</span>
                    </div>
                </div>

                <div style="border-top: 1px dashed #000; border-bottom: 1px dashed #000; margin: 10px 0;"></div>

                <table style="width: 100%; border-collapse: collapse; font-size: 11px; margin: 10px 0;">
                    <thead>
                        <tr style="border-bottom: 1px solid #000;">
                            <th style="text-align: left; padding: 5px;">Karazana</th>
                            <th style="text-align: center; padding: 5px; width: 50px;">Isa</th>
                            <th style="text-align: right; padding: 5px; width: 70px;">Vidin-tsirairay</th>
                            <th style="text-align: right; padding: 5px; width: 80px;">Vidy</th>
                        </tr>
                    </thead>
                    <tbody>
                        <tr>
                            <td style="padding: 5px;">Hofana compteur</td>
                            <td style="text-align: center; padding: 5px;">1</td>
                            <td style="text-align: right; padding: 5px;">${parseFloat(detail.abonnement).toLocaleString("fr-FR")}</td>
                            <td style="text-align: right; padding: 5px;">${parseFloat(detail.abonnement).toLocaleString("fr-FR")}</td>
                        </tr>
                        <tr style="border-top: 1px dashed #ccc;">
                            <td colspan="4" style="padding: 3px 5px; font-size: 10px; background-color: #f5f5f5;">
                                <strong>Rano lany:</strong> ${volume_consomme.toFixed(2)} m³
                            </td>
                        </tr>
                        ${
                          volume_carte_sociale > 0
                            ? `
                        <tr>
                            <td colspan="4" style="padding: 3px 5px; font-size: 9px;">
                                <i>- Carte sociale:</i> ${volume_carte_sociale.toFixed(2)} m³
                            </td>
                        </tr>`
                            : ""
                        }
                        ${
                          volume_non_facture > 0
                            ? `
                        <tr>
                            <td colspan="4" style="padding: 3px 5px; font-size: 9px;">
                                <i>- Non facturé:</i> ${volume_non_facture.toFixed(2)} m³
                            </td>
                        </tr>`
                            : ""
                        }
                        <tr style="border-bottom: 1px dashed #ccc;">
                            <td colspan="4" style="padding: 3px 5px; font-size: 10px; font-weight: bold; background-color: #f5f5f5;">
                                <strong>= Rano anaty facture:</strong> ${detail.volume_facture.toFixed(2)} m³
                            </td>
                        </tr>
                        <tr>
                            <td style="padding: 5px;">Rano anaty facture</td>
                            <td style="text-align: center; padding: 5px;">${detail.volume_facture.toFixed(2)}</td>
                            <td style="text-align: right; padding: 5px;">-</td>
                            <td style="text-align: right; padding: 5px;">${parseFloat(detail.montant_volume).toLocaleString("fr-FR")}</td>
                        </tr>
                    </tbody>
                </table>

                ${
                  releve.factures_impayees &&
                  releve.factures_impayees.length > 0
                    ? `
                <div style="border: 2px solid #ff0000; margin: 10px 0; padding: 8px; background-color: #fff5f5;">
                    <h3 style="margin: 0 0 8px 0; font-size: 12px; color: #dc2626; text-align: center; font-weight: bold;">
                        ⚠️ TROSA TALOHA / IMPAYÉS ANTÉRIEURS
                    </h3>
                    <table style="width: 100%; border-collapse: collapse; font-size: 9px;">
                        <thead>
                            <tr style="border-bottom: 1px solid #ccc;">
                                <th style="text-align: left; padding: 3px;">Daty</th>
                                <th style="text-align: center; padding: 3px;">Rano (m³)</th>
                                <th style="text-align: right; padding: 3px;">Vola (Ar)</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${releve.factures_impayees
                              .map(
                                (f) => `
                                <tr>
                                    <td style="padding: 3px;">${new Date(f.datereleve).toLocaleDateString("fr-FR")}</td>
                                    <td style="text-align: center; padding: 3px;">${parseFloat(f.volume_facture || 0).toFixed(2)}</td>
                                    <td style="text-align: right; padding: 3px;">${parseFloat(f.montant).toLocaleString("fr-FR")}</td>
                                </tr>
                            `,
                              )
                              .join("")}
                        </tbody>
                        <tfoot>
                            <tr style="border-top: 2px solid #dc2626; font-weight: bold;">
                                <td colspan="2" style="padding: 5px; text-align: left;">TOTAL TROSA:</td>
                                <td style="padding: 5px; text-align: right; color: #dc2626;">${parseFloat(releve.total_impaye).toLocaleString("fr-FR")} Ar</td>
                            </tr>
                        </tfoot>
                    </table>
                </div>
                `
                    : ""
                }

                <div style="border-top: 2px solid #000; border-bottom: 2px solid #000; margin: 10px 0; padding: 8px 0;">
                    <div style="display: flex; justify-content: space-between; margin: 5px 0; font-size: 10px; color: #666;">
                        <span>Taxe 7% (indicatif):</span>
                        <span>${parseFloat(detail.taxe_communale).toLocaleString("fr-FR")} Ar</span>
                    </div>
                    <div style="display: flex; justify-content: space-between; margin: 8px 0; font-size: 18px; font-weight: bold;">
                        <span>VOLA ALOHA:</span>
                        <span>${montantArrondi.toLocaleString("fr-FR")} Ar</span>
                    </div>
                </div>

                ${
                  releve.total_impaye > 0
                    ? `
                <div style="border: 2px dashed #dc2626; margin: 10px 0; padding: 8px; background-color: #fff5f5;">
                    <h4 style="margin: 0 0 5px 0; font-size: 11px; color: #dc2626; text-align: center; font-weight: bold;">
                        📢 FAMPAHAFANTARANA / RAPPEL
                    </h4>
                    <p style="margin: 5px 0; font-size: 9px; text-align: center; color: #666;">
                        Manana trosa tsy voaloa ianao / Vous avez des impayés antérieurs
                    </p>
                    <div style="display: flex; justify-content: space-between; margin: 8px 0; font-size: 14px; font-weight: bold; color: #dc2626;">
                        <span>TROSA TALOHA:</span>
                        <span>${parseFloat(releve.total_impaye).toLocaleString("fr-FR")} Ar</span>
                    </div>
                    <p style="margin: 5px 0 0 0; font-size: 8px; text-align: center; font-style: italic; color: #666;">
                        Tsy tafiditra amin'ny faktiora ankehitriny / Non inclus dans cette facture
                    </p>
                </div>
                `
                    : ""
                }

                <div style="margin: 15px 0; font-size: 10px;">
                    <p style="margin: 5px 0;"><strong>Sonian'ny Kiosque:</strong></p>
                    <div style="border-top: 1px solid #000; width: 100%; margin-top: 30px;"></div>
                </div>

                <div style="margin: 15px 0; font-size: 10px;">
                    <p style="margin: 5px 0;"><strong>Agent-mpandray:</strong></p>
                    <div style="border-top: 1px solid #000; width: 100%; margin-top: 30px;"></div>
                </div>

                <p style="text-align: center; margin-top: 20px; font-size: 9px;">Misaotra / Merci!</p>
            </div>
        `;
  });

  // Document pour tickets 80mm uniquement
  const fullHTML = `
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <title>Tickets de Caisse - ${ouvrageNom}</title>
            <script src="https://cdnjs.cloudflare.com/ajax/libs/qrcodejs/1.0.0/qrcode.min.js"></script>
            <style>
                @media print {
                    @page {
                        size: 80mm auto;
                        margin: 5mm;
                    }
                    .ticket {
                        width: 80mm;
                        page-break-after: always;
                    }
                    .print-buttons {
                        display: none !important;
                    }
                }
                body {
                    font-family: 'Courier New', monospace;
                    margin: 0;
                    padding: 0;
                }
                .ticket {
                    width: 80mm;
                    padding: 10px;
                    margin: 0 auto 20px;
                    border: 1px dashed #ccc;
                }
                .print-buttons {
                    position: fixed;
                    top: 20px;
                    right: 20px;
                    z-index: 1000;
                    background: white;
                    padding: 15px;
                    border: 2px solid #000;
                    border-radius: 8px;
                    box-shadow: 0 4px 8px rgba(0,0,0,0.2);
                }
                .print-buttons button {
                    display: block;
                    width: 100%;
                    padding: 12px 20px;
                    margin-bottom: 10px;
                    font-size: 14px;
                    font-weight: bold;
                    cursor: pointer;
                    border: none;
                    border-radius: 4px;
                    transition: all 0.3s;
                }
                .btn-print-2x {
                    background-color: #10b981;
                    color: white;
                }
                .btn-print-2x:hover {
                    background-color: #059669;
                }
                .btn-close {
                    background-color: #ef4444;
                    color: white;
                }
                .btn-close:hover {
                    background-color: #dc2626;
                }
            </style>
        </head>
        <body>
            <div class="print-buttons">
                <button class="btn-print-2x" onclick="imprimerDeuxExemplaires()">
                    🖨️ Imprimer 2 exemplaires
                </button>
                <button class="btn-close" onclick="window.close()">
                    ❌ Fermer
                </button>
            </div>

            ${ticketsHTML}

            <script>
                // Générer les QR codes après le chargement
                window.addEventListener('load', function() {
                    ${relevesCalcules
                      .map(
                        (releve, index) => `
                        new QRCode(document.getElementById("qr-${index}"), {
                            text: "FACT-VOL-${releve.releve_id.slice(0, 8).toUpperCase()}",
                            width: 100,
                            height: 100
                        });
                    `,
                      )
                      .join("")}
                });

                function imprimerDeuxExemplaires() {
                    window.print();
                    setTimeout(() => {
                        window.print();
                    }, 500);
                }
            </script>
        </body>
        </html>
    `;

  printWindow.document.write(fullHTML);
  printWindow.document.close();
}

/**
 * Fonction pour imprimer UNIQUEMENT le récapitulatif A4
 * Imprimante laser/jet d'encre A4
 */
function imprimerRecapA4(relevesCalcules, ouvrageNom, organisationData) {
  const printWindow = window.open("", "_blank", "width=1024,height=768");

  const escapeRecapHtml = (value) => String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
  const getTypePointEau = (releve) => {
    const typeNom = String(releve.type_point_eau || "").trim();
    return typeNom || "Type non défini";
  };

  const relevesTries = [...relevesCalcules].sort((a, b) => {
    const typeCompare = getTypePointEau(a).localeCompare(
      getTypePointEau(b),
      "fr",
      { numeric: true, sensitivity: "base" },
    );
    if (typeCompare !== 0) return typeCompare;

    const idxA = (a.idxls || "").toString().trim();
    const idxB = (b.idxls || "").toString().trim();
    const idxCompare = idxA.localeCompare(idxB, "fr", {
      numeric: true,
      sensitivity: "base",
    });
    if (idxCompare !== 0) {
      return idxCompare;
    }

    const abonneA = (a.abonne || "").toString().trim();
    const abonneB = (b.abonne || "").toString().trim();
    const abonneCompare = abonneA.localeCompare(abonneB, "fr", {
      sensitivity: "base",
    });
    if (abonneCompare !== 0) {
      return abonneCompare;
    }

    return (a.releve_id || "").localeCompare(b.releve_id || "", "fr", {
      sensitivity: "base",
    });
  });

  let recapRows = "";
  let totalGeneral = 0;
  let totalImpayes = 0;

  const groupesParType = new Map();
  relevesTries.forEach((releve) => {
    const typeNom = getTypePointEau(releve);
    if (!groupesParType.has(typeNom)) groupesParType.set(typeNom, []);
    groupesParType.get(typeNom).push(releve);
  });

  groupesParType.forEach((relevesDuType, typeNom) => {
    let sousTotalType = 0;
    let sousTotalImpayesType = 0;
    recapRows += `
      <tr style="background-color: #dbeafe; font-weight: bold;">
        <td colspan="10" style="border: 1px solid #000; padding: 7px; font-size: 12px;">
          TYPE DE POINT D'EAU : ${escapeRecapHtml(typeNom)}
          <span style="font-weight: normal; margin-left: 8px;">(${relevesDuType.length} point${relevesDuType.length > 1 ? "s" : ""} d'eau)</span>
        </td>
      </tr>`;

    relevesDuType.forEach((releve) => {
      const detail = releve.detail_calcul || {};
      const montantArrondi = Number.parseFloat(detail.montant_arrondi) || 0;
      const impayes = Number.parseFloat(releve.total_impaye) || 0;

      totalGeneral += montantArrondi;
      totalImpayes += impayes;
      sousTotalType += montantArrondi;
      sousTotalImpayesType += impayes;

    // Ligne du tableau récapitulatif avec colonnes de suivi
    recapRows += `
            <tr ${impayes > 0 ? 'style="background-color: #fff5f5;"' : ""}>
                <td style="border: 1px solid #000; padding: 6px; font-size: 11px;">${escapeRecapHtml(releve.idxls || "-")}</td>
                <td style="border: 1px solid #000; padding: 6px; font-size: 10px; font-weight: bold;">${escapeRecapHtml(getTypePointEau(releve))}</td>
                <td style="border: 1px solid #000; padding: 6px; font-size: 11px;">${escapeRecapHtml(releve.abonne || "-")}</td>
                <td style="border: 1px solid #000; padding: 6px; text-align: right; font-weight: bold; font-size: 11px;">${montantArrondi.toLocaleString("fr-FR")} Ar</td>
                <td style="border: 1px solid #000; padding: 6px; text-align: right; font-size: 10px; ${impayes > 0 ? "color: #dc2626; font-weight: bold;" : ""}">${impayes > 0 ? impayes.toLocaleString("fr-FR") + " Ar" : "-"}</td>
                <td style="border: 1px solid #000; padding: 6px; background-color: #f9f9f9;"></td>
                <td style="border: 1px solid #000; padding: 6px; background-color: #f9f9f9;"></td>
                <td style="border: 1px solid #000; padding: 6px; background-color: #f9f9f9;"></td>
                <td style="border: 1px solid #000; padding: 6px; background-color: #f9f9f9;"></td>
                <td style="border: 1px solid #000; padding: 6px; background-color: #f9f9f9;"></td>
            </tr>
        `;
    });

    recapRows += `
      <tr style="background-color: #eff6ff; font-weight: bold;">
        <td colspan="3" style="border: 1px solid #000; padding: 6px; text-align: right; font-size: 11px;">SOUS-TOTAL ${escapeRecapHtml(typeNom)} :</td>
        <td style="border: 1px solid #000; padding: 6px; text-align: right; font-size: 11px;">${sousTotalType.toLocaleString("fr-FR")} Ar</td>
        <td style="border: 1px solid #000; padding: 6px; text-align: right; color: #dc2626; font-size: 10px;">${sousTotalImpayesType > 0 ? sousTotalImpayesType.toLocaleString("fr-FR") + " Ar" : "-"}</td>
        <td colspan="5" style="border: 1px solid #000; padding: 6px; background-color: #eff6ff;"></td>
      </tr>`;
  });

  // Document A4 récapitulatif
  const fullHTML = `
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <title>Récapitulatif Factures - ${ouvrageNom}</title>
            <style>
                @media print {
                    @page {
                        size: A4 landscape;
                        margin: 15mm;
                    }
                    .print-buttons {
                        display: none !important;
                    }
                }
                body {
                    font-family: Arial, sans-serif;
                    margin: 0;
                    padding: 10px;
                }
                .print-buttons {
                    position: fixed;
                    top: 20px;
                    right: 20px;
                    z-index: 1000;
                    background: white;
                    padding: 15px;
                    border: 2px solid #000;
                    border-radius: 8px;
                    box-shadow: 0 4px 8px rgba(0,0,0,0.2);
                }
                .print-buttons button {
                    display: block;
                    width: 100%;
                    padding: 12px 20px;
                    margin-bottom: 10px;
                    font-size: 14px;
                    font-weight: bold;
                    cursor: pointer;
                    border: none;
                    border-radius: 4px;
                    transition: all 0.3s;
                }
                .btn-print {
                    background-color: #3b82f6;
                    color: white;
                }
                .btn-print:hover {
                    background-color: #2563eb;
                }
                .btn-close {
                    background-color: #ef4444;
                    color: white;
                }
                .btn-close:hover {
                    background-color: #dc2626;
                }
            </style>
        </head>
        <body>
            <div class="print-buttons">
                <button class="btn-print" onclick="window.print()">
                    🖨️ Imprimer
                </button>
                <button class="btn-close" onclick="window.close()">
                    ❌ Fermer
                </button>
            </div>

            <div style="padding: 10px;">
                <h1 style="text-align: center; margin-bottom: 10px; font-size: 18px;">RÉCAPITULATIF DES FACTURES</h1>
                <p style="text-align: center; margin-bottom: 15px; font-size: 11px;">
                    <strong>Ouvrage:</strong> ${ouvrageNom} |
                    <strong>Date:</strong> ${new Date().toLocaleDateString("fr-FR")} |
                    <strong>Nombre:</strong> ${relevesCalcules.length} factures
                </p>

                <table style="width: 100%; border-collapse: collapse; margin-bottom: 20px; font-size: 11px;">
                    <thead>
                        <tr style="background-color: #e0e0e0;">
                            <th style="border: 1px solid #000; padding: 6px; width: 6%;">IDXls</th>
                            <th style="border: 1px solid #000; padding: 6px; width: 9%;">Type</th>
                            <th style="border: 1px solid #000; padding: 6px; width: 13%;">Abonné/Kiosque</th>
                            <th style="border: 1px solid #000; padding: 6px; width: 10%;">Montant (Ar)</th>
                            <th style="border: 1px solid #000; padding: 6px; width: 9%; font-size: 10px; color: #dc2626;">Rappel Impayés (Ar)</th>
                            <th style="border: 1px solid #000; padding: 6px; width: 8%; font-size: 10px;">Paiement</th>
                            <th style="border: 1px solid #000; padding: 6px; width: 7%; font-size: 10px;">Descente</th>
                            <th style="border: 1px solid #000; padding: 6px; width: 7%; font-size: 10px;">Coupure</th>
                            <th style="border: 1px solid #000; padding: 6px; width: 7%; font-size: 10px;">Paiem. 2</th>
                            <th style="border: 1px solid #000; padding: 6px; width: 8%; font-size: 10px;">Désinstall.</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${recapRows}
                    </tbody>
                    <tfoot>
                        <tr style="background-color: #e0e0e0; font-weight: bold; font-size: 13px;">
                            <td colspan="3" style="border: 2px solid #000; padding: 8px; text-align: right;">TOTAL GÉNÉRAL:</td>
                            <td style="border: 2px solid #000; padding: 8px; text-align: right; font-size: 14px;">${totalGeneral.toLocaleString("fr-FR")} Ar</td>
                            <td style="border: 2px solid #000; padding: 8px; text-align: right; color: #dc2626; font-size: 11px;">${totalImpayes > 0 ? totalImpayes.toLocaleString("fr-FR") + " Ar" : "-"}</td>
                            <td colspan="5" style="border: 2px solid #000; padding: 8px; background-color: #f9f9f9;"></td>
                        </tr>
                    </tfoot>
                </table>

                ${
                  totalImpayes > 0
                    ? `
                <div style="margin-top: 15px; padding: 10px; border: 2px dashed #dc2626; background-color: #fff5f5;">
                    <p style="margin: 0; font-size: 11px; color: #dc2626; font-weight: bold;">
                        ⚠️ NOTE IMPORTANTE / FAMPAHAFANTARANA LEHIBE :
                    </p>
                    <p style="margin: 5px 0 0 0; font-size: 10px; color: #666;">
                        La colonne "Rappel Impayés" affiche les dettes antérieures (depuis 2025) à titre informatif uniquement.
                        Ces montants ne sont PAS inclus dans le Total Général à encaisser aujourd'hui.
                    </p>
                    <p style="margin: 5px 0 0 0; font-size: 10px; color: #666; font-style: italic;">
                        Ny "Rappel Impayés" dia mampiseho ny trosa taloha (manomboka 2025) ho fampahafantarana ihany.
                        Tsy tafiditra ao anatin'ny Total Général horaketina androany ireo vola ireo.
                    </p>
                </div>
                `
                    : ""
                }

                <div style="margin-top: 50px; display: flex; justify-content: space-between;">
                    <div style="text-align: center;">
                        <p style="font-weight: bold; margin-bottom: 60px;">Caissier(ère)</p>
                        <div style="border-top: 1px solid #000; width: 200px; margin: 0 auto;"></div>
                        <p style="margin-top: 5px;">Date: ___/___/_____</p>
                    </div>
                    <div style="text-align: center;">
                        <p style="font-weight: bold; margin-bottom: 60px;">Chef de Base</p>
                        <div style="border-top: 1px solid #000; width: 200px; margin: 0 auto;"></div>
                        <p style="margin-top: 5px;">Date: ___/___/_____</p>
                    </div>
                </div>
            </div>
        </body>
        </html>
    `;

  printWindow.document.write(fullHTML);
  printWindow.document.close();
}
