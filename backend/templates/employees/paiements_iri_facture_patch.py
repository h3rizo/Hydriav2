"""
Script pour ajouter les fonctions de génération et téléchargement de facture
"""
import os

template_file = r'c:\Users\Dir Soakoja\Documents\Formation appli web\hydria nuxt django\backend\templates\employees\paiements_iri_liste.html'

# Lire le contenu
with open(template_file, 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Trouver la ligne avec deletePaiement dans le menu dropdown
for i, line in enumerate(lines):
    if '<li><a onclick="deletePaiement' in line and 'text-error' in line:
        # Remplacer cette ligne pour ajouter les nouveaux boutons
        indent = ' ' * 28  # Garder l'indentation
        new_lines = [
            f'{indent}<li><a onclick="viewDetail(\' + p.id + \')"><i class="fas fa-eye text-info mr-2"></i>Voir détails</a></li>\n',
            f"{indent}${{p.statut === 'brouillon' ? `<li><a onclick=\"validerPaiement('${{p.id}}')\" class=\"text-primary\"><i class=\"fas fa-check mr-2\"></i>Valider</a></li>` : ''}}\n",
            f"{indent}${{p.statut === 'valide' && !p.facture_generee ? `<li><a onclick=\"genererFacture('${{p.id}}')\" class=\"text-success\"><i class=\"fas fa-file-excel mr-2\"></i>Générer facture</a></li>` : ''}}\n",
            f"{indent}${{p.facture_generee ? `<li><a onclick=\"telechargerFacture('${{p.id}}')\" class=\"text-primary\"><i class=\"fas fa-download mr-2\"></i>Télécharger facture</a></li>` : ''}}\n",
            f"{indent}${{p.statut === 'brouillon' ? `<li><a onclick=\"deletePaiement('${{p.id}}', '${{moisNom}} ${{p.annee}}')\" class=\"text-error\"><i class=\"fas fa-trash mr-2\"></i>Supprimer</a></li>` : ''}}\n"
        ]

        # Trouver le début du dropdown (ligne avec <ul tabindex=)
        start_idx = i
        while start_idx > 0 and '<ul tabindex="0"' not in lines[start_idx]:
            start_idx -= 1

        # Trouver la fin du dropdown (ligne avec </ul>)
        end_idx = i
        while end_idx < len(lines) and '</ul>' not in lines[end_idx]:
            end_idx += 1

        if start_idx > 0 and end_idx < len(lines):
            # Remplacer tout le contenu du dropdown
            lines[start_idx+1:end_idx] = new_lines
            print(f'[OK] Menu dropdown mis à jour (lignes {start_idx+1} à {end_idx})')
            break

# Ajouter les fonctions JavaScript avant le DOMContentLoaded
for i, line in enumerate(lines):
    if "document.addEventListener('DOMContentLoaded'," in line:
        # Insérer les nouvelles fonctions avant DOMContentLoaded
        new_functions = '''
// Générer la facture Excel
async function genererFacture(id) {
    if (!confirm('Générer la facture Excel pour ce paiement IRI ?')) {
        return;
    }

    try {
        const response = await fetch(`/api/paiement-iri/${id}/generer-facture/`, {
            method: 'POST',
            headers: {
                'X-CSRFToken': getCookie('csrftoken')
            }
        });

        const data = await response.json();

        if (data.success) {
            let message = `✓ Facture IRI générée avec succès!\\n\\nFichier: ${data.filename}`;
            if (data.erreurs && data.erreurs.length > 0) {
                message += '\\n\\n⚠️ Avertissements:\\n' + data.erreurs.join('\\n');
            }
            alert(message);
            // Recharger la liste pour afficher le bouton de téléchargement
            loadPaiements();
        } else {
            alert('Erreur: ' + data.error);
        }
    } catch (error) {
        console.error('Erreur:', error);
        alert('Erreur réseau: ' + error.message);
    }
}

// Télécharger la facture Excel
function telechargerFacture(id) {
    window.location.href = `/api/paiement-iri/${id}/telecharger-facture/`;
}

'''
        lines.insert(i, new_functions)
        print(f'[OK] Fonctions JavaScript ajoutées avant ligne {i}')
        break

# Écrire le contenu modifié
with open(template_file, 'w', encoding='utf-8') as f:
    f.writelines(lines)

print('[OK] Template mis à jour avec succès')
