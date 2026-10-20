(function () {
  function escapeHtml(value) {
    return String(value ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function toNumber(value) {
    const number = Number.parseFloat(value);
    return Number.isFinite(number) ? number : 0;
  }

  function formatAmount(value) {
    return `${toNumber(value).toLocaleString("fr-FR")} Ar`;
  }

  function formatQuantity(value) {
    const number = toNumber(value);
    if (Number.isInteger(number)) {
      return String(number);
    }
    return number.toLocaleString("fr-FR", {
      minimumFractionDigits: 0,
      maximumFractionDigits: 2,
    });
  }

  function formatDate(value) {
    if (!value) {
      return new Date().toLocaleDateString("fr-FR");
    }

    if (typeof value === "string" && value.includes("/")) {
      return value;
    }

    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? escapeHtml(value) : date.toLocaleDateString("fr-FR");
  }

  function buildMvolaPaymentReason(numeroAbonne, ouvrageNom) {
    return `${String(numeroAbonne || "").trim()}${String(ouvrageNom || "").trim()}`
      .replace(/\s+/g, "");
  }

  function renderMvolaPaymentNotice(numeroAbonne, ouvrageNom, fraisMvola) {
    const raisonPaiement = escapeHtml(buildMvolaPaymentReason(numeroAbonne, ouvrageNom));
    const fraisLabel = fraisMvola !== null && fraisMvola !== undefined && fraisMvola !== "" && Number.isFinite(Number(fraisMvola))
      ? ` <strong>( Frais paiement MVola: ${escapeHtml(formatAmount(fraisMvola))})</strong>`
      : "";
    return `
      <div class="mvola-payment-notice">
        <img src="/static/images/mvola-logo.svg" alt="MVola" class="mvola-payment-logo">
        <span>Afaka aloha MVola amin'ity numero ity ny vola : <strong>034 74 699 64</strong> amin'ny anaran'i <strong>Herizo nandrianintsoa</strong> Raison : <strong>${raisonPaiement}</strong>${fraisLabel}</span>
      </div>
    `;
  }

  function chunkArray(items, size) {
    const chunks = [];
    for (let index = 0; index < items.length; index += size) {
      chunks.push(items.slice(index, index + size));
    }
    return chunks;
  }

  function normalizeTicket(ticket, fallbackOrganisation) {
    const fallbackBaseTelephone =
      fallbackOrganisation.base_telephone ||
      fallbackOrganisation.baseTelephone ||
      "";
    const organisationName =
      ticket.organisation ||
      ticket.nom_organisation ||
      fallbackOrganisation.nom_organisation ||
      fallbackOrganisation.nom ||
      "HYDRIA";

    const normalizedLines =
      Array.isArray(ticket.lignes) && ticket.lignes.length
        ? ticket.lignes
        : [
            {
              quantity: ticket.quantity ?? 1,
              pu: ticket.pu ?? ticket.montant ?? 0,
              montant: ticket.montant ?? 0,
            },
          ];

    const sourceType = ticket.source_type || ticket.sourceType || "";
    const isForfaitaire = sourceType === "paiement_forfaitaire" || ticket.isBonPaiement;
    const totalLines = normalizedLines.reduce(
      (sum, line) => sum + toNumber(line.montant ?? line.pu ?? 0),
      0,
    );

    return {
      numero: ticket.numero_bon || ticket.numero || ticket.numero_bon_avance || "",
      date: formatDate(ticket.date || ticket.date_planning),
      employe: ticket.employe || ticket.employe_surnom || "",
      ouvrage: ticket.ouvrage || ticket.ouvrage_nom || "",
      pointEau: ticket.point_eau || ticket.point_eau_code || "",
      numeroAbonne: ticket.point_eau_idxls || ticket.numero_abonne || ticket.point_eau_code || "",
      nomAbonne: ticket.nom_abonne || "",
      organisation: organisationName,
      logoUrl: ticket.logo_url || fallbackOrganisation.logo_url || "",
      nif: ticket.nif || fallbackOrganisation.nif || "",
      stat: ticket.stat || fallbackOrganisation.stat || "",
      base: ticket.base || ticket.base_nom || fallbackOrganisation.base || "",
      baseTelephone:
        fallbackBaseTelephone ||
        ticket.base_telephone ||
        ticket.baseTelephone ||
        "",
      telephone: ticket.telephone || fallbackOrganisation.telephone || "",
      compte: ticket.compte || ticket.compte_nom || "",
      montant: totalLines || toNumber(ticket.montant),
      fraisMvola: ticket.frais_mvola ?? ticket.fraisMvola ?? "",
      isForfaitaire,
      forfaitaireTranchesHeader:
        ticket.forfaitaire_tranches_header || ticket.forfaitaireTranchesHeader || "",
      forfaitaireProchaineDate:
        formatDate(ticket.forfaitaire_prochaine_date || ticket.forfaitaireProchaineDate || ""),
      forfaitaireProchaineMontant: toNumber(
        ticket.forfaitaire_prochaine_montant ?? ticket.forfaitaireProchaineMontant ?? 0,
      ),
      docTitle: isForfaitaire ? "FAKTIORA FANDOAVAM-BOLA FORFAITAIRE" : "TARATASY FANAMARINANA FANDRAISAM-BOLA",
      lines: normalizedLines.map((line) => ({
        designation: line.designation || ticket.designation || "Paiement forfaitaire",
        quantity: toNumber(line.quantity ?? 1),
        pu: toNumber(line.pu ?? line.montant ?? 0),
        montant: toNumber(line.montant ?? ticket.montant ?? 0),
      })),
    };
  }

  function renderLineItems(ticket) {
    return ticket.lines
      .map(
        (line) => `
          <tr>
            <td class="text-center">${formatQuantity(line.quantity)}</td>
            <td class="text-right">${formatAmount(line.pu)}</td>
            <td class="text-right">${formatAmount(line.montant)}</td>
          </tr>
        `,
      )
      .join("");
  }

  function renderInfoCell(label, value) {
    return `
      <span>
        <strong>${escapeHtml(label)}:</strong> ${escapeHtml(value || "-")}
      </span>
    `;
  }

  function renderCompactCopy(ticket, editionDate) {
    const baseNom = escapeHtml(ticket.base || "");
    const baseTelephone = escapeHtml(ticket.baseTelephone || ticket.telephone || "");
    const logoBlock = ticket.logoUrl
      ? `
          <div class="logo-wrap">
            <img src="${escapeHtml(ticket.logoUrl)}" alt="Logo">
          </div>
        `
      : "";

    return `
      <section class="invoice-copy">
        <div class="invoice-header">
          <div class="header-left">
            ${logoBlock}
            ${
              baseNom || baseTelephone
                ? `
                  <div class="base-meta">
                    ${baseNom ? `<span class="base-label">${baseNom}</span>` : ""}
                    ${baseTelephone ? `<span class="base-phone">Tel: ${baseTelephone}</span>` : ""}
                  </div>
                `
                : ""
            }
          </div>
          <div class="header-right">
            <div class="doc-type">${escapeHtml(ticket.docTitle)}</div>
            ${ticket.numero ? `<div class="invoice-number">${escapeHtml(ticket.numero)}</div>` : ""}
             <div class="invoice-edition">Navoaka ny ${escapeHtml(editionDate)}</div>
          </div>
        </div>

        ${
          ticket.isForfaitaire && ticket.forfaitaireTranchesHeader
            ? `
              <div class="forfaitaire-tranche-banner">${escapeHtml(ticket.forfaitaireTranchesHeader)}</div>
            `
            : ""
        }

        <div class="info-row info-row--top">
          ${renderInfoCell("Daty", ticket.date)}
          ${renderInfoCell("Anaran'ny mpanjifa", ticket.nomAbonne || ticket.pointEau)}
          ${renderInfoCell("Fotodrafitrasa", ticket.ouvrage)}
          ${renderInfoCell("Mpiasa", ticket.employe)}
        </div>

        <div class="info-row info-row--bottom">
          ${renderInfoCell("N° BF", ticket.pointEau)}
          ${renderInfoCell("Fikambanana", ticket.organisation)}
        </div>

        <table class="invoice-table">
          <thead>
            <tr>
              <th class="text-center">Isa</th>
              <th class="text-right">P.U.</th>
              <th class="text-right">Vola</th>
            </tr>
          </thead>
          <tbody>
            ${renderLineItems(ticket)}
          </tbody>
        </table>

        ${
          ticket.isForfaitaire && ticket.forfaitaireProchaineDate && ticket.forfaitaireProchaineMontant > 0
            ? `
              <div class="forfaitaire-next">
                <strong>Fandoavam-bola manaraka :</strong>
                ${escapeHtml(ticket.forfaitaireProchaineDate)} - ${escapeHtml(formatAmount(ticket.forfaitaireProchaineMontant))}
              </div>
            `
            : ""
        }

        ${renderMvolaPaymentNotice(ticket.numeroAbonne, ticket.ouvrage, ticket.fraisMvola)}

        <div class="invoice-footer">
          <div class="signatures">
            <div class="signature-box">
              <span>Mpanjifa</span>
              <div class="signature-line"></div>
            </div>
            <div class="signature-box">
              <span>Mpiasa</span>
              <div class="signature-line"></div>
            </div>
          </div>
          <div class="total-box">
            <span>Fitambarany</span>
            <strong>${formatAmount(ticket.montant)}</strong>
          </div>
        </div>
      </section>
    `;
  }

  function buildRecettesAvancesA4Html(tickets, organisation, options) {
    const printOptions = options || {};
    const normalizedTickets = (tickets || []).map((ticket) =>
      normalizeTicket(ticket, organisation || {}),
    );
    const printableCopies = normalizedTickets.flatMap((ticket) =>
      Array.from({ length: ticket.isForfaitaire ? 2 : 1 }, () => ticket),
    );
    const editionDate = new Date().toLocaleDateString("fr-FR");
    const sheets = chunkArray(printableCopies, 4);
    const toolbar =
      printOptions.showToolbar === false
        ? ""
        : `
          <div class="print-toolbar">
            <button class="btn-print" onclick="window.print()">Imprimer</button>
            <button class="btn-close" onclick="window.close()">Fermer</button>
          </div>
        `;

    const sheetsHtml = sheets
      .map((sheetCopies) => {
        const placeholders = Math.max(0, 4 - sheetCopies.length);
        const copiesHtml =
          sheetCopies.map((ticket) => renderCompactCopy(ticket, editionDate)).join("") +
          Array.from({ length: placeholders })
            .map(() => `<section class="invoice-copy invoice-copy--placeholder"></section>`)
            .join("");

        return `
          <section class="sheet">
            ${copiesHtml}
          </section>
        `;
      })
      .join("");

    const autoPrintScript = printOptions.autoPrint
      ? `
        <script>
          window.addEventListener('load', function () {
            setTimeout(function () {
              window.print();
            }, 250);
          });
        <\/script>
      `
      : "";

    return `
      <!DOCTYPE html>
      <html lang="fr">
        <head>
          <meta charset="UTF-8">
          <title>Factures A4 - Avances et forfaitaires</title>
          <style>
            :root {
              --sheet-width: 18cm;
              --sheet-height: 26.7cm;
              --sheet-safe-height: 25.95cm;
              --copy-gap: 0.18cm;
              --sheet-top-safe: 0.08cm;
              --sheet-bottom-safe: 0.32cm;
              --border-color: #1f2937;
              --soft-border: #d7dee8;
              --muted: #6b7280;
            }

            * { box-sizing: border-box; }

            @page {
              size: A4 portrait;
              margin: 1.5cm;
            }

            @media print {
              body {
                padding: 0;
                background: #ffffff;
              }

              .print-toolbar {
                display: none !important;
              }

              .sheet {
                page-break-after: always;
                margin: 0 auto;
              }

              .sheet:last-child {
                page-break-after: auto;
              }
            }

            body {
              margin: 0;
              padding: 16px 0 32px;
              font-family: Arial, sans-serif;
              background: #eef2f7;
              color: #111827;
            }

            .print-toolbar {
              position: fixed;
              top: 16px;
              right: 16px;
              z-index: 1000;
              display: flex;
              gap: 10px;
              padding: 10px;
              border: 1px solid #d1d5db;
              border-radius: 10px;
              background: rgba(255, 255, 255, 0.96);
              box-shadow: 0 12px 28px rgba(15, 23, 42, 0.15);
            }

            .print-toolbar button {
              border: none;
              border-radius: 8px;
              padding: 10px 14px;
              font-size: 13px;
              font-weight: 700;
              cursor: pointer;
            }

            .btn-print {
              background: #2563eb;
              color: #ffffff;
            }

            .btn-close {
              background: #dc2626;
              color: #ffffff;
            }

            .sheet {
              width: var(--sheet-width);
              min-height: var(--sheet-height);
              margin: 0 auto 16px;
              padding-top: var(--sheet-top-safe);
              padding-bottom: var(--sheet-bottom-safe);
              display: flex;
              flex-direction: column;
              gap: var(--copy-gap);
            }

            .invoice-copy {
              height: calc((var(--sheet-safe-height) - (3 * var(--copy-gap))) / 4);
              border: 1.2px solid var(--border-color);
              background: #ffffff;
              padding: 0.18cm 0.24cm;
              display: flex;
              flex-direction: column;
              justify-content: space-between;
            }

            .invoice-copy--placeholder {
              visibility: hidden;
            }

            .invoice-header {
              display: flex;
              justify-content: space-between;
              align-items: center;
              gap: 10px;
              padding-bottom: 2px;
              margin-bottom: 1px;
              border-bottom: 1px solid var(--border-color);
            }

            .header-left {
              display: flex;
              align-items: center;
              gap: 8px;
              min-width: 0;
            }

            .logo-wrap {
              width: 1.3cm;
              height: 0.85cm;
              display: flex;
              align-items: center;
              justify-content: center;
            }

            .logo-wrap img {
              max-width: 100%;
              max-height: 100%;
              object-fit: contain;
            }

            .base-meta {
              display: flex;
              flex-direction: column;
              gap: 1px;
              min-width: 0;
            }

            .base-label {
              font-size: 9px;
              font-weight: 700;
              color: #374151;
            }

            .base-phone {
              font-size: 8px;
              color: var(--muted);
            }

            .header-right {
              text-align: right;
            }

            .doc-type {
              font-size: 8px;
              color: var(--muted);
              letter-spacing: 0.06em;
              text-transform: uppercase;
              font-weight: 700;
            }

            .invoice-number {
              font-size: 9px;
              font-weight: 700;
              line-height: 1.1;
              margin-top: 1px;
            }

            .invoice-edition {
              font-size: 8px;
              color: var(--muted);
              margin-top: 2px;
            }

            .info-row {
              display: grid;
              gap: 2px 8px;
              font-size: 8.7px;
              line-height: 1.15;
              margin-bottom: 1px;
            }

            .info-row--top {
              grid-template-columns: repeat(4, minmax(0, 1fr));
            }

            .info-row--bottom {
              grid-template-columns: repeat(3, minmax(0, 1fr));
            }

            .info-row span {
              min-width: 0;
              white-space: nowrap;
              overflow: hidden;
              text-overflow: ellipsis;
            }

            .forfaitaire-tranche-banner {
              margin: 3px 0 2px;
              padding: 3px 6px;
              border: 1px solid var(--border-color);
              background: #eff6ff;
              font-size: 9px;
              font-weight: 700;
              text-align: center;
              text-transform: uppercase;
              letter-spacing: 0.04em;
            }

            .invoice-table {
              width: 100%;
              border-collapse: collapse;
              margin-bottom: 2px;
            }

            .invoice-table th,
            .invoice-table td {
              border: 1px solid var(--soft-border);
              padding: 2px 4px;
              font-size: 8.6px;
              line-height: 1.15;
            }

            .invoice-table th {
              background: #e2e8f0;
              text-align: left;
            }

            .text-center { text-align: center; }
            .text-right { text-align: right; }

            .forfaitaire-next {
              margin-bottom: 3px;
              padding: 3px 6px;
              border: 1px solid var(--soft-border);
              background: #f8fafc;
              font-size: 8.4px;
              line-height: 1.2;
            }

            .mvola-payment-notice {
              display: flex;
              align-items: center;
              gap: 5px;
              margin-bottom: 3px;
              padding: 3px 5px;
              border: 1px solid #317041;
              border-radius: 4px;
              background: #f3faf5;
              color: #183d25;
              font-size: 8px;
              line-height: 1.15;
              page-break-inside: avoid;
            }

            .mvola-payment-logo {
              display: block;
              width: 1.45cm;
              max-height: 0.46cm;
              flex: 0 0 1.45cm;
              object-fit: contain;
            }

            .invoice-footer {
              display: flex;
              justify-content: space-between;
              align-items: flex-end;
              gap: 10px;
            }

            .signatures {
              flex: 1;
              display: grid;
              grid-template-columns: repeat(2, minmax(0, 1fr));
              gap: 8px;
            }

            .signature-box span {
              display: block;
              font-size: 8px;
              font-weight: 700;
              margin-bottom: 10px;
            }

            .signature-line {
              border-top: 1px solid var(--border-color);
            }

            .total-box {
              min-width: 2.6cm;
              text-align: right;
            }

            .total-box span {
              display: block;
              font-size: 8px;
              color: var(--muted);
              text-transform: uppercase;
              letter-spacing: 0.05em;
            }

            .total-box strong {
              display: block;
              margin-top: 2px;
              font-size: 12px;
            }
          </style>
        </head>
        <body>
          ${toolbar}
          ${sheetsHtml}
          ${autoPrintScript}
        </body>
      </html>
    `;
  }

  function imprimerTicketsRecettesA4(tickets, organisation, options) {
    const printWindow = window.open("", "_blank", "width=1200,height=900");

    if (!printWindow) {
      alert("La fenetre d'impression a ete bloquee par le navigateur.");
      return;
    }

    const html = buildRecettesAvancesA4Html(tickets, organisation, options);
    printWindow.document.open();
    printWindow.document.write(html);
    printWindow.document.close();
  }

  window.buildRecettesAvancesA4Html = buildRecettesAvancesA4Html;
  window.imprimerTicketsRecettesA4 = imprimerTicketsRecettesA4;
})();
