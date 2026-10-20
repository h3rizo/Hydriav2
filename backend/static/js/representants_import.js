// Fonctions d'import pour la page représentants
console.log('✅ Script representants_import.js chargé');

function importAvis(input) {
    if (!input.files[0]) return;

    console.log('📤 Envoi fichier:', input.files[0].name);

    const formData = new FormData();
    formData.append('file', input.files[0]);

    const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]').value;

    fetch('/usagers/avis/import/', {
        method: 'POST',
        body: formData,
        headers: {'X-CSRFToken': csrfToken}
    })
    .then(response => {
        console.log('📥 Réponse reçue:', response.status);
        return response.json();
    })
    .then(data => {
        console.log('📊 Données:', data);
        if (data.success) {
            let message = `Import terminé:\n- ${data.imported} avis créés`;
            if (data.errors && data.errors.length > 0) {
                message += `\n- ${data.errors.length} erreurs\n\nErreurs:\n${data.errors.join('\n')}`;
            }
            alert(message);
            if (data.imported > 0) {
                location.reload();
            }
        } else {
            alert('Erreur: ' + data.message);
            console.error('Erreur import:', data);
        }
    })
    .catch(error => {
        console.error('Erreur réseau:', error);
        alert('Erreur réseau: ' + error.message);
    });

    input.value = '';
}

function importRepresentants(input) {
    if (!input.files[0]) return;

    const formData = new FormData();
    formData.append('file', input.files[0]);

    const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]').value;

    fetch('/usagers/representants/import/', {
        method: 'POST',
        body: formData,
        headers: {'X-CSRFToken': csrfToken}
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            alert(`Import réussi:\n- ${data.imported} créés\n- ${data.updated} mis à jour\n- ${data.errors.length} erreurs`);
            if (data.errors.length > 0) {
                console.log('Erreurs:', data.errors);
            }
            location.reload();
        } else {
            alert('Erreur: ' + data.message);
        }
    })
    .catch(error => {
        alert('Erreur réseau: ' + error.message);
    });

    input.value = '';
}

console.log('✅ Fonctions importAvis et importRepresentants définies');
