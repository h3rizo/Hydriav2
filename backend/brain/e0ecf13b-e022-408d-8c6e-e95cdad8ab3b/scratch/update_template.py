import sys

file_path = r'C:\Users\Dir Soakoja\Documents\Formation appli web\hydria nuxt django\backend\templates\accounting\etat_taxe_communale.html'

with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Update commune header and add reimbursement section
old_header = """                <div class="flex items-center gap-3">
                    <span class="badge badge-outline">{{ item.nb_ouvrages }} ouvrage{{ item.nb_ouvrages|pluralize }}</span>
                    <a href="?annee={{ annee }}&print=true&print_commune_id={{ item.commune.id }}{% if selected_organisation_id %}&organisation_id={{ selected_organisation_id }}{% endif %}{% if selected_region_id %}&region_id={{ selected_region_id }}{% endif %}{% if selected_district_id %}&district_id={{ selected_district_id }}{% endif %}" target="_blank"
                        class="btn btn-sm btn-outline btn-primary" title="Imprimer cette facture">
                        <i class="fas fa-print"></i>
                    </a>
                    <div class="badge badge-lg badge-primary">{{ item.total_taxe|floatformat:0|intcomma }} Ar</div>
                </div>"""

new_header = """                <div class="flex items-center gap-3">
                    <div class="flex flex-col items-end">
                        <span class="text-xs opacity-60">Taxe Finale à payer</span>
                        <div class="badge badge-lg badge-primary font-bold">{{ item.total_taxe|floatformat:0|intcomma }} Ar</div>
                    </div>
                    <span class="badge badge-outline">{{ item.nb_ouvrages }} ouvrage{{ item.nb_ouvrages|pluralize }}</span>
                    <a href="?annee={{ annee }}&print=true&print_commune_id={{ item.commune.id }}{% if selected_organisation_id %}&organisation_id={{ selected_organisation_id }}{% endif %}{% if selected_region_id %}&region_id={{ selected_region_id }}{% endif %}{% if selected_district_id %}&district_id={{ selected_district_id }}{% endif %}" target="_blank"
                        class="btn btn-sm btn-outline btn-primary" title="Imprimer cette facture">
                        <i class="fas fa-print"></i>
                    </a>
                </div>
            </div>

            <!-- Section Remboursements -->
            <div class="bg-base-200 rounded-lg p-4 mt-4">
                <div class="flex justify-between items-center mb-2">
                    <h3 class="font-bold text-sm uppercase tracking-wider text-base-content/70">
                        <i class="fas fa-hand-holding-usd mr-2"></i>
                        Comptes de tiers à rembourser par la commune
                    </h3>
                    <button class="btn btn-xs btn-outline btn-secondary" onclick="openAddRemboursementModal('{{ item.commune.id }}', '{{ item.commune.nom_commune|escapejs }}')">
                        <i class="fas fa-plus mr-1"></i> Ajouter un remboursement
                    </button>
                </div>

                {% if item.remboursements %}
                <div class="overflow-x-auto">
                    <table class="table table-compact w-full bg-base-100">
                        <thead>
                            <tr>
                                <th>Date</th>
                                <th>Désignation</th>
                                <th class="text-right">Montant</th>
                                <th class="text-center">Action</th>
                            </tr>
                        </thead>
                        <tbody>
                            {% for remb in item.remboursements %}
                            <tr>
                                <td class="text-xs">{{ remb.date_remboursement|date:"d/m/Y" }}</td>
                                <td class="text-xs">{{ remb.designation }}</td>
                                <td class="text-right text-xs font-semibold text-secondary">- {{ remb.montant|floatformat:0|intcomma }} Ar</td>
                                <td class="text-center">
                                    <button class="btn btn-ghost btn-xs text-error" onclick="deleteRemboursement('{{ remb.id }}')" title="Supprimer">
                                        <i class="fas fa-trash-alt"></i>
                                    </button>
                                </td>
                            </tr>
                            {% endfor %}
                        </tbody>
                        <tfoot>
                            <tr class="bg-base-300 font-bold">
                                <td colspan="2">TOTAL REMBOURSEMENTS</td>
                                <td class="text-right text-secondary">- {{ item.total_remboursements|floatformat:0|intcomma }} Ar</td>
                                <td></td>
                            </tr>
                        </tfoot>
                    </table>
                </div>
                {% else %}
                <div class="text-center py-2 text-sm opacity-50 italic">
                    Aucun remboursement enregistré pour cette commune en {{ annee }}.
                </div>
                {% endif %}

                <div class="flex justify-end gap-6 mt-3 border-t border-base-300 pt-2">
                    <div class="text-right">
                        <span class="text-xs opacity-60">Taxe Brute :</span>
                        <span class="font-semibold ml-2">{{ item.total_taxe_brute|floatformat:0|intcomma }} Ar</span>
                    </div>
                    <div class="text-right">
                        <span class="text-xs opacity-60">Total Déductions :</span>
                        <span class="font-semibold text-secondary ml-2">- {{ item.total_remboursements|floatformat:0|intcomma }} Ar</span>
                    </div>
                    <div class="text-right">
                        <span class="text-xs font-bold">NET À PAYER :</span>
                        <span class="font-bold text-primary ml-2">{{ item.total_taxe|floatformat:0|intcomma }} Ar</span>
                    </div>
                </div>"""

# 2. Add Modal
old_modal_end = '    </div>\n</div>'
new_modal_end = """    </div>
</div>

<!-- Modal pour ajouter un remboursement -->
<input type="checkbox" id="add-remboursement-modal" class="modal-toggle" />
<div class="modal">
    <div class="modal-box">
        <h3 class="font-bold text-lg mb-4">
            <i class="fas fa-plus-circle mr-2 text-secondary"></i>
            Ajouter un remboursement : <span id="add-remb-commune-name" class="text-secondary"></span>
        </h3>
        
        <form id="add-remboursement-form">
            <input type="hidden" id="add-remb-commune-id" name="commune_id">
            
            <div class="form-control mb-3">
                <label class="label"><span class="label-text">Date du remboursement</span></label>
                <input type="date" id="add-remb-date" class="input input-bordered w-full" required>
            </div>
            
            <div class="form-control mb-3">
                <label class="label"><span class="label-text">Désignation / Motif</span></label>
                <input type="text" id="add-remb-designation" class="input input-bordered w-full" placeholder="Ex: Remboursement pièces de rechange" required>
            </div>
            
            <div class="form-control mb-6">
                <label class="label"><span class="label-text">Montant (Ar)</span></label>
                <input type="number" id="add-remb-montant" class="input input-bordered w-full" step="0.01" required>
            </div>
            
            <div class="modal-action">
                <label for="add-remboursement-modal" class="btn">Annuler</label>
                <button type="submit" class="btn btn-secondary">Enregistrer</button>
            </div>
        </form>
    </div>
</div>"""

# 3. Add JS
old_js_end = "    document.getElementById('details-modal').checked = true;\n}"
new_js_end = """    document.getElementById('details-modal').checked = true;
}

function openAddRemboursementModal(communeId, communeName) {
    document.getElementById('add-remb-commune-id').value = communeId;
    document.getElementById('add-remb-commune-name').textContent = communeName;
    document.getElementById('add-remb-date').value = new Date().toISOString().split('T')[0];
    document.getElementById('add-remb-designation').value = '';
    document.getElementById('add-remb-montant').value = '';
    document.getElementById('add-remboursement-modal').checked = true;
}

document.getElementById('add-remboursement-form').addEventListener('submit', function(e) {
    e.preventDefault();
    
    const data = {
        action: 'add_remboursement',
        commune_id: document.getElementById('add-remb-commune-id').value,
        date: document.getElementById('add-remb-date').value,
        designation: document.getElementById('add-remb-designation').value,
        montant: document.getElementById('add-remb-montant').value,
        annee: "{{ annee }}"
    };
    
    fetch('', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': '{{ csrf_token }}'
        },
        body: JSON.stringify(data)
    })
    .then(response => response.json())
    .then(result => {
        if (result.success) {
            window.location.reload();
        } else {
            alert("Erreur lors de l'ajout: " + result.error);
        }
    })
    .catch(error => {
        console.error('Error:', error);
        alert("Erreur réseau");
    });
});

function deleteRemboursement(rembId) {
    if (!confirm("Voulez-vous vraiment supprimer ce remboursement ?")) return;
    
    const data = {
        action: 'delete_remboursement',
        remboursement_id: rembId
    };
    
    fetch('', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': '{{ csrf_token }}'
        },
        body: JSON.stringify(data)
    })
    .then(response => response.json())
    .then(result => {
        if (result.success) {
            window.location.reload();
        } else {
            alert("Erreur lors de la suppression: " + result.error);
        }
    })
    .catch(error => {
        console.error('Error:', error);
        alert("Erreur réseau");
    });
}"""

# Perform replacements
content = content.replace(old_header, new_header)
content = content.replace(old_modal_end, new_modal_end)
content = content.replace(old_js_end, new_js_end)

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)

print("Successfully updated template programmatically.")
