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
    return `${Math.round(toNumber(value)).toLocaleString("fr-FR")} Ar`;
  }

  function formatVolume(value) {
    return `${toNumber(value).toLocaleString("fr-FR", {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    })} m3`;
  }

  function formatIndexValue(value) {
    return toNumber(value).toLocaleString("fr-FR", {
      minimumFractionDigits: 0,
      maximumFractionDigits: 2,
    });
  }

  function buildMvolaPaymentReason(numeroAbonne, ouvrageNom) {
    return `${String(numeroAbonne || "").trim()}${String(ouvrageNom || "").trim()}`
      .replace(/\s+/g, "");
  }

  function renderMvolaPaymentNotice(fraisMvola, numeroAbonne, ouvrageNom) {
    const fraisLabel = fraisMvola !== null && fraisMvola !== undefined && Number.isFinite(Number(fraisMvola))
      ? ` <strong>( Frais paiement MVola: ${escapeHtml(formatAmount(fraisMvola))})</strong>`
      : "";
    const raisonPaiement = escapeHtml(buildMvolaPaymentReason(numeroAbonne, ouvrageNom));
    return `
      <div class="mvola-payment-notice">
        <img src="/static/images/mvola-logo.svg" alt="MVola" class="mvola-payment-logo">
        <span>Afaka aloha MVola amin'ity numero ity ny vola : <strong>034 74 699 64</strong> amin'ny anaran'i <strong>Herizo nandrianintsoa</strong> Raison : <strong>${raisonPaiement}</strong>${fraisLabel}</span>
      </div>
    `;
  }

  function isNonZero(value) {
    return Math.abs(toNumber(value)) > 0.000001;
  }

  function formatMonthLabel(value) {
    const date = value ? new Date(value) : new Date();
    if (Number.isNaN(date.getTime())) {
      return "";
    }
    return date.toLocaleDateString("fr-FR", {
      month: "long",
      year: "numeric",
    });
  }

  function chunk(items, size) {
    const result = [];
    for (let i = 0; i < items.length; i += size) {
      result.push(items.slice(i, i + size));
    }
    return result;
  }

  function formatTrancheOrdinal(index) {
    return index === 0 ? "1ère tranche" : `${index + 1}e tranche`;
  }

  function getPointEauTypeMarkup(typeNom) {
    const rawType = String(typeNom || "").trim();
    const upperType = rawType.toUpperCase();
    let icon = "";

    if (upperType.includes("KIOSQUE")) {
      icon = `
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <path d="M4 9h16v10H4z"></path>
          <path d="M3 9l2-4h14l2 4"></path>
          <path d="M8 19v-4h8v4"></path>
        </svg>
      `;
    } else if (upperType.includes("BP") || upperType.includes("BRANCHEMENT") || upperType.includes("PRIVE") || upperType.includes("PRIVÉ")) {
      icon = `
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <path d="M4 20h16"></path>
          <path d="M6 20V10l6-5 6 5v10"></path>
          <path d="M10 20v-5h4v5"></path>
        </svg>
      `;
    } else if (upperType.includes("BI") || upperType.includes("BORNE")) {
      icon = `
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <path d="M7 20v-8"></path>
          <path d="M7 12h7a3 3 0 0 0 3-3V7"></path>
          <path d="M17 7h-4"></path>
          <path d="M17 9v3"></path>
          <path d="M17 14c0 1.5-1 2.5-2 3"></path>
        </svg>
      `;
    }

    if (!icon && !rawType) {
      return "-";
    }

    return `
      <span class="type-badge">
        ${icon ? `<span class="type-icon">${icon}</span>` : ""}
        <span>${escapeHtml(rawType || "N/A")}</span>
      </span>
    `;
  }

  function renderInvoice(releve, organisationData = {}) {
    const detail = releve.detail_calcul || {};
    const tranches = Array.isArray(detail.tranches) ? detail.tranches : [];
    const ouvrageNom = escapeHtml(releve.ouvrage_nom || "-");
    const dateSource = releve.date_facture || releve.datereleve || releve.date_releve;
    const moisLabel = escapeHtml(formatMonthLabel(dateSource));
    const pointEau = escapeHtml(releve.idxls || releve.point_eau || "-");
    const beneficiaire = escapeHtml(releve.abonne || "-");
    const parcelle = escapeHtml(
      releve.parcelle_display ||
      releve.parcelle ||
      releve.parcelle_numero ||
      releve.numero_parcelle ||
      releve.parcelle_abonne ||
      "-"
    );
    const typePointEau = getPointEauTypeMarkup(releve.type_point_eau);
    const numeroFacture = escapeHtml(releve.numero_facture || `PROV-${String(releve.releve_id || "").slice(0, 8) || "-"}`);
    const qrPayload = String(
      releve.qr_payload ||
      `HYDRIA|FACTURE|${String(releve.releve_id || "").trim()}|${String(releve.numero_facture || "").trim()}|${String(releve.date_facture || "").slice(0, 7)}|${String(releve.ouvrage_id || "").trim()}`
    ).trim();
    const qrCodeUrl = qrPayload
      ? `https://api.qrserver.com/v1/create-qr-code/?size=140x140&margin=0&data=${encodeURIComponent(qrPayload)}`
      : "";
    const organisationNom = escapeHtml(organisationData.nom || "HYDRIA");
    const organisationLogoUrl = String(organisationData.logo_url || "").trim();
    const responsableNom = escapeHtml(
      releve.responsable_ouvrage_nom ||
      organisationData.responsable_ouvrage_nom ||
      "-"
    );
    const responsableTelephone = escapeHtml(
      releve.responsable_ouvrage_telephone ||
      organisationData.responsable_ouvrage_telephone ||
      ""
    );
    const organisationMetaParts = [
      organisationData.base_telephone ? `Tel: ${escapeHtml(organisationData.base_telephone)}` : "",
      organisationData.nif ? `NIF: ${escapeHtml(organisationData.nif)}` : "",
      organisationData.stat ? `STAT: ${escapeHtml(organisationData.stat)}` : "",
      organisationData.adresse ? `${escapeHtml(organisationData.adresse)}` : "",
    ].filter(Boolean);
    const organisationMetaHtml = organisationMetaParts.length
      ? `<div class="org-meta">${organisationMetaParts.map((item) => `<div class="org-meta-line">${item}</div>`).join("")}</div>`
      : "";
    const organisationHeader = `
      <div class="org-header">
        ${organisationLogoUrl
          ? `<img src="${escapeHtml(organisationLogoUrl)}" alt="${organisationNom}" class="org-logo">`
          : `<div class="org-name">${organisationNom}</div>`
        }
        <div class="org-side">
          ${organisationMetaHtml}
          <div class="responsable-box">
            <div class="responsable-label">Agent responsable</div>
            <div class="responsable-name">${responsableNom}</div>
            ${responsableTelephone ? `<div class="responsable-phone">Tel: ${responsableTelephone}</div>` : ""}
          </div>
        </div>
      </div>
    `;
    const volumeCarteSocialeValue = detail.volume_carte_sociale ?? releve.volume_carte_sociale ?? 0;
    const volumeNonFactureValue = detail.volume_non_facture ?? releve.volume_non_facture ?? 0;
    const indexDepart = escapeHtml(formatIndexValue(releve.ancienindex ?? releve.ancien_index ?? 0));
    const indexArrive = escapeHtml(formatIndexValue(releve.nouvelindex ?? releve.nouvel_index ?? 0));
    const volumeConsomme = escapeHtml(formatVolume(detail.volume_consomme ?? releve.volume_consomme ?? 0));
    const volumeCarteSociale = escapeHtml(formatVolume(volumeCarteSocialeValue));
    const volumeNonFacture = escapeHtml(formatVolume(volumeNonFactureValue));
    const volumeFacture = escapeHtml(formatVolume(detail.volume_facture ?? releve.volume_facture ?? 0));
    const segmentsCompteur = Array.isArray(releve.segments_compteur) ? releve.segments_compteur : [];
    const segmentsCompteurHtml = segmentsCompteur.length > 1
      ? `<div class="meta-item meta-item-full">
          <span class="meta-label">Details du changement de compteur</span>
          <span class="meta-value">${segmentsCompteur.map((segment) =>
            `${escapeHtml(segment.compteur_numero)}: ${escapeHtml(formatIndexValue(segment.index_debut))} -> ${escapeHtml(formatIndexValue(segment.index_fin))} = <strong>${escapeHtml(formatVolume(segment.volume))}</strong>${segment.est_estime ? ' (estime)' : ''}`
          ).join(' | ')}</span>
        </div>`
      : "";
    const abonnement = escapeHtml(formatAmount(detail.abonnement ?? 0));
    const montantVolume = escapeHtml(formatAmount(detail.montant_volume ?? 0));
    const taxeCommunale = escapeHtml(formatAmount(detail.taxe_communale ?? 0));
    const impotSynthetique = escapeHtml(formatAmount(toNumber(detail.montant_ht ?? 0) * 0.05));
    const montant = escapeHtml(
      formatAmount(
        releve.montant_calcule ??
        releve.montant_enregistre ??
        releve.montant ??
        detail.montant_arrondi ??
        0,
      ),
    );
    const tranchesHtml = tranches.length
      ? tranches
          .map((tranche, index) => `
            <tr class="tranche-row">
              <td class="tranche-label">
                <span class="tranche-inline-title">${formatTrancheOrdinal(index)} - ${escapeHtml(tranche.tranche || "-")}</span>
              </td>
              <td class="tranche-calc">
                ${escapeHtml(formatVolume(tranche.volume ?? 0))} x ${escapeHtml(formatAmount(tranche.tarif_unitaire ?? 0)).replace(" Ar", "")}/m3
              </td>
              <td>${escapeHtml(formatAmount(tranche.montant ?? 0))}</td>
            </tr>
          `)
          .join("")
      : `
        <tr class="tranche-row tranche-empty">
          <td class="tranche-label">Aucune tranche detaillee</td>
          <td class="tranche-calc">-</td>
          <td>-</td>
        </tr>
      `;
    const volumeCarteSocialeRow = isNonZero(volumeCarteSocialeValue)
      ? `<tr><td>Volume carte sociale</td><td>${volumeCarteSociale}</td></tr>`
      : "";
    const volumeNonFactureRow = isNonZero(volumeNonFactureValue)
      ? `<tr><td>Volume non facture</td><td>${volumeNonFacture}</td></tr>`
      : "";

    return `
      <section class="invoice">
        <aside class="stub">
          <div class="stub-kicker">TAPAKILA</div>
          <div class="stub-grid">
            <div class="stub-cell stub-cell-full">${moisLabel}</div>
            <div class="stub-cell">N°${numeroFacture}</div>
            <div class="stub-cell">${ouvrageNom}</div>
          </div>
          ${qrCodeUrl ? `
            <div class="stub-qr-box">
              <img src="${escapeHtml(qrCodeUrl)}" alt="QR facture ${numeroFacture}" class="stub-qr-image">
              <div class="stub-qr-caption">Scanner a l'encaissement</div>
            </div>
          ` : ""}
          <div class="stub-cell">${beneficiaire} / ${typePointEau} ${pointEau}</div>
          <div class="stub-cell"><strong>Volume </strong>${volumeFacture}</div>
          <div class="stub-amount-label">Vola aloa</div>
          <div class="stub-amount">${montant}</div>
          <div class="stub-payment-date">
            <span class="stub-payment-date-label">Daty nandoavam-bola</span>
            <span class="stub-payment-date-line"></span>
          </div>
          <div class="stub-signature-label">Sonian'ny mpandoa vola</div>
          <div class="stub-signature-line"></div>
        </aside>

        <div class="main">
          <div class="main-header">
            <div class="main-header-left">
              <div class="org-block">${organisationHeader}</div>
              <div>
                <div class="main-title">FAKTIORA</div>
                <div class="main-subtitle">${moisLabel}</div>
              </div>
            </div>
            <div class="main-number">N° ${numeroFacture}</div>
          </div>

          <div class="meta-grid meta-grid-top">
            <div class="meta-item">
              <span class="meta-label">Fotodrafitrasa</span>
              <span class="meta-value">${ouvrageNom}</span>
            </div>
            ${segmentsCompteurHtml}
            <div class="meta-item meta-item-value-only">
              <span class="meta-value meta-beneficiaire">${beneficiaire} / ${typePointEau} ${pointEau}</span>
            </div>
            <div class="meta-item">
              <span class="meta-label">Parcelle / Index depart / Index arrive / Habetsahana aloa</span>
              <span class="meta-value">${parcelle} / ${indexDepart} / ${indexArrive} / <strong>${volumeFacture}</strong></span>
            </div>
            ${isNonZero(volumeCarteSocialeValue) ? `
              <div class="meta-item">
                <span class="meta-label">Habetsahana carte sociale</span>
                <span class="meta-value">${volumeCarteSociale}</span>
              </div>` : ""}
            ${isNonZero(volumeNonFactureValue) ? `
              <div class="meta-item">
                <span class="meta-label">Habetsahana tsy aloa</span>
                <span class="meta-value">${volumeNonFacture}</span>
              </div>` : ""}
          </div>

          <table class="total-table">
            <tr><td>Abonnement</td><td></td><td>${abonnement}</td></tr>
            <tr><td>Sandan'ny rano</td><td></td><td>${montantVolume}</td></tr>
            ${tranchesHtml}
            <tr class="grand-total"><td>Totaly aloa</td><td></td><td class="grand-total-amount">${montant}</td></tr>
          </table>

          ${renderMvolaPaymentNotice(detail.frais_mvola, releve.idxls || releve.point_eau, releve.ouvrage_nom)}

          <div class="agent-dates-box">
            <div class="agent-dates-title">R&eacute;serv&eacute; &agrave; l'agent</div>
            <div class="agent-dates-fields">
              <div class="agent-date-field">
                <span>Daty nandraisan'ny mpanjifa ny faktiora</span>
                <span class="agent-date-line"></span>
              </div>
              <div class="agent-date-field">
                <span>Daty fandoavana farany</span>
                <span class="agent-date-line"></span>
              </div>
              <div class="agent-date-field">
                <span>Daty nandoavam-bola</span>
                <span class="agent-date-line"></span>
              </div>
            </div>
          </div>
        </div>
      </section>
    `;
  }

  function resolveOuvrageNom(relevesCalcules, ouvrageNom) {
    const directName = String(ouvrageNom || "").trim();
    if (directName) {
      return directName;
    }

    const releveName = String(relevesCalcules?.[0]?.ouvrage_nom || "").trim();
    if (releveName) {
      return releveName;
    }

    return "Factures";
  }

  function buildWindowHtml(relevesCalcules, ouvrageNom, organisationData = {}) {
    const ouvrageLabel = resolveOuvrageNom(relevesCalcules, ouvrageNom);
    const sheetsHtml = chunk(relevesCalcules, 5)
      .map((items) => `
        <section class="sheet">
          <div class="sheet-title">${escapeHtml(ouvrageLabel)}</div>
          ${items.map((item) => renderInvoice(item, organisationData)).join("")}
        </section>
      `)
      .join("");

    return `<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="UTF-8">
  <meta name="color-scheme" content="light">
  <title>Factures</title>
  <style>
    * { box-sizing: border-box; }
    html, body {
      margin: 0;
      padding: 0;
      background: #fff;
      color: #000;
      font-family: Arial, sans-serif;
    }
    @page {
      size: A4 portrait;
      margin: 8mm;
    }
    @media print {
      .toolbar { display: none !important; }
      .sheet { page-break-after: always; }
      .sheet:last-child { page-break-after: auto; }
      .invoice {
        break-inside: avoid;
        page-break-inside: avoid;
      }
    }
    body {
      padding: 12px 0 24px;
    }
    .toolbar {
      position: fixed;
      top: 12px;
      right: 12px;
      z-index: 10;
      background: #fff;
      border: 1px solid #bbb;
      padding: 8px;
    }
    .toolbar button {
      border: 1px solid #555;
      background: #fff;
      color: #000;
      padding: 6px 10px;
      margin-left: 6px;
      cursor: pointer;
    }
    .sheet {
      width: 19.4cm;
      min-height: 27.8cm;
      margin: 0 auto 10px;
      background: #fff;
    }
    .sheet-title {
      text-align: center;
      font-size: 12px;
      font-weight: 700;
      margin-bottom: 2mm;
    }
    .invoice {
      width: 100%;
      min-height: 4.15cm;
      border: 1px solid #000;
      display: flex;
      margin-bottom: 2mm;
      background: #fff;
      break-inside: avoid;
      page-break-inside: avoid;
    }
    .stub, .main {
      vertical-align: top;
      background: #fff;
    }
    .stub {
      width: 7.2cm;
      flex: 0 0 7.2cm;
      border-right: 1px dashed #666;
      padding: 1.8mm 2mm;
      display: grid !important;
      grid-template-columns: minmax(0, 1fr) 2.5cm;
      column-gap: 1.8mm;
      align-content: start;
    }
    .main {
      flex: 1;
      padding: 1.8mm 2mm;
    }
    .stub-title {
      font-size: 14px;
      font-weight: 700;
      margin-bottom: 2mm;
    }
    .stub-kicker {
      font-size: 10px;
      letter-spacing: 1px;
      color: #4b5563;
      margin-bottom: 1mm;
      text-transform: uppercase;
      grid-column: 1 / -1;
    }
    .stub-value {
      font-size: 10px;
      margin-bottom: 1.2mm;
      word-break: break-word;
    }
    .stub-grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 1mm 2mm;
      margin-bottom: 1.5mm;
      grid-column: 1;
    }
    .stub-cell {
      font-size: 9px;
      line-height: 1.2;
      word-break: break-word;
      grid-column: 1;
    }
    .stub-cell-full {
      grid-column: 1 / -1;
    }
    .stub-qr-box {
      margin: 0;
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 0.8mm;
      grid-column: 2;
      grid-row: 2 / span 7;
      justify-content: flex-start;
      align-self: start;
    }
    .stub-qr-image {
      display: block;
      width: 22mm;
      height: 22mm;
      object-fit: contain;
      border: 1px solid #d1d5db;
      padding: 0.6mm;
      background: #fff;
    }
    .stub-qr-caption {
      font-size: 7.5px;
      text-align: center;
      line-height: 1.15;
      text-transform: uppercase;
    }
    .stub-amount-label {
      font-size: 9px;
      margin-top: 2mm;
      text-transform: uppercase;
      grid-column: 1;
    }
    .stub-amount {
      font-size: 18px;
      font-weight: 700;
      margin-bottom: 1.5mm;
      grid-column: 1;
    }
    .stub-payment-date {
      grid-column: 1;
      display: flex;
      flex-direction: column;
      gap: 1mm;
      margin: 0.5mm 0 1mm;
    }
    .stub-payment-date-label {
      font-size: 8px;
      font-weight: 700;
      text-transform: uppercase;
    }
    .stub-payment-date-line {
      display: block;
      height: 4mm;
      border-bottom: 1px solid #000;
    }
    .stub-signature-label {
      font-size: 9px;
      text-transform: uppercase;
      margin-top: 1mm;
      margin-bottom: 1mm;
      grid-column: 1;
    }
    .stub-signature-line {
      border-bottom: 1px solid #000;
      height: 8mm;
      grid-column: 1;
    }
    .main-header {
      position: relative;
      display: block;
      border-bottom: 1px solid #ccc;
      margin-bottom: 2mm;
      padding-bottom: 1mm;
      padding-right: 28mm;
    }
    .main-header-left {
      display: contents;
    }
    .org-block {
      width: 100%;
      min-width: 0;
      margin-bottom: 1.2mm;
    }
    .main-header-left > div:last-child {
      display: block;
      margin: 0;
    }
    .org-header {
      display: flex;
      align-items: flex-start;
      gap: 2.5mm;
      margin-bottom: 0;
      width: 100%;
    }
    .org-side {
      display: flex;
      align-items: flex-start;
      gap: 3mm;
      flex: 1 1 auto;
      min-width: 0;
    }
    .org-logo {
      display: block;
      max-width: 22mm;
      max-height: 10mm;
      object-fit: contain;
    }
    .org-meta {
      display: flex;
      flex-direction: column;
      gap: 0.3mm;
      text-align: left;
      font-size: 7px;
      line-height: 1.2;
      color: #374151;
    }
    .org-meta-line {
      white-space: nowrap;
    }
    .responsable-box {
      border-left: 1px solid #d1d5db;
      padding-left: 2.5mm;
      min-width: 32mm;
    }
    .responsable-label {
      font-size: 7px;
      text-transform: uppercase;
      color: #6b7280;
      margin-bottom: 0.5mm;
    }
    .responsable-name {
      font-size: 9px;
      font-weight: 700;
      line-height: 1.15;
    }
    .responsable-phone {
      font-size: 8px;
      margin-top: 0.5mm;
    }
    .org-name {
      font-size: 10px;
      font-weight: 700;
      text-transform: uppercase;
    }
    .main-title {
      font-size: 13px;
      font-weight: 700;
      margin: 0;
    }
    .main-subtitle, .main-number {
      font-size: 10px;
    }
    .main-subtitle {
      margin-top: 0.2mm;
    }
    .main-number {
      position: absolute;
      top: 0;
      right: 0;
      text-align: right;
      white-space: nowrap;
    }
    .total-table {
      width: 100%;
      border-collapse: collapse;
      font-size: 9px;
      margin-bottom: 2mm;
    }
    .total-table td {
      border-bottom: 1px solid #ddd;
      padding: 1mm 0;
    }
    .total-table td:nth-child(2) {
      text-align: right;
      white-space: nowrap;
      color: #4b5563;
      font-size: 7.7px;
      padding-right: 2mm;
    }
    .total-table td:nth-child(3) {
      text-align: right;
      white-space: nowrap;
      color: #374151;
      font-size: 8px;
      padding-right: 2mm;
    }
    .total-table td:last-child {
      text-align: right;
      font-weight: 700;
      white-space: nowrap;
    }
    .meta-grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 1mm 5mm;
      margin-bottom: 2mm;
      font-size: 9px;
    }
    .meta-grid-top {
      grid-template-columns: max-content minmax(0, 1fr);
    }
    .meta-grid-single {
      grid-template-columns: 1fr;
    }
    .meta-item {
      display: grid;
      grid-template-columns: max-content minmax(0, 1fr);
      align-items: flex-start;
      column-gap: 2.2mm;
      row-gap: 0.6mm;
      border-bottom: 1px solid #ddd;
      padding: 0.7mm 0;
      min-width: 0;
    }
    .meta-item-value-only {
      grid-template-columns: minmax(0, 1fr);
    }
    .meta-label {
      color: #111827;
      white-space: nowrap;
    }
    .meta-value {
      text-align: left;
      font-weight: 700;
      min-width: 0;
      word-break: normal;
      overflow-wrap: anywhere;
      white-space: normal;
    }
    .meta-beneficiaire {
      font-size: 13px;
      line-height: 1.15;
      text-align: left;
    }
    .meta-grid-top .meta-item:nth-child(2) {
      grid-column: 2;
    }
    .meta-grid-top .meta-item:nth-child(3) {
      grid-column: 1 / span 2;
    }
    .meta-grid-top .meta-item:nth-child(n+4) {
      grid-column: 1 / span 2;
    }
    .meta-grid-top .meta-item:nth-child(n+7),
    .meta-grid-top .meta-item:nth-child(n+7) .meta-label,
    .meta-grid-top .meta-item:nth-child(n+7) .meta-value {
      color: #8b8b8b;
    }
    .type-badge {
      display: inline-flex;
      align-items: center;
      gap: 4px;
      justify-content: flex-end;
      max-width: 100%;
      white-space: normal;
    }
    .type-icon {
      display: inline-flex;
      width: 14px;
      height: 14px;
      flex: 0 0 14px;
    }
    .type-icon svg {
      width: 14px;
      height: 14px;
      stroke: currentColor;
      fill: none;
      stroke-width: 1.7;
      stroke-linecap: round;
      stroke-linejoin: round;
    }
    .tranche-row td {
      font-size: 8px;
      color: #8b8b8b;
      padding-top: 0.6mm;
      padding-bottom: 0.6mm;
      vertical-align: top;
    }
    .tranche-label {
      padding-left: 3mm !important;
      white-space: normal;
      width: 40%;
    }
    .tranche-inline-title {
      display: block;
      font-weight: 400;
      color: #8b8b8b;
      white-space: normal;
    }
    .tranche-calc {
      width: 35%;
      text-align: right;
      white-space: nowrap;
      color: #8b8b8b;
      font-size: 7.7px;
    }
    .tranche-row td:last-child {
      color: #8b8b8b;
      font-weight: 400;
    }
    .tranche-empty td {
      color: #6b7280;
      font-style: italic;
    }
    .indicative-row td {
      color: #8b8b8b;
    }
    .indicative-row td:last-child {
      color: #8b8b8b;
      font-weight: 400;
    }
    .grand-total td {
      font-size: 12px;
      font-weight: 700;
      border: 1px solid #000;
      padding: 1.2mm 1.5mm;
    }
    .grand-total-amount {
      font-size: 15px !important;
    }
    .mvola-payment-notice {
      display: flex;
      align-items: center;
      gap: 2mm;
      margin: 1mm 0;
      padding: 0.8mm 1.2mm;
      border: 1px solid #317041;
      border-radius: 1.5mm;
      background: #f3faf5;
      color: #183d25;
      font-size: 8px;
      line-height: 1.2;
      page-break-inside: avoid;
    }
    .mvola-payment-logo {
      display: block;
      width: 18mm;
      max-height: 5.5mm;
      flex: 0 0 18mm;
      object-fit: contain;
    }
    .agent-dates-box {
      border: 1px solid #000;
      margin-top: 1.5mm;
      page-break-inside: avoid;
    }
    .agent-dates-title {
      border-bottom: 1px solid #000;
      padding: 0.7mm 1.2mm;
      font-size: 8px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.2px;
      background: #f3f4f6;
    }
    .agent-dates-fields {
      display: grid;
      grid-template-columns: 1.45fr 1fr 1fr;
    }
    .agent-date-field {
      min-width: 0;
      padding: 1mm 1.2mm 0.8mm;
      font-size: 7.5px;
      line-height: 1.15;
    }
    .agent-date-field + .agent-date-field {
      border-left: 1px solid #000;
    }
    .agent-date-line {
      display: block;
      height: 4mm;
      margin-top: 0.7mm;
      border-bottom: 1px dotted #555;
    }
  </style>
</head>
<body>
  <div class="toolbar">
    <button onclick="window.print()">Imprimer</button>
    <button onclick="window.close()">Fermer</button>
  </div>
  ${sheetsHtml}
</body>
</html>`;
  }

  window.imprimerFacturesCompactesA4 = function imprimerFacturesCompactesA4(
    relevesCalcules,
    ouvrageNom,
    organisationData,
  ) {
    const printWindow = window.open("", "_blank", "width=1200,height=900");
    if (!printWindow) {
      alert("La fenetre d'impression a ete bloquee par le navigateur.");
      return;
    }
    printWindow.document.open();
    printWindow.document.write(buildWindowHtml(relevesCalcules, ouvrageNom, organisationData));
    printWindow.document.close();
  };
})();
