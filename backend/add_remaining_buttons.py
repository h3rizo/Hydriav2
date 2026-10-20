#!/usr/bin/env python3
"""
Script pour ajouter tous les boutons manquants dans home_launcher.html
"""

# Boutons de Comptabilité à ajouter après les boutons existants
comptabilite_buttons = '''
                    <a href="{% url 'accounting:ecritures_comptables' %}" class="group">
                        <div class="card bg-gradient-to-br from-primary to-primary-focus text-primary-content h-full shadow-xl hover:shadow-2xl transition-all duration-300">
                            <div class="card-body items-center text-center p-4">
                                <i class="fas fa-book text-4xl mb-2"></i>
                                <h3 class="font-bold text-sm">Écritures comptables</h3>
                            </div>
                        </div>
                    </a>
                    <a href="{% url 'accounting:transactions_temporaires' %}" class="group">
                        <div class="card bg-gradient-to-br from-info to-info-focus text-info-content h-full shadow-xl hover:shadow-2xl transition-all duration-300">
                            <div class="card-body items-center text-center p-4">
                                <i class="fas fa-exchange-alt text-4xl mb-2"></i>
                                <h3 class="font-bold text-sm">Transactions temp.</h3>
                            </div>
                        </div>
                    </a>
                    <a href="{% url 'accounting:export_paie_charges' %}" class="group">
                        <div class="card bg-gradient-to-br from-success to-success-focus text-success-content h-full shadow-xl hover:shadow-2xl transition-all duration-300">
                            <div class="card-body items-center text-center p-4">
                                <i class="fas fa-file-export text-4xl mb-2"></i>
                                <h3 class="font-bold text-sm">Export Paie</h3>
                            </div>
                        </div>
                    </a>
                    <a href="{% url 'accounting:diagnostic_soldes' %}" class="group">
                        <div class="card bg-gradient-to-br from-warning to-warning-focus text-warning-content h-full shadow-xl hover:shadow-2xl transition-all duration-300">
                            <div class="card-body items-center text-center p-4">
                                <i class="fas fa-stethoscope text-4xl mb-2"></i>
                                <h3 class="font-bold text-sm">Diagnostic soldes</h3>
                            </div>
                        </div>
                    </a>
                    <a href="{% url 'accounting:comparaison_soldes' %}" class="group">
                        <div class="card bg-gradient-to-br from-secondary to-secondary-focus text-secondary-content h-full shadow-xl hover:shadow-2xl transition-all duration-300">
                            <div class="card-body items-center text-center p-4">
                                <i class="fas fa-balance-scale text-4xl mb-2"></i>
                                <h3 class="font-bold text-sm">Comparaison soldes</h3>
                            </div>
                        </div>
                    </a>
                    <a href="{% url 'accounting:soldes_reels' %}" class="group">
                        <div class="card bg-gradient-to-br from-accent to-accent-focus text-accent-content h-full shadow-xl hover:shadow-2xl transition-all duration-300">
                            <div class="card-body items-center text-center p-4">
                                <i class="fas fa-coins text-4xl mb-2"></i>
                                <h3 class="font-bold text-sm">Soldes Réels</h3>
                            </div>
                        </div>
                    </a>
                    <a href="{% url 'accounting:controle_conversion' %}" class="group">
                        <div class="card bg-gradient-to-br from-error to-error-focus text-error-content h-full shadow-xl hover:shadow-2xl transition-all duration-300">
                            <div class="card-body items-center text-center p-4">
                                <i class="fas fa-sync-alt text-4xl mb-2"></i>
                                <h3 class="font-bold text-sm">Contrôle Conversion</h3>
                            </div>
                        </div>
                    </a>
                    <a href="{% url 'accounting:conversion_partie_double' %}" class="group">
                        <div class="card bg-gradient-to-br from-primary to-primary-focus text-primary-content h-full shadow-xl hover:shadow-2xl transition-all duration-300">
                            <div class="card-body items-center text-center p-4">
                                <i class="fas fa-random text-4xl mb-2"></i>
                                <h3 class="font-bold text-sm">Conversion double</h3>
                            </div>
                        </div>
                    </a>
                    <a href="{% url 'accounting:budgets_annuels' %}" class="group">
                        <div class="card bg-gradient-to-br from-info to-info-focus text-info-content h-full shadow-xl hover:shadow-2xl transition-all duration-300">
                            <div class="card-body items-center text-center p-4">
                                <i class="fas fa-chart-line text-4xl mb-2"></i>
                                <h3 class="font-bold text-sm">Budgets annuels</h3>
                            </div>
                        </div>
                    </a>
                    <a href="{% url 'accounting:demande_fonds' %}" class="group">
                        <div class="card bg-gradient-to-br from-success to-success-focus text-success-content h-full shadow-xl hover:shadow-2xl transition-all duration-300">
                            <div class="card-body items-center text-center p-4">
                                <i class="fas fa-hand-holding-usd text-4xl mb-2"></i>
                                <h3 class="font-bold text-sm">Demande fonds</h3>
                            </div>
                        </div>
                    </a>
                    <a href="{% url 'accounting:evaluation_saisie' %}" class="group">
                        <div class="card bg-gradient-to-br from-warning to-warning-focus text-warning-content h-full shadow-xl hover:shadow-2xl transition-all duration-300">
                            <div class="card-body items-center text-center p-4">
                                <i class="fas fa-clipboard-check text-4xl mb-2"></i>
                                <h3 class="font-bold text-sm">Évaluation saisie</h3>
                            </div>
                        </div>
                    </a>
                    <a href="{% url 'accounting:recoupements' %}" class="group">
                        <div class="card bg-gradient-to-br from-secondary to-secondary-focus text-secondary-content h-full shadow-xl hover:shadow-2xl transition-all duration-300">
                            <div class="card-body items-center text-center p-4">
                                <i class="fas fa-link text-4xl mb-2"></i>
                                <h3 class="font-bold text-sm">Recoupements</h3>
                            </div>
                        </div>
                    </a>
                    <a href="{% url 'accounting:saisie_documents' %}" class="group">
                        <div class="card bg-gradient-to-br from-accent to-accent-focus text-accent-content h-full shadow-xl hover:shadow-2xl transition-all duration-300">
                            <div class="card-body items-center text-center p-4">
                                <i class="fas fa-file-upload text-4xl mb-2"></i>
                                <h3 class="font-bold text-sm">Saisie documents</h3>
                            </div>
                        </div>
                    </a>
                    <a href="{% url 'accounting:declaration_communication' %}" class="group">
                        <div class="card bg-gradient-to-br from-error to-error-focus text-error-content h-full shadow-xl hover:shadow-2xl transition-all duration-300">
                            <div class="card-body items-center text-center p-4">
                                <i class="fas fa-file-contract text-4xl mb-2"></i>
                                <h3 class="font-bold text-sm">Déclaration comm.</h3>
                            </div>
                        </div>
                    </a>'''

# Nouvelles sections complètes
new_sections = '''
            <!-- Tableaux & Rapports -->
            <div>
                <h3 class="text-xl font-bold mb-4 flex items-center">
                    <i class="fas fa-table mr-2"></i>
                    Tableaux & Rapports
                </h3>
                <div class="grid grid-cols-3 md:grid-cols-5 lg:grid-cols-8 gap-4">
                    <a href="{% url 'reports:dashboard' %}" class="group">
                        <div class="card bg-gradient-to-br from-primary to-primary-focus text-primary-content h-full shadow-xl hover:shadow-2xl transition-all duration-300">
                            <div class="card-body items-center text-center p-4">
                                <i class="fas fa-chart-pie text-4xl mb-2"></i>
                                <h3 class="font-bold text-sm">Tableaux de bord</h3>
                            </div>
                        </div>
                    </a>
                    <a href="{% url 'reports:exports' %}" class="group">
                        <div class="card bg-gradient-to-br from-info to-info-focus text-info-content h-full shadow-xl hover:shadow-2xl transition-all duration-300">
                            <div class="card-body items-center text-center p-4">
                                <i class="fas fa-file-excel text-4xl mb-2"></i>
                                <h3 class="font-bold text-sm">Exports</h3>
                            </div>
                        </div>
                    </a>
                </div>
            </div>

            <!-- Recherche Globale -->
            <div>
                <h3 class="text-xl font-bold mb-4 flex items-center">
                    <i class="fas fa-search mr-2"></i>
                    Recherche
                </h3>
                <div class="grid grid-cols-3 md:grid-cols-5 lg:grid-cols-8 gap-4">
                    <a href="{% url 'core:search' %}" class="group">
                        <div class="card bg-gradient-to-br from-info to-info-focus text-info-content h-full shadow-xl hover:shadow-2xl transition-all duration-300">
                            <div class="card-body items-center text-center p-4">
                                <i class="fas fa-search text-4xl mb-2"></i>
                                <h3 class="font-bold text-sm">Recherche globale</h3>
                            </div>
                        </div>
                    </a>
                </div>
            </div>

            <!-- Achats & Stocks -->
            <div>
                <h3 class="text-xl font-bold mb-4 flex items-center">
                    <i class="fas fa-warehouse mr-2"></i>
                    Achats & Stocks
                </h3>
                <div class="grid grid-cols-3 md:grid-cols-5 lg:grid-cols-8 gap-4">
                    <a href="{% url 'inventory:products' %}" class="group">
                        <div class="card bg-gradient-to-br from-primary to-primary-focus text-primary-content h-full shadow-xl hover:shadow-2xl transition-all duration-300">
                            <div class="card-body items-center text-center p-4">
                                <i class="fas fa-box text-4xl mb-2"></i>
                                <h3 class="font-bold text-sm">Produits</h3>
                            </div>
                        </div>
                    </a>
                    <a href="{% url 'inventory:stock_list' %}" class="group">
                        <div class="card bg-gradient-to-br from-info to-info-focus text-info-content h-full shadow-xl hover:shadow-2xl transition-all duration-300">
                            <div class="card-body items-center text-center p-4">
                                <i class="fas fa-boxes text-4xl mb-2"></i>
                                <h3 class="font-bold text-sm">Stocks</h3>
                            </div>
                        </div>
                    </a>
                    <a href="{% url 'billing:fournisseurs_list' %}" class="group">
                        <div class="card bg-gradient-to-br from-success to-success-focus text-success-content h-full shadow-xl hover:shadow-2xl transition-all duration-300">
                            <div class="card-body items-center text-center p-4">
                                <i class="fas fa-store text-4xl mb-2"></i>
                                <h3 class="font-bold text-sm">Fournisseurs</h3>
                            </div>
                        </div>
                    </a>
                    <a href="{% url 'inventory:purchases' %}" class="group">
                        <div class="card bg-gradient-to-br from-warning to-warning-focus text-warning-content h-full shadow-xl hover:shadow-2xl transition-all duration-300">
                            <div class="card-body items-center text-center p-4">
                                <i class="fas fa-shopping-cart text-4xl mb-2"></i>
                                <h3 class="font-bold text-sm">Achats</h3>
                            </div>
                        </div>
                    </a>
                </div>
            </div>

            <!-- Conversations -->
            <div>
                <h3 class="text-xl font-bold mb-4 flex items-center">
                    <i class="fas fa-comments mr-2"></i>
                    Communication
                </h3>
                <div class="grid grid-cols-3 md:grid-cols-5 lg:grid-cols-8 gap-4">
                    <a href="{% url 'conversations:inbox' %}" class="group">
                        <div class="card bg-gradient-to-br from-primary to-primary-focus text-primary-content h-full shadow-xl hover:shadow-2xl transition-all duration-300">
                            <div class="card-body items-center text-center p-4">
                                <i class="fas fa-inbox text-4xl mb-2"></i>
                                <h3 class="font-bold text-sm">Conversations</h3>
                            </div>
                        </div>
                    </a>
                </div>
            </div>

            <!-- Référentiels -->
            <div>
                <h3 class="text-xl font-bold mb-4 flex items-center">
                    <i class="fas fa-database mr-2"></i>
                    Référentiels
                </h3>
                <div class="grid grid-cols-3 md:grid-cols-5 lg:grid-cols-8 gap-4">
                    <a href="{% url 'geography:regions' %}" class="group">
                        <div class="card bg-gradient-to-br from-primary to-primary-focus text-primary-content h-full shadow-xl hover:shadow-2xl transition-all duration-300">
                            <div class="card-body items-center text-center p-4">
                                <i class="fas fa-map text-4xl mb-2"></i>
                                <h3 class="font-bold text-sm">Géographie</h3>
                            </div>
                        </div>
                    </a>
                    <a href="{% url 'organization:organisations' %}" class="group">
                        <div class="card bg-gradient-to-br from-info to-info-focus text-info-content h-full shadow-xl hover:shadow-2xl transition-all duration-300">
                            <div class="card-body items-center text-center p-4">
                                <i class="fas fa-building text-4xl mb-2"></i>
                                <h3 class="font-bold text-sm">Organisations</h3>
                            </div>
                        </div>
                    </a>
                    <a href="{% url 'organization:ouvrages' %}" class="group">
                        <div class="card bg-gradient-to-br from-success to-success-focus text-success-content h-full shadow-xl hover:shadow-2xl transition-all duration-300">
                            <div class="card-body items-center text-center p-4">
                                <i class="fas fa-hammer text-4xl mb-2"></i>
                                <h3 class="font-bold text-sm">Ouvrages</h3>
                            </div>
                        </div>
                    </a>
                </div>
            </div>

            <!-- Administration -->
            <div>
                <h3 class="text-xl font-bold mb-4 flex items-center">
                    <i class="fas fa-cog mr-2"></i>
                    Administration
                </h3>
                <div class="grid grid-cols-3 md:grid-cols-5 lg:grid-cols-8 gap-4">
                    <a href="{% url 'system:users' %}" class="group">
                        <div class="card bg-gradient-to-br from-primary to-primary-focus text-primary-content h-full shadow-xl hover:shadow-2xl transition-all duration-300">
                            <div class="card-body items-center text-center p-4">
                                <i class="fas fa-users-cog text-4xl mb-2"></i>
                                <h3 class="font-bold text-sm">Utilisateurs</h3>
                            </div>
                        </div>
                    </a>
                    <a href="{% url 'system:settings' %}" class="group">
                        <div class="card bg-gradient-to-br from-info to-info-focus text-info-content h-full shadow-xl hover:shadow-2xl transition-all duration-300">
                            <div class="card-body items-center text-center p-4">
                                <i class="fas fa-sliders-h text-4xl mb-2"></i>
                                <h3 class="font-bold text-sm">Paramètres</h3>
                            </div>
                        </div>
                    </a>
                    <a href="{% url 'system:logs' %}" class="group">
                        <div class="card bg-gradient-to-br from-warning to-warning-focus text-warning-content h-full shadow-xl hover:shadow-2xl transition-all duration-300">
                            <div class="card-body items-center text-center p-4">
                                <i class="fas fa-history text-4xl mb-2"></i>
                                <h3 class="font-bold text-sm">Journaux</h3>
                            </div>
                        </div>
                    </a>
                </div>
            </div>'''

print("Sections générées avec succès!")
print("\nBoutons Comptabilité:", len(comptabilite_buttons.split('<a href')))
print("Nouvelles sections:", new_sections.count('<!-- '))
