param(
    [string]$BaseUrl = "http://localhost:8000",
    [Parameter(Mandatory = $true)][string]$OuvrageId,
    [Parameter(Mandatory = $true)][string]$TypeEquipementCiterneId,
    [Parameter(Mandatory = $true)][string]$DesignationId,
    [Parameter(Mandatory = $true)][string]$PosteMainOeuvreId,
    [Parameter(Mandatory = $true)][string]$TacheronId,
    [string]$BesoinId = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Invoke-Api {
    param(
        [ValidateSet("GET", "POST")] [string]$Method,
        [string]$Path,
        [object]$Body = $null
    )

    $url = "$BaseUrl$Path"
    if ($Method -eq "GET") {
        return Invoke-RestMethod -Method GET -Uri $url
    }

    $json = if ($null -eq $Body) { "{}" } else { $Body | ConvertTo-Json -Depth 10 }
    return Invoke-RestMethod -Method POST -Uri $url -ContentType "application/json" -Body $json
}

function Ensure-Success {
    param(
        [object]$Response,
        [string]$Step
    )
    if (-not $Response.success) {
        throw "Echec [$Step]: $($Response.error)"
    }
}

$timestamp = Get-Date -Format "yyyyMMddHHmmss"
$workflowCode = "WF-PS-$timestamp"

Write-Host "=== Workflow Chantiers API Run ==="
Write-Host "BaseUrl: $BaseUrl"
Write-Host "Workflow code: $workflowCode"

# 1) Create workflow
$r = Invoke-Api -Method POST -Path "/chantiers/api/workflows/create/" -Body @{
    code       = $workflowCode
    ouvrage_id = $OuvrageId
    notes      = "Run script PowerShell"
}
Ensure-Success -Response $r -Step "create workflow"
$workflowId = $r.id
Write-Host "WorkflowId: $workflowId"

# 2) Add selection (citerne)
$r = Invoke-Api -Method POST -Path "/chantiers/api/workflows/$workflowId/selections/add/" -Body @{
    type_equipement_id      = $TypeEquipementCiterneId
    quantite                = 1
    citerne_dimensionnement = @{
        volume_cible_m3      = 2
        diametre_interieur_m = 1.6
        hauteur_eau_m        = 1.0
    }
}
Ensure-Success -Response $r -Step "add selection"
Write-Host "SelectionId: $($r.selection_id)"

# 3) Generate besoins
$r = Invoke-Api -Method POST -Path "/chantiers/api/workflows/$workflowId/generate-besoins/" -Body @{
    reset_auto = $true
}
Ensure-Success -Response $r -Step "generate besoins"
Write-Host "Besoins générés: $($r.created)"

# 4) Add surplus
$r = Invoke-Api -Method POST -Path "/chantiers/api/workflows/$workflowId/surplus/add/" -Body @{
    type_ligne    = "designation"
    designation_id = $DesignationId
    quantite      = 2
    prix_unitaire = 1000
    justification = "Ajout manuel script"
}
Ensure-Success -Response $r -Step "add surplus designation"

$r = Invoke-Api -Method POST -Path "/chantiers/api/workflows/$workflowId/surplus/add/" -Body @{
    type_ligne          = "main_oeuvre"
    poste_main_oeuvre_id = $PosteMainOeuvreId
    quantite            = 1
    prix_unitaire       = 50000
    justification       = "MO manuelle script"
}
Ensure-Success -Response $r -Step "add surplus main oeuvre"

# 5) Integrate surplus + generate devis
$r = Invoke-Api -Method POST -Path "/chantiers/api/workflows/$workflowId/surplus/integrate/" -Body @{
    reset_surplus = $true
}
Ensure-Success -Response $r -Step "integrate surplus"
Write-Host "Surplus intégrés: $($r.created)"

$r = Invoke-Api -Method POST -Path "/chantiers/api/workflows/$workflowId/devis/generate/" -Body @{}
Ensure-Success -Response $r -Step "generate devis"
$devisNumero = $r.numero
Write-Host "Devis: $devisNumero montant=$($r.montant)"

# 6) Contrat + avenant + facture tranche
$r = Invoke-Api -Method POST -Path "/chantiers/api/workflows/$workflowId/contrat/create/" -Body @{
    numero        = "CTR-$workflowCode-001"
    tacheron_id   = $TacheronId
    montant       = 2000000
    date_document = "2026-02-22"
}
Ensure-Success -Response $r -Step "create contrat"
$contratDocumentId = $r.document_id

$r = Invoke-Api -Method POST -Path "/chantiers/api/workflows/$workflowId/avenant/create/" -Body @{
    numero              = "AV-$workflowCode-001"
    contrat_document_id = $contratDocumentId
    montant             = 150000
    date_document       = "2026-02-22"
}
Ensure-Success -Response $r -Step "create avenant"
$avenantDocumentId = $r.document_id

$r = Invoke-Api -Method POST -Path "/chantiers/api/workflows/$workflowId/facture-tranche/create/" -Body @{
    numero             = "FTR-$workflowCode-001"
    parent_document_id = $avenantDocumentId
    montant            = 700000
    date_document      = "2026-02-22"
}
Ensure-Success -Response $r -Step "create facture tranche"
$factureDocumentId = $r.document_id

$r = Invoke-Api -Method POST -Path "/chantiers/api/workflows/$workflowId/documents/$factureDocumentId/statut/" -Body @{
    statut = "valide"
}
Ensure-Success -Response $r -Step "update facture statut"

# 7) Determine besoin id if not provided
if ([string]::IsNullOrWhiteSpace($BesoinId)) {
    $rb = Invoke-Api -Method GET -Path "/chantiers/api/workflows/$workflowId/besoins/"
    Ensure-Success -Response $rb -Step "list besoins"
    if (-not $rb.results -or $rb.results.Count -eq 0) {
        throw "Aucun besoin disponible pour les mouvements."
    }
    $BesoinId = $rb.results[0].id
    Write-Host "BesoinId auto sélectionné: $BesoinId"
}

# 8) Mouvements
$mouvements = @(
    @{ type_mouvement = "commande"; quantite = 10; reference_document = "BC-001" },
    @{ type_mouvement = "livraison"; quantite = 8; reference_document = "BL-001" },
    @{ type_mouvement = "utilisation"; quantite = 7; reference_document = "UT-001" },
    @{ type_mouvement = "retour"; quantite = 1; reference_document = "RT-001" },
    @{ type_mouvement = "recollement"; quantite = 7.2; reference_document = "REC-001" }
)

foreach ($m in $mouvements) {
    $r = Invoke-Api -Method POST -Path "/chantiers/api/workflows/$workflowId/mouvements/add/" -Body @{
        besoin_id          = $BesoinId
        type_mouvement     = $m.type_mouvement
        quantite           = $m.quantite
        reference_document = $m.reference_document
    }
    Ensure-Success -Response $r -Step "add mouvement $($m.type_mouvement)"
}

# 9) Recollement + devis final + suivi contrat
$r = Invoke-Api -Method GET -Path "/chantiers/api/workflows/$workflowId/recollement/synthese/"
Ensure-Success -Response $r -Step "recollement synthese"
$totalValeurFinale = $r.totaux.valeur_finale

$r = Invoke-Api -Method POST -Path "/chantiers/api/workflows/$workflowId/devis-final/generate/" -Body @{}
Ensure-Success -Response $r -Step "generate devis final"
$devisFinalNumero = $r.numero

$r = Invoke-Api -Method GET -Path "/chantiers/api/workflows/$workflowId/contrat/suivi/"
Ensure-Success -Response $r -Step "contrat suivi"

Write-Host ""
Write-Host "=== Résumé ==="
Write-Host "WorkflowId: $workflowId"
Write-Host "Devis: $devisNumero"
Write-Host "Devis final: $devisFinalNumero"
Write-Host "Valeur finale récolement: $totalValeurFinale"
Write-Host "Suivi contrat (reste à facturer): $($r.totaux.reste_a_facturer)"
