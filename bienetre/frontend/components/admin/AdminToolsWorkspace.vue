<template>
  <div class="space-y-6">
    <section class="panel space-y-4 p-6">
      <div class="flex flex-wrap items-center gap-3">
        <NuxtLink class="btn-secondary" to="/admin-tools">
          <span aria-hidden="true">←</span>
          <span>Accueil admin</span>
        </NuxtLink>
        <NuxtLink
          v-for="section in sections"
          :key="section.key"
          :class="activeSection === section.key
            ? 'btn-primary ring-2 ring-emerald-300/40 shadow-[0_0_0_1px_rgba(16,185,129,0.25)]'
            : 'btn-secondary opacity-85 hover:opacity-100'"
          :to="`/admin-tools/${section.key}`"
        >
          <span aria-hidden="true">{{ section.icon }}</span>
          <span>{{ section.label }}</span>
          <span
            v-if="activeSection === section.key"
            class="rounded-full bg-white/15 px-2 py-0.5 text-[10px] uppercase tracking-[0.2em]"
          >
            Actif
          </span>
        </NuxtLink>
      </div>
    </section>

    <p v-if="feedback" class="text-sm aurora-subtle">{{ feedback }}</p>

    <section v-if="activeSection === 'users'" class="grid gap-6 xl:grid-cols-[0.8fr_1.2fr]">
      <form class="panel space-y-4 p-8" @submit.prevent="createAdminUser">
        <h2 class="text-2xl font-semibold aurora-title">Ajouter un utilisateur</h2>
        <input v-model="userForm.username" class="field" type="text" placeholder="Nom d'utilisateur" />
        <input v-model="userForm.email" class="field" type="email" placeholder="Email" />
        <input v-model="userForm.password" class="field" type="password" placeholder="Mot de passe" />
        <label class="inline-flex items-center gap-3 text-sm text-stone-300">
          <input v-model="userForm.is_staff" type="checkbox" class="h-4 w-4 accent-emerald-400" />
          <span>Administrateur</span>
        </label>
        <label class="inline-flex items-center gap-3 text-sm text-stone-300">
          <input v-model="userForm.is_superuser" type="checkbox" class="h-4 w-4 accent-emerald-400" />
          <span>Superutilisateur</span>
        </label>
        <label class="inline-flex items-center gap-3 text-sm text-stone-300">
          <input v-model="userForm.is_active" type="checkbox" class="h-4 w-4 accent-emerald-400" />
          <span>Compte actif</span>
        </label>
        <button class="btn-primary" type="submit">Creer l'utilisateur</button>
      </form>

      <div class="panel p-8">
        <h2 class="text-2xl font-semibold">Utilisateurs</h2>
        <div class="mt-5 grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          <article v-for="user in users" :key="user.id" class="glass-card p-5">
            <p class="text-xs uppercase tracking-[0.25em] aurora-muted">{{ user.email || "Sans email" }}</p>
            <h3 class="mt-2 text-xl font-semibold">{{ user.username }}</h3>
            <p class="mt-3 text-sm aurora-subtle">Admin: {{ user.is_staff ? "Oui" : "Non" }}</p>
            <p class="text-sm aurora-subtle">Superuser: {{ user.is_superuser ? "Oui" : "Non" }}</p>
            <p class="text-sm aurora-subtle">Actif: {{ user.is_active ? "Oui" : "Non" }}</p>
          </article>
        </div>
      </div>
    </section>

    <section v-if="activeSection === 'catalog'" class="space-y-6">
      <div class="page-hero overflow-hidden p-8">
        <div class="grid gap-8 lg:grid-cols-[1.05fr_0.95fr] lg:items-end">
        <div>
          <span class="hero-badge">Parametrage</span>
          <h2 class="page-hero-title mt-4">Villes, vendeurs et prix ingredients</h2>
          <p class="page-hero-copy">
            Les villes servent de base, les vendeurs sont rattaches a une ville, puis les prix lient un ingredient a un vendeur pour les achats et les preferences.
          </p>
          <div class="mt-6 flex flex-wrap gap-3">
            <button :class="catalogTab === 'cities' ? 'btn-primary' : 'btn-secondary'" type="button" @click="catalogTab = 'cities'">Villes</button>
            <button :class="catalogTab === 'vendors' ? 'btn-primary' : 'btn-secondary'" type="button" @click="catalogTab = 'vendors'">Vendeurs</button>
            <button :class="catalogTab === 'ingredient-prices' ? 'btn-primary' : 'btn-secondary'" type="button" @click="catalogTab = 'ingredient-prices'">Prix ingredients</button>
            <button :class="catalogTab === 'wellbeing-articles' ? 'btn-primary' : 'btn-secondary'" type="button" @click="catalogTab = 'wellbeing-articles'">Articles bien-etre</button>
            <button :class="catalogTab === 'wellbeing-article-prices' ? 'btn-primary' : 'btn-secondary'" type="button" @click="catalogTab = 'wellbeing-article-prices'">Prix articles bien-etre</button>
          </div>
        </div>
        <article class="glass-card overflow-hidden p-0">
          <div class="grid gap-3 p-6">
            <article class="stat-card stat-card-warm">
              <p class="text-sm aurora-subtle">Villes</p>
              <p class="mt-2 text-2xl font-semibold">{{ cities.length }}</p>
            </article>
            <article class="stat-card stat-card-cool">
              <p class="text-sm aurora-subtle">Vendeurs</p>
              <p class="mt-2 text-2xl font-semibold">{{ vendors.length }}</p>
            </article>
            <article class="stat-card stat-card-violet">
              <p class="text-sm aurora-subtle">Ingredients</p>
              <p class="mt-2 text-2xl font-semibold">{{ ingredients.length }}</p>
            </article>
          </div>
        </article>
        </div>
      </div>

      <section v-if="catalogTab === 'cities'" class="grid gap-6 xl:grid-cols-[0.8fr_1.2fr]">
        <form class="panel space-y-4 p-8" @submit.prevent="saveCity">
          <h3 class="text-2xl font-semibold">{{ cityEditId ? 'Modifier une ville' : 'Ajouter une ville' }}</h3>
          <input v-model="cityForm.nom" class="field" type="text" placeholder="Nom de la ville" />
          <div class="flex flex-wrap gap-3">
            <button class="btn-primary" type="submit">{{ cityEditId ? 'Mettre a jour' : 'Creer la ville' }}</button>
            <button v-if="cityEditId" class="btn-secondary" type="button" @click="cancelCityEdit">Annuler</button>
          </div>
        </form>

        <div class="panel p-8">
          <div class="flex items-center justify-between gap-4">
            <div>
              <h3 class="text-2xl font-semibold">Villes enregistrees</h3>
              <p class="mt-2 text-sm aurora-subtle">La base pour filtrer les vendeurs et les prix.</p>
            </div>
            <span class="text-sm aurora-muted">{{ cities.length }} villes</span>
          </div>
          <div class="mt-5 grid gap-3 md:grid-cols-2">
            <article v-for="city in cities" :key="city.id" class="glass-card p-4">
              <div class="flex items-start justify-between gap-3">
                <div>
                  <p class="text-xs uppercase tracking-[0.25em] aurora-muted">Ville</p>
                  <h4 class="mt-2 text-lg font-semibold">{{ city.nom }}</h4>
                  <p class="mt-2 text-sm aurora-subtle">{{ getCityVendorCount(city.id) }} vendeurs rattaches</p>
                </div>
                <div class="flex flex-col gap-2">
                  <button class="btn-secondary" type="button" @click="startCityEdit(city)">Modifier</button>
                  <button class="btn-secondary" type="button" @click="deleteCity(city.id)">Supprimer</button>
                </div>
              </div>
            </article>
          </div>
        </div>
      </section>

      <section v-if="catalogTab === 'vendors'" class="grid gap-6 xl:grid-cols-[0.8fr_1.2fr]">
        <form class="panel space-y-4 p-8" @submit.prevent="saveVendor">
          <h3 class="text-2xl font-semibold">{{ vendorEditId ? 'Modifier un vendeur' : 'Ajouter un vendeur' }}</h3>
          <input v-model="vendorForm.nom" class="field" type="text" placeholder="Nom du vendeur" />
          <select v-model.number="vendorForm.city" class="field">
            <option :value="0">Choisir une ville</option>
            <option v-for="city in cities" :key="city.id" :value="city.id">{{ city.nom }}</option>
          </select>
          <textarea v-model="vendorForm.description" class="field min-h-[120px]" placeholder="Description" />
          <div class="flex flex-wrap gap-3">
            <button class="btn-primary" type="submit">{{ vendorEditId ? 'Mettre a jour' : 'Creer le vendeur' }}</button>
            <button v-if="vendorEditId" class="btn-secondary" type="button" @click="cancelVendorEdit">Annuler</button>
          </div>
        </form>

        <div class="panel p-8">
          <div class="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
            <div>
              <h3 class="text-2xl font-semibold">Vendeurs enregistres</h3>
              <p class="mt-2 text-sm aurora-subtle">Filtrer la liste par ville pour retrouver rapidement les vendeurs locaux.</p>
            </div>
            <select v-model.number="catalogCityFilter" class="field lg:w-72">
              <option :value="0">Toutes les villes</option>
              <option v-for="city in cities" :key="city.id" :value="city.id">{{ city.nom }}</option>
            </select>
          </div>
          <div class="mt-5 grid gap-3 md:grid-cols-2">
            <article v-for="vendor in filteredVendors" :key="vendor.id" class="glass-card p-4">
              <div class="flex items-start justify-between gap-3">
                <div>
                  <p class="text-xs uppercase tracking-[0.25em] aurora-muted">{{ vendor.city_nom }}</p>
                  <h4 class="mt-2 text-lg font-semibold">{{ vendor.nom }}</h4>
                  <p class="mt-2 whitespace-pre-line text-sm aurora-subtle">{{ vendor.description || 'Aucune description' }}</p>
                </div>
                <div class="flex flex-col gap-2">
                  <button class="btn-secondary" type="button" @click="startVendorEdit(vendor)">Modifier</button>
                  <button class="btn-secondary" type="button" @click="deleteVendor(vendor.id)">Supprimer</button>
                </div>
              </div>
            </article>
          </div>
        </div>
      </section>

      <section v-if="catalogTab === 'ingredient-prices'" class="space-y-6">
        <div class="panel p-8">
          <div class="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
            <div>
              <h3 class="text-2xl font-semibold">Prix ingredients</h3>
              <p class="mt-2 text-sm aurora-subtle">Partez d'une categorie, ouvrez un ingredient puis saisissez ou modifiez ses prix par vendeur.</p>
            </div>
            <select v-model.number="catalogCityFilter" class="field lg:w-72">
              <option :value="0">Toutes les villes</option>
              <option v-for="city in cities" :key="city.id" :value="city.id">{{ city.nom }}</option>
            </select>
          </div>

          <div class="mt-5" v-if="selectedPriceIngredientGroup">
            <div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <button class="btn-secondary" type="button" @click="selectedPriceCategory = null">
                <span aria-hidden="true">←</span>
                <span>Retour aux categories</span>
              </button>
              <span class="glass-chip">{{ selectedPriceIngredientGroup.items.length }} ingredients</span>
            </div>
            <div class="mt-4 glass-card p-5">
              <p class="text-xs uppercase tracking-[0.24em] aurora-muted">Categorie</p>
              <h3 class="mt-2 text-xl font-semibold">{{ selectedPriceIngredientGroup.category }}</h3>
            </div>
            <div class="mt-4 grid gap-4 md:grid-cols-2">
              <article v-for="ingredient in selectedPriceIngredientGroup.items" :key="`price-ingredient-${ingredient.id}`" class="glass-card p-4">
                <div class="flex items-start justify-between gap-3">
                  <div class="min-w-0">
                    <h4 class="truncate text-lg font-semibold">{{ ingredient.icone || "🥒" }} {{ ingredient.nom }}</h4>
                    <p class="mt-1 text-sm aurora-subtle">{{ getIngredientPriceLabel(ingredient) }}</p>
                  </div>
                  <button class="btn-secondary px-3 text-xs" type="button" @click="startIngredientPriceCreateForIngredient(ingredient.id)">
                    Ajouter prix
                  </button>
                </div>

                <form class="mt-4 grid gap-3 rounded-2xl border border-white/10 bg-white/5 p-4" @submit.prevent="saveIngredientPrice(ingredient.id)">
                  <select v-model.number="getIngredientPriceDraft(ingredient.id).vendor" class="field">
                    <option :value="0">Choisir un vendeur</option>
                    <option v-for="vendor in priceVendorOptions" :key="vendor.id" :value="vendor.id">
                      {{ vendor.nom }} - {{ vendor.city_nom }}
                    </option>
                  </select>
                  <div class="grid gap-3 sm:grid-cols-2">
                    <input
                      v-model="getIngredientPriceDraft(ingredient.id).prix"
                      class="field"
                      inputmode="decimal"
                      type="text"
                      :placeholder="`${getIngredientPriceLabel(ingredient)} (optionnel)`"
                    />
                    <input v-model="getIngredientPriceDraft(ingredient.id).date_dernier_prix" class="field" type="date" />
                  </div>
                  <div class="flex flex-wrap gap-3">
                    <button class="btn-primary" type="submit">
                      {{ getIngredientPriceDraft(ingredient.id).editId ? 'Mettre a jour' : 'Enregistrer' }}
                    </button>
                    <button
                      v-if="getIngredientPriceDraft(ingredient.id).editId"
                      class="btn-secondary"
                      type="button"
                      @click="cancelIngredientPriceEdit(ingredient.id)"
                    >
                      Annuler
                    </button>
                  </div>
                </form>

                <div class="mt-4 space-y-2">
                  <article
                    v-for="price in getPricesForIngredient(ingredient.id)"
                    :key="price.id"
                    class="rounded-2xl border border-white/10 bg-white/5 px-4 py-3"
                  >
                    <div class="flex items-start justify-between gap-3">
                      <div>
                        <p class="font-medium">{{ price.vendor_nom }}</p>
                        <p class="text-sm aurora-muted">{{ price.city_nom }}</p>
                        <p class="mt-1 text-sm aurora-subtle">{{ getIngredientPriceLabel(ingredient) }} : {{ formatCurrency(price.prix) }} · {{ price.date_dernier_prix }}</p>
                      </div>
                      <div class="flex gap-2">
                        <button class="btn-secondary px-3 text-xs" type="button" @click="startIngredientPriceEdit(price)">✏️</button>
                        <button class="btn-secondary px-3 text-xs" type="button" @click="deleteIngredientPrice(price.id)">🗑️</button>
                      </div>
                    </div>
                  </article>
                  <p v-if="!getPricesForIngredient(ingredient.id).length" class="text-sm aurora-muted">Aucun prix enregistre pour cet ingredient.</p>
                </div>
              </article>
            </div>
          </div>

          <div v-else class="mt-5 grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            <section v-for="group in groupedIngredients" :key="`price-category-${group.category}`" class="space-y-3">
              <button
                class="glass-card flex w-full min-w-0 items-center justify-between gap-3 p-4 text-left transition hover:bg-white/10"
                type="button"
                @click="selectedPriceCategory = group.category"
              >
                <span class="min-w-0 truncate">{{ group.category }}</span>
                <span class="glass-chip shrink-0">{{ group.items.length }}</span>
              </button>
              <div class="glass-card -mt-1 overflow-hidden p-0">
                <div class="divide-y divide-white/10">
                  <div
                    v-for="ingredient in group.items.slice(0, 4)"
                    :key="`price-preview-${group.category}-${ingredient.id}`"
                    class="flex items-center justify-between gap-3 px-4 py-3"
                  >
                    <div class="flex min-w-0 items-center gap-3">
                      <span class="text-xl">{{ ingredient.icone || "🥒" }}</span>
                      <span class="truncate text-sm text-stone-100">{{ ingredient.nom }}</span>
                    </div>
                    <span class="text-xs aurora-muted">{{ getPricesForIngredient(ingredient.id).length }} prix</span>
                  </div>
                </div>
                <p v-if="group.items.length > 4" class="px-4 py-3 text-xs aurora-muted">
                  + {{ group.items.length - 4 }} autres ingredients
                </p>
              </div>
            </section>
          </div>
        </div>
      </section>

      <section v-if="catalogTab === 'wellbeing-articles'" class="space-y-6">
        <div class="panel p-8">
          <div class="flex items-start justify-between gap-4">
            <div>
              <h2 class="text-2xl font-semibold">Articles bien-etre</h2>
              <p class="mt-2 text-sm aurora-subtle">Catalogue des achats non alimentaires lies au bien-etre, organise par categories.</p>
            </div>
            <div class="flex flex-wrap gap-3">
              <button class="btn-secondary" type="button" @click="wellbeingArticleViewMode = wellbeingArticleViewMode === 'cards' ? 'table' : 'cards'">
                <span aria-hidden="true">{{ wellbeingArticleViewMode === 'cards' ? "📋" : "🪟" }}</span>
                <span>{{ wellbeingArticleViewMode === 'cards' ? "Mode tableau" : "Mode cartes" }}</span>
              </button>
              <button class="btn-primary" type="button" @click="openWellbeingArticleCreateModal">
                <span aria-hidden="true">➕</span>
                <span>Ajouter un article</span>
              </button>
              <span class="glass-chip">{{ wellbeingArticles.length }} articles</span>
            </div>
          </div>

          <div v-if="wellbeingArticles.length && wellbeingArticleViewMode === 'cards'" class="mt-5 max-h-[70vh] overflow-y-auto sm:pr-2">
            <div v-if="selectedWellbeingArticleGroup" class="space-y-5">
              <div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                <button class="btn-secondary" type="button" @click="selectedWellbeingArticleCategory = null">
                  <span aria-hidden="true">←</span>
                  <span>Retour aux categories</span>
                </button>
                <span class="glass-chip">{{ selectedWellbeingArticleGroup.items.length }} articles</span>
              </div>
              <div class="glass-card p-5">
                <p class="text-xs uppercase tracking-[0.24em] aurora-muted">Categorie</p>
                <h3 class="mt-2 text-xl font-semibold">{{ selectedWellbeingArticleGroup.category }}</h3>
              </div>
              <div class="grid gap-3 md:grid-cols-2">
                <article v-for="article in selectedWellbeingArticleGroup.items" :key="article.id" class="glass-card p-4">
                  <div class="flex items-start justify-between gap-3">
                    <div class="min-w-0 flex-1">
                      <h3 class="truncate text-lg font-semibold">{{ article.icone || "🧴" }} {{ article.nom }}</h3>
                      <p class="mt-2 text-sm aurora-subtle">{{ article.categorie || "Sans categorie" }}</p>
                      <div class="mt-2 flex flex-wrap gap-2">
                        <span class="glass-chip">Unite: {{ article.unite_base }}</span>
                        <span class="glass-chip">{{ article.vendor_ids.length }} vendeur(s)</span>
                      </div>
                    </div>
                    <div class="flex shrink-0 items-center gap-1 self-start">
                      <button class="btn-secondary px-2 py-1.5 text-xs" type="button" title="Details" aria-label="Details" @click="openWellbeingArticleDetailModal(article)">👁️</button>
                      <button class="btn-secondary px-2 py-1.5 text-xs" type="button" title="Modifier" aria-label="Modifier" @click="openWellbeingArticleEditModal(article)">✏️</button>
                      <button class="btn-secondary px-2 py-1.5 text-xs" type="button" title="Supprimer" aria-label="Supprimer" @click="deleteWellbeingArticle(article.id)">🗑️</button>
                    </div>
                  </div>
                  <p v-if="article.description" class="mt-3 text-sm aurora-muted">{{ article.description }}</p>
                  <div class="mt-4 flex flex-wrap gap-2">
                    <span v-for="vendorId in article.vendor_ids.slice(0, 3)" :key="`wa-chip-${article.id}-${vendorId}`" class="glass-chip">
                      {{ getVendorName(vendorId) }}
                    </span>
                    <span v-if="article.vendor_ids.length > 3" class="glass-chip">+ {{ article.vendor_ids.length - 3 }}</span>
                  </div>
                </article>
              </div>
            </div>
            <div v-else class="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
              <section v-for="group in groupedWellbeingArticlesForAdmin" :key="group.category" class="space-y-3">
                <button
                  class="glass-card flex w-full min-w-0 items-center justify-between gap-3 p-4 text-left transition hover:bg-white/10"
                  type="button"
                  @click="selectedWellbeingArticleCategory = group.category"
                >
                  <span class="min-w-0 truncate">{{ group.category }}</span>
                  <span class="glass-chip shrink-0">{{ group.items.length }}</span>
                </button>
                <div class="glass-card -mt-1 overflow-hidden p-0">
                  <div class="divide-y divide-white/10">
                    <div
                      v-for="article in group.items.slice(0, 4)"
                      :key="`wa-preview-${group.category}-${article.id}`"
                      class="flex items-center justify-between gap-3 px-4 py-3"
                    >
                      <div class="flex min-w-0 items-center gap-3">
                        <span class="text-xl">{{ article.icone || "🧴" }}</span>
                        <span class="truncate text-sm text-stone-100">{{ article.nom }}</span>
                      </div>
                      <span class="text-xs aurora-muted">{{ article.unite_base }}</span>
                    </div>
                  </div>
                  <p v-if="group.items.length > 4" class="px-4 py-3 text-xs aurora-muted">
                    + {{ group.items.length - 4 }} autres articles
                  </p>
                </div>
              </section>
            </div>
          </div>

          <div v-else-if="wellbeingArticles.length" class="mt-5 overflow-x-auto">
            <div v-if="selectedWellbeingArticleGroup" class="space-y-5">
              <div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                <button class="btn-secondary" type="button" @click="selectedWellbeingArticleCategory = null">
                  <span aria-hidden="true">←</span>
                  <span>Retour aux categories</span>
                </button>
                <span class="glass-chip">{{ selectedWellbeingArticleGroup.items.length }} articles</span>
              </div>
              <table class="min-w-full text-left text-sm">
                <thead class="text-xs uppercase tracking-[0.2em] aurora-muted">
                  <tr>
                    <th class="py-3 pr-4">Icone</th>
                    <th class="py-3 pr-4">Nom</th>
                    <th class="py-3 pr-4">Unite</th>
                    <th class="py-3 pr-4">Vendeurs</th>
                    <th class="py-3 pr-4">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  <tr class="border-t border-white/10 bg-white/5">
                    <td colspan="5" class="py-3 pr-4 text-xs font-semibold uppercase tracking-[0.24em] aurora-muted">
                      {{ selectedWellbeingArticleGroup.category }}
                    </td>
                  </tr>
                  <tr v-for="article in selectedWellbeingArticleGroup.items" :key="article.id" class="border-t border-white/10">
                    <td class="py-3 pr-4 text-xl">{{ article.icone || "🧴" }}</td>
                    <td class="py-3 pr-4">{{ article.nom }}</td>
                    <td class="py-3 pr-4">{{ article.unite_base }}</td>
                    <td class="py-3 pr-4">{{ article.vendor_ids.length }}</td>
                    <td class="py-3 pr-4">
                      <div class="flex flex-wrap gap-2">
                        <button class="btn-secondary px-3" type="button" title="Details" aria-label="Details" @click="openWellbeingArticleDetailModal(article)">👁️</button>
                        <button class="btn-secondary px-3" type="button" title="Modifier" aria-label="Modifier" @click="openWellbeingArticleEditModal(article)">✏️</button>
                        <button class="btn-secondary px-3" type="button" title="Supprimer" aria-label="Supprimer" @click="deleteWellbeingArticle(article.id)">🗑️</button>
                      </div>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
            <table v-else class="min-w-full text-left text-sm">
              <thead class="text-xs uppercase tracking-[0.2em] aurora-muted">
                <tr>
                  <th class="py-3 pr-4">Categorie</th>
                  <th class="py-3 pr-4">Apercu</th>
                  <th class="py-3 pr-4">Total</th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="group in groupedWellbeingArticlesForAdmin"
                  :key="group.category"
                  class="cursor-pointer border-t border-white/10 transition hover:bg-white/5"
                  @click="selectedWellbeingArticleCategory = group.category"
                >
                  <td class="py-3 pr-4 font-semibold">{{ group.category }}</td>
                  <td class="py-3 pr-4">
                    <div class="flex flex-wrap items-center gap-3">
                      <span
                        v-for="article in group.items.slice(0, 3)"
                        :key="`wa-table-preview-${group.category}-${article.id}`"
                        class="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-3 py-1 text-xs"
                      >
                        <span>{{ article.icone || "🧴" }}</span>
                        <span>{{ article.nom }}</span>
                      </span>
                    </div>
                  </td>
                  <td class="py-3 pr-4">
                    <span class="glass-chip">{{ group.items.length }}</span>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
          <p v-else class="mt-5 text-sm aurora-muted">Aucun article bien-etre charge pour le moment.</p>
        </div>
      </section>

      <section v-if="catalogTab === 'wellbeing-article-prices'" class="space-y-6">
        <div class="panel p-8">
          <div class="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
            <div>
              <h3 class="text-2xl font-semibold">Prix articles bien-etre</h3>
              <p class="mt-2 text-sm aurora-subtle">Meme logique que pour les ingredients, par article puis par vendeur.</p>
            </div>
            <select v-model.number="catalogCityFilter" class="field lg:w-72">
              <option :value="0">Toutes les villes</option>
              <option v-for="city in cities" :key="city.id" :value="city.id">{{ city.nom }}</option>
            </select>
          </div>

          <div class="mt-4 grid gap-4 md:grid-cols-2">
            <article v-for="article in wellbeingArticles" :key="`price-article-${article.id}`" class="glass-card p-4">
              <div class="flex items-start justify-between gap-3">
                <div class="min-w-0">
                  <h4 class="truncate text-lg font-semibold">{{ article.icone || "🧴" }} {{ article.nom }}</h4>
                  <p class="mt-1 text-sm aurora-subtle">{{ article.categorie || "Sans categorie" }}</p>
                </div>
                <button class="btn-secondary px-3 text-xs" type="button" @click="startWellbeingArticlePriceCreateForArticle(article.id)">
                  Ajouter prix
                </button>
              </div>

              <form class="mt-4 grid gap-3 rounded-2xl border border-white/10 bg-white/5 p-4" @submit.prevent="saveWellbeingArticlePrice(article.id)">
                <select v-model.number="getWellbeingArticlePriceDraft(article.id).vendor" class="field">
                  <option :value="0">Choisir un vendeur</option>
                  <option v-for="vendor in priceVendorOptions" :key="`wa-price-${article.id}-${vendor.id}`" :value="vendor.id">
                    {{ vendor.nom }} - {{ vendor.city_nom }}
                  </option>
                </select>
                <div class="grid gap-3 sm:grid-cols-2">
                  <input v-model="getWellbeingArticlePriceDraft(article.id).prix" class="field" inputmode="decimal" type="text" placeholder="Prix (optionnel)" />
                  <input v-model="getWellbeingArticlePriceDraft(article.id).date_dernier_prix" class="field" type="date" />
                </div>
                <div class="flex flex-wrap gap-3">
                  <button class="btn-primary" type="submit">
                    {{ getWellbeingArticlePriceDraft(article.id).editId ? 'Mettre a jour' : 'Enregistrer' }}
                  </button>
                  <button v-if="getWellbeingArticlePriceDraft(article.id).editId" class="btn-secondary" type="button" @click="cancelWellbeingArticlePriceEdit(article.id)">
                    Annuler
                  </button>
                </div>
              </form>

              <div class="mt-4 space-y-2">
                <article v-for="price in getPricesForWellbeingArticle(article.id)" :key="price.id" class="rounded-2xl border border-white/10 bg-white/5 px-4 py-3">
                  <div class="flex items-start justify-between gap-3">
                    <div>
                      <p class="font-medium">{{ price.vendor_nom }}</p>
                      <p class="text-sm aurora-muted">{{ price.city_nom }}</p>
                      <p class="mt-1 text-sm aurora-subtle">{{ formatCurrency(price.prix) }} · {{ price.date_dernier_prix }}</p>
                    </div>
                    <div class="flex gap-2">
                      <button class="btn-secondary px-3 text-xs" type="button" @click="startWellbeingArticlePriceEdit(price)">✏️</button>
                      <button class="btn-secondary px-3 text-xs" type="button" @click="deleteWellbeingArticlePrice(price.id)">🗑️</button>
                    </div>
                  </div>
                </article>
                <p v-if="!getPricesForWellbeingArticle(article.id).length" class="text-sm aurora-muted">Aucun prix enregistre pour cet article.</p>
              </div>
            </article>
          </div>
        </div>
      </section>
    </section>

    <section v-if="activeSection === 'coach'" class="grid gap-6 xl:grid-cols-[0.85fr_1.15fr]">
      <form class="panel space-y-4 p-8" @submit.prevent="assignWorkoutPlan">
        <h2 class="text-2xl font-semibold">Assigner un programme</h2>
        <select v-model.number="coachForm.user_id" class="field">
          <option :value="0">Choisir un utilisateur</option>
          <option v-for="user in users" :key="user.id" :value="user.id">{{ user.username }}</option>
        </select>
        <input v-model="coachForm.date_debut" class="field" type="date" />
        <select v-model.number="coachForm.frequence_semaine" class="field">
          <option :value="2">2 seances</option>
          <option :value="3">3 seances</option>
          <option :value="4">4 seances</option>
          <option :value="5">5 seances</option>
        </select>
        <select v-model.number="coachForm.duree_semaines" class="field">
          <option :value="4">Cycle 4 semaines</option>
          <option :value="6">Cycle 6 semaines</option>
          <option :value="8">Cycle 8 semaines</option>
        </select>
        <button class="btn-primary" type="submit">Generer pour cet utilisateur</button>
      </form>

      <div class="panel p-8">
        <div class="flex items-center justify-between gap-4">
          <h2 class="text-2xl font-semibold">Adherence du programme</h2>
          <button class="btn-secondary" type="button" @click="loadAdherence">Actualiser</button>
        </div>
        <div v-if="adherenceData?.summary" class="mt-5 grid gap-4 md:grid-cols-3">
          <article class="glass-card p-4">
            <p class="text-sm aurora-subtle">Items prevus</p>
            <p class="mt-2 text-2xl font-semibold">{{ adherenceData.summary.total_items }}</p>
          </article>
          <article class="glass-card p-4">
            <p class="text-sm aurora-subtle">Items termines</p>
            <p class="mt-2 text-2xl font-semibold">{{ adherenceData.summary.completed_items }}</p>
          </article>
          <article class="glass-card p-4">
            <p class="text-sm aurora-subtle">Adherence</p>
            <p class="mt-2 text-2xl font-semibold">{{ adherenceData.summary.adherence_rate }}%</p>
          </article>
        </div>
        <div v-if="adherenceData?.insights" class="mt-5 grid gap-4 md:grid-cols-2">
          <article class="glass-card p-4">
            <h3 class="text-lg font-semibold">Poids</h3>
            <p class="mt-2 text-sm aurora-subtle">{{ adherenceData.insights.weight_message }}</p>
          </article>
          <article class="glass-card p-4">
            <h3 class="text-lg font-semibold">Alimentation</h3>
            <p class="mt-2 text-sm aurora-subtle">{{ adherenceData.insights.meal_message }}</p>
          </article>
          <article class="glass-card p-4">
            <h3 class="text-lg font-semibold">Entrainement</h3>
            <p class="mt-2 text-sm aurora-subtle">{{ adherenceData.insights.sport_message }}</p>
          </article>
          <article class="glass-card p-4">
            <h3 class="text-lg font-semibold">Appreciation auto</h3>
            <p v-for="(line, index) in adherenceData.insights.appreciation" :key="index" class="mt-2 text-sm aurora-subtle">{{ line }}</p>
          </article>
        </div>
        <div class="mt-5 space-y-3">
          <article v-for="item in adherenceData?.items || []" :key="item.id" class="glass-card p-4">
            <div class="flex items-center justify-between gap-4">
              <div>
                <h3 class="text-lg font-semibold">{{ item.exercise_nom }}</h3>
                <p class="text-sm aurora-subtle">{{ item.date_prevue || item.jour_semaine }} - semaine {{ item.semaine_index }}</p>
              </div>
              <span class="rounded-full px-3 py-1 text-xs" :class="item.completed ? 'bg-emerald-300/15 text-emerald-200' : 'bg-amber-300/15 text-amber-200'">
                {{ item.completed ? "Termine" : "En attente" }}
              </span>
            </div>
          </article>
        </div>
      </div>
    </section>

    <section v-if="activeSection === 'ingredients'" class="space-y-6">
      <div class="panel p-8">
        <div class="flex items-start justify-between gap-4">
          <div>
            <h2 class="text-2xl font-semibold">Ingredients existants</h2>
            <p class="mt-2 text-sm aurora-subtle">La liste charge depuis la base de donnees de production.</p>
          </div>
          <div class="flex flex-wrap gap-3">
            <button class="btn-secondary" type="button" @click="ingredientViewMode = ingredientViewMode === 'cards' ? 'table' : 'cards'">
              <span aria-hidden="true">{{ ingredientViewMode === 'cards' ? "📋" : "🪟" }}</span>
              <span>{{ ingredientViewMode === 'cards' ? "Mode tableau" : "Mode cartes" }}</span>
            </button>
            <button class="btn-secondary" type="button" @click="exportIngredientsExcel">
              <span aria-hidden="true">📥</span>
              <span>Exporter Excel</span>
            </button>
            <button class="btn-primary" type="button" @click="openIngredientCreateModal">
              <span aria-hidden="true">➕</span>
              <span>{{ ingredientCreateButtonLabel }}</span>
            </button>
            <span class="glass-chip">{{ ingredients.length }} ingredients</span>
          </div>
        </div>

        <div v-if="ingredients.length && ingredientViewMode === 'cards'" class="mt-5 max-h-[70vh] overflow-y-auto sm:pr-2">
          <div v-if="selectedIngredientGroup" class="space-y-5">
            <div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <button class="btn-secondary" type="button" @click="selectedIngredientCategory = null">
                <span aria-hidden="true">←</span>
                <span>Retour aux categories</span>
              </button>
              <span class="glass-chip">{{ selectedIngredientGroup.items.length }} ingredients</span>
            </div>
            <div class="glass-card p-5">
              <p class="text-xs uppercase tracking-[0.24em] aurora-muted">Categorie</p>
              <h3 class="mt-2 text-xl font-semibold">{{ selectedIngredientGroup.category }}</h3>
            </div>
            <div class="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
              <article
                v-for="summary in getIngredientCategoryHighlights(selectedIngredientGroup.items)"
                :key="summary.key"
                :class="summary.tone"
                class="glass-card border p-4"
              >
                <p class="text-xs uppercase tracking-[0.2em] aurora-muted">{{ summary.label }}</p>
                <p class="mt-2 text-lg font-semibold">{{ summary.icon }} {{ summary.name }}</p>
                <p class="mt-1 text-sm aurora-subtle">{{ summary.value }}</p>
              </article>
            </div>
            <div class="grid gap-3 md:grid-cols-2">
              <article v-for="ingredient in selectedIngredientGroup.items" :key="ingredient.id" class="glass-card min-w-0 overflow-hidden p-4">
                <img
                  v-if="resolveImageSrc(ingredient)"
                  :src="resolveImageSrc(ingredient)"
                  :alt="ingredient.nom"
                  class="mb-3 h-28 w-full rounded-2xl object-cover sm:h-36"
                  :style="ingredientImageStyle(ingredient)"
                />
                <div v-else class="mb-3 flex h-28 w-full items-center justify-center rounded-2xl border border-white/10 bg-white/5 text-sm aurora-muted sm:h-36">
                  Aucun visuel
                </div>
                <div class="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                  <div class="min-w-0 flex-1">
                    <h3 class="truncate text-lg font-semibold">{{ ingredient.icone || "🥒" }} {{ ingredient.nom }}</h3>
                    <p class="mt-2 text-sm aurora-subtle">{{ ingredient.categorie || "Sans categorie" }}</p>
                    <div class="mt-2 flex flex-wrap gap-2">
                      <span v-if="ingredient.is_perishable" class="glass-chip">Perissable</span>
                      <span v-if="ingredient.is_perishable && ingredient.max_storage_days" class="glass-chip">{{ ingredient.max_storage_days }} jour(s) max</span>
                    </div>
                    <div class="mt-3 max-w-full overflow-x-auto pb-1">
                      <div class="flex w-max min-w-full gap-2 whitespace-nowrap pr-1">
                      <span
                        v-for="badge in getIngredientComparisonBadges(ingredient, selectedIngredientGroup.items)"
                        :key="`${ingredient.id}-${badge.label}`"
                        :class="badge.tone"
                        class="inline-flex shrink-0 items-center gap-2 rounded-full border px-2.5 py-0.5 text-[11px]"
                      >
                        <span>{{ badge.icon }}</span>
                        <span>{{ badge.label }}</span>
                      </span>
                      </div>
                    </div>
                  </div>
                  <div class="flex shrink-0 items-center gap-1 self-end sm:self-start">
                    <button class="btn-secondary px-2 py-1.5 text-xs" type="button" title="Details" aria-label="Details" @click="openIngredientDetailModal(ingredient)">👁️</button>
                    <button class="btn-secondary px-2 py-1.5 text-xs" type="button" title="Modifier" aria-label="Modifier" @click="openIngredientEditModal(ingredient)">✏️</button>
                    <button class="btn-secondary px-2 py-1.5 text-xs" type="button" title="Supprimer" aria-label="Supprimer" @click="deleteIngredient(ingredient.id)">🗑️</button>
                  </div>
                </div>
                <p v-if="ingredient.preparation" class="mt-2 text-sm aurora-muted">{{ ingredient.preparation }}</p>
                <div class="mt-4 grid gap-2 text-sm aurora-muted sm:grid-cols-2">
                  <p>
                    <span class="aurora-subtle">Calories:</span>
                    <span :class="getIngredientMetricValueClass(ingredient, selectedIngredientGroup.items, 'calories_100g')">{{ ingredient.calories_100g }}</span> kcal / 100g
                  </p>
                  <p>
                    <span class="aurora-subtle">Proteines:</span>
                    <span :class="getIngredientMetricValueClass(ingredient, selectedIngredientGroup.items, 'proteines_100g')">{{ ingredient.proteines_100g }}</span> g / 100g
                  </p>
                  <p>
                    <span class="aurora-subtle">Glucides:</span>
                    <span :class="getIngredientMetricValueClass(ingredient, selectedIngredientGroup.items, 'glucides_100g')">{{ ingredient.glucides_100g }}</span> g / 100g
                  </p>
                  <p>
                    <span class="aurora-subtle">Lipides:</span>
                    <span :class="getIngredientMetricValueClass(ingredient, selectedIngredientGroup.items, 'lipides_100g')">{{ ingredient.lipides_100g }}</span> g / 100g
                  </p>
                </div>
                <div v-if="ingredient.micronutrient_tag_labels?.length" class="mt-4">
                  <p class="text-[11px] uppercase tracking-[0.2em] aurora-muted">Micronutriments</p>
                  <div class="mt-2 flex flex-wrap gap-2">
                    <span
                      v-for="tag in ingredient.micronutrient_tag_labels"
                      :key="`card-micro-${ingredient.id}-${tag}`"
                      class="glass-chip"
                    >
                      {{ tag }}
                    </span>
                  </div>
                </div>
                <div v-if="ingredient.benefit_tag_labels?.length" class="mt-4">
                  <p class="text-[11px] uppercase tracking-[0.2em] aurora-muted">Vertus</p>
                  <div class="mt-2 flex flex-wrap gap-2">
                    <span
                      v-for="tag in ingredient.benefit_tag_labels"
                      :key="`card-benefit-${ingredient.id}-${tag}`"
                      class="glass-chip"
                    >
                      {{ tag }}
                    </span>
                  </div>
                </div>
                <div v-if="ingredient.drawback_tag_labels?.length" class="mt-4">
                  <p class="text-[11px] uppercase tracking-[0.2em] aurora-muted">Inconvenients</p>
                  <div class="mt-2 flex flex-wrap gap-2">
                    <span
                      v-for="tag in ingredient.drawback_tag_labels"
                      :key="`card-drawback-${ingredient.id}-${tag}`"
                      class="glass-chip"
                    >
                      {{ tag }}
                    </span>
                  </div>
                </div>
              </article>
            </div>
          </div>
          <div v-else class="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            <section v-for="group in groupedIngredients" :key="group.category" class="space-y-3">
              <button
                class="glass-card flex w-full min-w-0 items-center justify-between gap-3 p-4 text-left transition hover:bg-white/10"
                type="button"
                @click="selectedIngredientCategory = group.category"
              >
                <span class="min-w-0 truncate">{{ group.category }}</span>
                <span class="glass-chip shrink-0">{{ group.items.length }}</span>
              </button>
              <div class="glass-card -mt-1 overflow-hidden p-0">
                <div class="divide-y divide-white/10">
                  <div
                    v-for="ingredient in group.items.slice(0, 4)"
                    :key="`preview-${group.category}-${ingredient.id}`"
                    class="flex items-center justify-between gap-3 px-4 py-3"
                  >
                    <div class="flex min-w-0 items-center gap-3">
                      <span class="text-xl">{{ ingredient.icone || "🥒" }}</span>
                      <span class="truncate text-sm text-stone-100">{{ ingredient.nom }}</span>
                    </div>
                    <span class="text-xs aurora-muted">{{ ingredient.unite_base }}</span>
                  </div>
                </div>
                <p v-if="group.items.length > 4" class="px-4 py-3 text-xs aurora-muted">
                  + {{ group.items.length - 4 }} autres ingredients
                </p>
              </div>
              <div v-if="false" class="grid gap-3 md:grid-cols-2">
                <article v-for="ingredient in group.items" :key="ingredient.id" class="glass-card p-4">
                  <img
                    v-if="resolveImageSrc(ingredient)"
                    :src="resolveImageSrc(ingredient)"
                    :alt="ingredient.nom"
                    class="mb-3 h-36 w-full rounded-2xl object-cover"
                    :style="ingredientImageStyle(ingredient)"
                  />
                  <div v-else class="mb-3 flex h-36 w-full items-center justify-center rounded-2xl border border-white/10 bg-white/5 text-sm aurora-muted">
                    Aucun visuel
                  </div>
                  <div class="flex items-start justify-between gap-3">
                    <div>
                      <h3 class="text-lg font-semibold">{{ ingredient.icone || "🥒" }} {{ ingredient.nom }}</h3>
                      <p class="mt-2 text-sm aurora-subtle">{{ ingredient.categorie || "Sans categorie" }}</p>
                    </div>
                    <div class="flex items-center gap-1">
                      <button class="btn-secondary px-2 py-1.5 text-xs" type="button" title="Details" aria-label="Details" @click="openIngredientDetailModal(ingredient)">👁️</button>
                      <button class="btn-secondary px-2 py-1.5 text-xs" type="button" title="Modifier" aria-label="Modifier" @click="openIngredientEditModal(ingredient)">✏️</button>
                      <button class="btn-secondary px-2 py-1.5 text-xs" type="button" title="Supprimer" aria-label="Supprimer" @click="deleteIngredient(ingredient.id)">🗑️</button>
                    </div>
                  </div>
                  <p v-if="ingredient.preparation" class="mt-2 text-sm aurora-muted">{{ ingredient.preparation }}</p>
                  <div class="mt-4 grid gap-2 text-sm aurora-muted sm:grid-cols-2">
                    <p><span class="aurora-subtle">Calories:</span> {{ ingredient.calories_100g }} kcal / 100g</p>
                    <p><span class="aurora-subtle">Proteines:</span> {{ ingredient.proteines_100g }} g / 100g</p>
                    <p><span class="aurora-subtle">Glucides:</span> {{ ingredient.glucides_100g }} g / 100g</p>
                    <p><span class="aurora-subtle">Lipides:</span> {{ ingredient.lipides_100g }} g / 100g</p>
                  </div>
                </article>
              </div>
            </section>
          </div>
        </div>

        <div v-else-if="ingredients.length" class="mt-5 overflow-x-auto">
          <div v-if="selectedIngredientGroup" class="space-y-5">
            <div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <button class="btn-secondary" type="button" @click="selectedIngredientCategory = null">
                <span aria-hidden="true">←</span>
                <span>Retour aux categories</span>
              </button>
              <span class="glass-chip">{{ selectedIngredientGroup.items.length }} ingredients</span>
            </div>
            <table class="min-w-full text-left text-sm">
              <thead class="text-xs uppercase tracking-[0.2em] aurora-muted">
                <tr>
                  <th class="py-3 pr-4">Icone</th>
                  <th class="py-3 pr-4">Nom</th>
                  <th class="py-3 pr-4">Unite</th>
                  <th class="py-3 pr-4">Calories</th>
                  <th class="py-3 pr-4">Actions</th>
                </tr>
              </thead>
              <tbody>
                <tr class="border-t border-white/10 bg-white/5">
                  <td colspan="6" class="py-3 pr-4 text-xs font-semibold uppercase tracking-[0.24em] aurora-muted">
                    {{ selectedIngredientGroup.category }}
                  </td>
                </tr>
                <tr v-for="ingredient in selectedIngredientGroup.items" :key="ingredient.id" class="border-t border-white/10">
                  <td class="py-3 pr-4 text-xl">{{ ingredient.icone || "🥒" }}</td>
                  <td class="py-3 pr-4">{{ ingredient.nom }}</td>
                  <td class="py-3 pr-4">
                    <div>{{ ingredient.unite_base }}</div>
                    <div v-if="ingredient.is_perishable" class="text-xs aurora-subtle">
                      {{ ingredient.max_storage_days ? `${ingredient.max_storage_days} j max` : "Perissable" }}
                    </div>
                  </td>
                  <td class="py-3 pr-4">{{ ingredient.calories_100g }} kcal</td>
                  <td class="py-3 pr-4">
                    <div class="flex flex-wrap gap-2">
                      <button class="btn-secondary px-3" type="button" title="Details" aria-label="Details" @click="openIngredientDetailModal(ingredient)">👁️</button>
                      <button class="btn-secondary px-3" type="button" title="Modifier" aria-label="Modifier" @click="openIngredientEditModal(ingredient)">✏️</button>
                      <button class="btn-secondary px-3" type="button" title="Supprimer" aria-label="Supprimer" @click="deleteIngredient(ingredient.id)">🗑️</button>
                    </div>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
          <table v-else class="min-w-full text-left text-sm">
            <thead class="text-xs uppercase tracking-[0.2em] aurora-muted">
              <tr>
                <th class="py-3 pr-4">Categorie</th>
                <th class="py-3 pr-4">Apercu</th>
                <th class="py-3 pr-4">Total</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="group in groupedIngredients"
                :key="group.category"
                class="cursor-pointer border-t border-white/10 transition hover:bg-white/5"
                @click="selectedIngredientCategory = group.category"
              >
                <td class="py-3 pr-4 font-semibold">{{ group.category }}</td>
                <td class="py-3 pr-4">
                  <div class="flex flex-wrap items-center gap-3">
                    <span
                      v-for="ingredient in group.items.slice(0, 3)"
                      :key="`table-preview-${group.category}-${ingredient.id}`"
                      class="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-3 py-1 text-xs"
                    >
                      <span>{{ ingredient.icone || "🥒" }}</span>
                      <span>{{ ingredient.nom }}</span>
                    </span>
                  </div>
                </td>
                <td class="py-3 pr-4">
                  <span class="glass-chip">{{ group.items.length }}</span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
<p v-else class="mt-5 text-sm aurora-muted">Aucun ingredient charge pour le moment.</p>
      </div>
    </section>

    <section v-if="activeSection === 'recipes'" class="space-y-6">
      <div class="panel p-8">
        <div class="flex items-start justify-between gap-4">
          <div>
            <h2 class="text-2xl font-semibold">Recettes</h2>
            <p class="mt-2 text-sm aurora-subtle">Bibliotheque des recettes regroupee par moment de repas.</p>
          </div>
          <div class="flex flex-wrap gap-3">
            <button class="btn-secondary" type="button" @click="recipeViewMode = recipeViewMode === 'cards' ? 'table' : 'cards'">
              <span aria-hidden="true">{{ recipeViewMode === 'cards' ? "📋" : "🪟" }}</span>
              <span>{{ recipeViewMode === 'cards' ? "Mode tableau" : "Mode cartes" }}</span>
            </button>
            <button class="btn-primary" type="button" @click="openRecipeCreateModal">
              <span aria-hidden="true">➕</span>
              <span>Ajouter une recette</span>
            </button>
            <span class="glass-chip">{{ recipes.length }} recettes</span>
          </div>
        </div>

        <div v-if="recipes.length && recipeViewMode === 'cards'" class="mt-5">
          <div v-if="selectedRecipeGroup" class="space-y-5">
            <div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <button class="btn-secondary" type="button" @click="selectedRecipeCategory = null">
                <span aria-hidden="true">←</span>
                <span>Retour aux categories</span>
              </button>
              <span class="glass-chip">{{ selectedRecipeGroup.items.length }} recettes</span>
            </div>
            <div class="glass-card p-5">
              <p class="text-xs uppercase tracking-[0.24em] aurora-muted">Categorie</p>
              <h3 class="mt-2 text-xl font-semibold">{{ selectedRecipeGroup.category }}</h3>
            </div>
            <div class="grid gap-3 md:grid-cols-2">
              <article v-for="recipe in selectedRecipeGroup.items" :key="recipe.id" class="glass-card min-w-0 overflow-hidden p-4">
                <img v-if="resolveImageSrc(recipe)" :src="resolveImageSrc(recipe)" :alt="recipe.nom" class="mb-3 h-40 w-full rounded-2xl object-cover" />
                <div v-else class="mb-3 flex h-40 w-full items-center justify-center rounded-2xl border border-white/10 bg-white/5 text-sm aurora-muted">
                  Aucun visuel
                </div>
                <div class="flex items-start justify-between gap-3">
                  <div class="min-w-0">
                    <h3 class="truncate text-lg font-semibold">{{ recipeIcon(recipe) }} {{ recipe.nom }}</h3>
                    <p class="mt-2 text-sm aurora-subtle">{{ formatRecipeCategoryLabel(recipe.categorie_repas) }}</p>
                    <p class="text-sm aurora-muted">{{ formatRecipeObjectiveLabel(recipe.objectif_adapte) }}</p>
                    <div class="mt-3 flex max-w-full gap-2 overflow-x-auto pb-1">
                      <span
                        v-for="badge in getRecipeComparisonBadges(recipe, selectedRecipeGroup.items)"
                        :key="`${recipe.id}-${badge.label}`"
                        :class="badge.tone"
                        class="inline-flex shrink-0 items-center gap-2 rounded-full border px-2.5 py-0.5 text-[11px]"
                      >
                        <span>{{ badge.icon }}</span>
                        <span>{{ badge.label }}</span>
                      </span>
                    </div>
                  </div>
                  <div class="flex items-center gap-1">
                    <button class="btn-secondary px-2 py-1.5 text-xs" type="button" title="Details" aria-label="Details" @click="openRecipeDetailModal(recipe)">👁️</button>
                    <button class="btn-secondary px-2 py-1.5 text-xs" type="button" title="Modifier" aria-label="Modifier" @click="openRecipeEditModal(recipe)">✏️</button>
                    <button class="btn-secondary px-2 py-1.5 text-xs" type="button" title="Supprimer" aria-label="Supprimer" @click="deleteRecipe(recipe.id)">🗑️</button>
                  </div>
                </div>
                <p v-if="recipe.preparation" class="mt-3 whitespace-pre-line text-sm aurora-subtle">{{ recipe.preparation }}</p>
                <div class="mt-3 grid gap-2 text-sm aurora-muted sm:grid-cols-2">
                  <p><span class="aurora-subtle">Calories:</span> {{ formatCurrency(getRecipeMetrics(recipe).calories) }} kcal</p>
                  <p><span class="aurora-subtle">Proteines:</span> {{ formatCurrency(getRecipeMetrics(recipe).proteines) }} g</p>
                  <p><span class="aurora-subtle">Glucides:</span> {{ formatCurrency(getRecipeMetrics(recipe).glucides) }} g</p>
                  <p><span class="aurora-subtle">Lipides:</span> {{ formatCurrency(getRecipeMetrics(recipe).lipides) }} g</p>
                  <p class="sm:col-span-2">
                    <span class="aurora-subtle">Cout minimum estime:</span>
                    {{ getRecipeMetrics(recipe).hasPrice ? `${formatCurrency(getRecipeMetrics(recipe).cout)}` : "Indisponible" }}
                  </p>
                </div>
                <div class="mt-3 space-y-1 text-sm aurora-muted">
                  <p v-for="ingredient in recipe.recipe_ingredients" :key="`${recipe.id}-${ingredient.ingredient}-${ingredient.unite}`">
                    {{ ingredient.ingredient_nom }} - {{ ingredient.quantite }} {{ ingredient.unite }}
                  </p>
                </div>
              </article>
            </div>
          </div>
          <div v-else class="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            <section v-for="group in groupedRecipes" :key="group.category" class="space-y-3">
              <button class="glass-card flex w-full min-w-0 items-center justify-between gap-3 p-4 text-left transition hover:bg-white/10" type="button" @click="selectedRecipeCategory = group.category">
                <span class="min-w-0 truncate">{{ group.category }}</span>
                <span class="glass-chip shrink-0">{{ group.items.length }}</span>
              </button>
              <div class="glass-card -mt-1 overflow-hidden p-0">
                <div class="divide-y divide-white/10">
                  <div v-for="recipe in group.items.slice(0, 4)" :key="`preview-recipe-${group.category}-${recipe.id}`" class="flex items-center justify-between gap-3 px-4 py-3">
                    <div class="min-w-0">
                      <p class="truncate text-sm text-stone-100">{{ recipe.nom }}</p>
                      <p class="text-[11px] aurora-muted">{{ formatRecipeObjectiveLabel(recipe.objectif_adapte) }}</p>
                    </div>
                    <span class="text-xs aurora-muted">{{ formatCurrency(getRecipeMetrics(recipe).calories) }} kcal</span>
                  </div>
                </div>
                <p v-if="group.items.length > 4" class="px-4 py-3 text-xs aurora-muted">+ {{ group.items.length - 4 }} autres recettes</p>
              </div>
            </section>
          </div>
        </div>

        <div v-else-if="recipes.length" class="mt-5 overflow-x-auto">
          <div v-if="selectedRecipeGroup" class="space-y-5">
            <div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <button class="btn-secondary" type="button" @click="selectedRecipeCategory = null">
                <span aria-hidden="true">←</span>
                <span>Retour aux categories</span>
              </button>
              <span class="glass-chip">{{ selectedRecipeGroup.items.length }} recettes</span>
            </div>
            <table class="min-w-full text-left text-sm">
              <thead class="text-xs uppercase tracking-[0.2em] aurora-muted">
                <tr>
                  <th class="py-3 pr-4">Nom</th>
                  <th class="py-3 pr-4">Objectif</th>
                  <th class="py-3 pr-4">Ingredients</th>
                  <th class="py-3 pr-4">Actions</th>
                </tr>
              </thead>
              <tbody>
                <tr class="border-t border-white/10 bg-white/5">
                  <td colspan="4" class="py-3 pr-4 text-xs font-semibold uppercase tracking-[0.24em] aurora-muted">{{ selectedRecipeGroup.category }}</td>
                </tr>
                <tr v-for="recipe in selectedRecipeGroup.items" :key="recipe.id" class="border-t border-white/10">
                  <td class="py-3 pr-4">{{ recipeIcon(recipe) }} {{ recipe.nom }}</td>
                  <td class="py-3 pr-4">{{ formatRecipeObjectiveLabel(recipe.objectif_adapte) }}</td>
                  <td class="py-3 pr-4">{{ recipe.recipe_ingredients.length }} · {{ formatCurrency(getRecipeMetrics(recipe).calories) }} kcal</td>
                  <td class="py-3 pr-4">
                    <div class="flex flex-wrap gap-2">
                      <button class="btn-secondary px-3" type="button" title="Details" aria-label="Details" @click="openRecipeDetailModal(recipe)">👁️</button>
                      <button class="btn-secondary px-3" type="button" title="Modifier" aria-label="Modifier" @click="openRecipeEditModal(recipe)">✏️</button>
                      <button class="btn-secondary px-3" type="button" title="Supprimer" aria-label="Supprimer" @click="deleteRecipe(recipe.id)">🗑️</button>
                    </div>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
          <table v-else class="min-w-full text-left text-sm">
            <thead class="text-xs uppercase tracking-[0.2em] aurora-muted">
              <tr>
                <th class="py-3 pr-4">Categorie</th>
                <th class="py-3 pr-4">Apercu</th>
                <th class="py-3 pr-4">Total</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="group in groupedRecipes" :key="group.category" class="cursor-pointer border-t border-white/10 transition hover:bg-white/5" @click="selectedRecipeCategory = group.category">
                <td class="py-3 pr-4 font-semibold">{{ group.category }}</td>
                <td class="py-3 pr-4">
                  <div class="flex flex-wrap items-center gap-3">
                    <span v-for="recipe in group.items.slice(0, 3)" :key="`table-preview-recipe-${group.category}-${recipe.id}`" class="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-3 py-1 text-xs">
                      <span>{{ recipeIcon(recipe) }} {{ recipe.nom }}</span>
                    </span>
                  </div>
                </td>
                <td class="py-3 pr-4"><span class="glass-chip">{{ group.items.length }}</span></td>
              </tr>
            </tbody>
          </table>
        </div>
        <p v-else class="mt-5 text-sm aurora-muted">Aucune recette chargee pour le moment.</p>
      </div>
    </section>

    <section v-if="activeSection === 'exercises'" class="space-y-6">
      <div class="panel p-8">
        <div class="flex items-start justify-between gap-4">
          <div>
            <h2 class="text-2xl font-semibold">Exercices existants</h2>
            <p class="mt-2 text-sm aurora-subtle">Bibliotheque des exercices regroupes par groupe musculaire.</p>
          </div>
          <div class="flex flex-wrap gap-3">
            <button class="btn-secondary" type="button" @click="showOnlyIncompleteExercises = !showOnlyIncompleteExercises">
              <span aria-hidden="true">{{ showOnlyIncompleteExercises ? "✅" : "🧩" }}</span>
              <span>{{ showOnlyIncompleteExercises ? "Voir tous" : "A completer" }}</span>
            </button>
            <button class="btn-secondary" type="button" @click="prefillAllIncompleteExercises">
              <span aria-hidden="true">⚙️</span>
              <span>Pre-remplir les incomplets</span>
            </button>
            <button class="btn-secondary" type="button" @click="exerciseViewMode = exerciseViewMode === 'cards' ? 'table' : 'cards'">
              <span aria-hidden="true">{{ exerciseViewMode === 'cards' ? "📋" : "🪟" }}</span>
              <span>{{ exerciseViewMode === 'cards' ? "Mode tableau" : "Mode cartes" }}</span>
            </button>
            <button class="btn-primary" type="button" @click="openExerciseCreateModal">
              <span aria-hidden="true">➕</span>
              <span>Ajouter un exercice</span>
            </button>
            <span class="glass-chip">{{ exercises.length }} exercices</span>
          </div>
        </div>

        <div v-if="exercises.length && exerciseViewMode === 'cards'" class="mt-5">
          <div v-if="selectedExerciseGroup" class="space-y-5">
            <div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <button class="btn-secondary" type="button" @click="selectedExerciseGroupKey = null">
                <span aria-hidden="true">←</span>
                <span>Retour aux groupes</span>
              </button>
              <span class="glass-chip">{{ selectedExerciseGroup.items.length }} exercices</span>
            </div>
            <div class="glass-card p-5">
              <p class="text-xs uppercase tracking-[0.24em] aurora-muted">Groupe</p>
              <h3 class="mt-2 text-xl font-semibold">{{ selectedExerciseGroup.group }}</h3>
            </div>
            <div class="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
              <article v-for="exercise in selectedExerciseGroup.items" :key="exercise.id" class="glass-card min-w-0 overflow-hidden p-4">
                <img v-if="resolveImageSrc(exercise)" :src="resolveImageSrc(exercise)" :alt="exercise.nom" class="mb-3 h-28 w-full rounded-2xl object-cover sm:h-36" />
                <div v-else class="mb-3 flex h-28 w-full items-center justify-center rounded-2xl border border-white/10 bg-white/5 text-sm aurora-muted sm:h-36">
                  Aucun visuel
                </div>
                <div class="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                  <div class="min-w-0 flex-1">
                    <h3 class="truncate text-lg font-semibold">{{ inferExerciseIcon(exercise) }} {{ exercise.nom }}</h3>
                    <p class="mt-2 text-sm aurora-subtle">{{ formatExerciseGroupLabel(exercise.groupe_musculaire) }}</p>
                    <p class="text-sm aurora-muted">{{ exercise.niveau }}</p>
                    <p v-if="isExerciseAnalysisIncomplete(exercise)" class="mt-2 text-xs font-medium text-amber-200">Analyse a completer</p>
                  </div>
                  <div class="flex shrink-0 items-center gap-1 self-end sm:self-start">
                    <button class="btn-secondary px-2 py-1.5 text-xs" type="button" title="Details" aria-label="Details" @click="openExerciseDetailModal(exercise)">👁️</button>
                    <button class="btn-secondary px-2 py-1.5 text-xs" type="button" title="Modifier" aria-label="Modifier" @click="openExerciseEditModal(exercise)">✏️</button>
                    <button class="btn-secondary px-2 py-1.5 text-xs" type="button" title="Supprimer" aria-label="Supprimer" @click="deleteExercise(exercise.id)">🗑️</button>
                  </div>
                </div>
                <p v-if="exercise.preparation" class="mt-3 whitespace-pre-line text-sm aurora-subtle">{{ exercise.preparation }}</p>
                <p v-if="exercise.description" class="mt-2 whitespace-pre-line text-sm aurora-muted">{{ exercise.description }}</p>
              </article>
            </div>
          </div>
          <div v-else class="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            <section v-for="group in groupedExercises" :key="group.group" class="space-y-3">
              <button class="glass-card flex w-full min-w-0 items-start justify-between gap-4 p-4 text-left transition hover:bg-white/10" type="button" @click="selectedExerciseGroupKey = group.group">
                <div class="flex min-w-0 items-start gap-3">
                  <div class="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl border border-white/10 bg-white/10 text-2xl">
                    {{ inferExerciseGroupIcon(group.items) }}
                  </div>
                  <div class="min-w-0">
                    <p class="text-xs uppercase tracking-[0.24em] aurora-muted">Groupe</p>
                    <h3 class="mt-1 truncate text-lg font-semibold">{{ group.group }}</h3>
                    <p class="mt-1 text-xs aurora-muted">{{ summarizeExerciseLevels(group.items) }}</p>
                    <p v-if="group.items.some((exercise) => isExerciseAnalysisIncomplete(exercise))" class="mt-1 text-xs text-amber-200">
                      {{ group.items.filter((exercise) => isExerciseAnalysisIncomplete(exercise)).length }} a completer
                    </p>
                  </div>
                </div>
                <span class="glass-chip shrink-0">{{ group.items.length }}</span>
              </button>
              <div class="glass-card -mt-1 overflow-hidden p-0">
                <div class="divide-y divide-white/10">
                  <div v-for="exercise in group.items.slice(0, 4)" :key="`preview-exercise-${group.group}-${exercise.id}`" class="flex items-center justify-between gap-3 px-4 py-3">
                    <div class="flex min-w-0 items-center gap-3">
                      <span class="text-xl">{{ inferExerciseIcon(exercise) }}</span>
                      <div class="min-w-0">
                        <p class="truncate text-sm text-stone-100">{{ exercise.nom }}</p>
                        <p class="text-[11px] aurora-muted">{{ formatExerciseLevelLabel(exercise.niveau) }}</p>
                        <p v-if="isExerciseAnalysisIncomplete(exercise)" class="text-[11px] text-amber-200">Analyse a completer</p>
                      </div>
                    </div>
                    <span class="text-xs aurora-muted">›</span>
                  </div>
                </div>
                <p v-if="group.items.length > 4" class="px-4 py-3 text-xs aurora-muted">+ {{ group.items.length - 4 }} autres exercices</p>
              </div>
            </section>
          </div>
        </div>

        <div v-else-if="exercises.length" class="mt-5 overflow-x-auto">
          <div v-if="selectedExerciseGroup" class="space-y-5">
            <div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <button class="btn-secondary" type="button" @click="selectedExerciseGroupKey = null">
                <span aria-hidden="true">←</span>
                <span>Retour aux groupes</span>
              </button>
              <span class="glass-chip">{{ selectedExerciseGroup.items.length }} exercices</span>
            </div>
            <table class="min-w-full text-left text-sm">
              <thead class="text-xs uppercase tracking-[0.2em] aurora-muted">
                <tr>
                  <th class="py-3 pr-4">Icone</th>
                  <th class="py-3 pr-4">Nom</th>
                  <th class="py-3 pr-4">Niveau</th>
                  <th class="py-3 pr-4">Actions</th>
                </tr>
              </thead>
              <tbody>
                <tr class="border-t border-white/10 bg-white/5">
                  <td colspan="5" class="py-3 pr-4 text-xs font-semibold uppercase tracking-[0.24em] aurora-muted">{{ selectedExerciseGroup.group }}</td>
                </tr>
                <tr v-for="exercise in selectedExerciseGroup.items" :key="exercise.id" class="border-t border-white/10">
                  <td class="py-3 pr-4 text-xl">{{ inferExerciseIcon(exercise) }}</td>
                  <td class="py-3 pr-4">
                    <div>
                      <p>{{ exercise.nom }}</p>
                      <p v-if="isExerciseAnalysisIncomplete(exercise)" class="mt-1 text-[11px] text-amber-200">Analyse a completer</p>
                    </div>
                  </td>
                  <td class="py-3 pr-4">{{ exercise.niveau }}</td>
                  <td class="py-3 pr-4">
                    <div class="flex flex-wrap gap-2">
                      <button class="btn-secondary px-3" type="button" title="Details" aria-label="Details" @click="openExerciseDetailModal(exercise)">👁️</button>
                      <button class="btn-secondary px-3" type="button" title="Modifier" aria-label="Modifier" @click="openExerciseEditModal(exercise)">✏️</button>
                      <button class="btn-secondary px-3" type="button" title="Supprimer" aria-label="Supprimer" @click="deleteExercise(exercise.id)">🗑️</button>
                    </div>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
          <table v-else class="min-w-full text-left text-sm">
            <thead class="text-xs uppercase tracking-[0.2em] aurora-muted">
              <tr>
                <th class="py-3 pr-4">Groupe</th>
                <th class="py-3 pr-4">Etat</th>
                <th class="py-3 pr-4">Apercu</th>
                <th class="py-3 pr-4">Total</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="group in groupedExercises" :key="group.group" class="cursor-pointer border-t border-white/10 transition hover:bg-white/5" @click="selectedExerciseGroupKey = group.group">
                <td class="py-3 pr-4 font-semibold">{{ group.group }}</td>
                <td class="py-3 pr-4 text-xs">
                  <span v-if="group.items.some((exercise) => isExerciseAnalysisIncomplete(exercise))" class="text-amber-200">
                    {{ group.items.filter((exercise) => isExerciseAnalysisIncomplete(exercise)).length }} a completer
                  </span>
                  <span v-else class="text-emerald-200">Complet</span>
                </td>
                <td class="py-3 pr-4">
                  <div class="flex flex-wrap items-center gap-3">
                    <span v-for="exercise in group.items.slice(0, 3)" :key="`table-preview-exercise-${group.group}-${exercise.id}`" class="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-3 py-1 text-xs">
                      <span>{{ inferExerciseIcon(exercise) }}</span>
                      <span>{{ exercise.nom }}</span>
                    </span>
                  </div>
                </td>
                <td class="py-3 pr-4"><span class="glass-chip">{{ group.items.length }}</span></td>
              </tr>
            </tbody>
          </table>
        </div>
        <p v-else class="mt-5 text-sm aurora-muted">Aucun exercice charge pour le moment.</p>
      </div>
    </section>

    <div v-if="showIngredientModal" class="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
      <div class="panel max-h-[90vh] w-full max-w-3xl overflow-y-auto p-4 sm:p-8">
        <div class="flex items-start justify-between gap-4">
          <div>
            <h2 class="text-2xl font-semibold">{{ ingredientModalMode === 'edit' ? 'Modifier un ingredient' : ingredientModalMode === 'detail' ? 'Details ingredient' : 'Ajouter un ingredient' }}</h2>
            <p class="mt-2 text-sm aurora-subtle">Gestion detaillee du catalogue ingredient.</p>
          </div>
          <button class="btn-secondary" type="button" @click="closeIngredientModal">Fermer</button>
        </div>

        <div v-if="ingredientModalMode === 'detail' && selectedIngredient" class="mt-6 space-y-4">
          <div class="glass-card p-5">
            <p class="text-3xl">{{ selectedIngredient.icone || "🥒" }}</p>
            <h3 class="mt-3 text-xl font-semibold">{{ selectedIngredient.nom }}</h3>
            <p class="mt-2 text-sm aurora-subtle">{{ selectedIngredient.categorie || "Sans categorie" }}</p>
            <p class="mt-4 text-sm aurora-muted">{{ selectedIngredient.preparation || "Aucune preparation" }}</p>
            <div class="mt-4 flex flex-wrap gap-2">
              <span class="glass-chip">{{ selectedIngredient.is_perishable ? "Perissable" : "Non perissable" }}</span>
              <span v-if="selectedIngredient.is_perishable && selectedIngredient.max_storage_days" class="glass-chip">
                {{ selectedIngredient.max_storage_days }} jour(s) max
              </span>
            </div>
            <div class="mt-4 grid gap-2 text-sm aurora-muted sm:grid-cols-2">
              <p><span class="aurora-subtle">Calories:</span> {{ selectedIngredient.calories_100g }} kcal / 100g</p>
              <p><span class="aurora-subtle">Proteines:</span> {{ selectedIngredient.proteines_100g }} g / 100g</p>
              <p><span class="aurora-subtle">Glucides:</span> {{ selectedIngredient.glucides_100g }} g / 100g</p>
              <p><span class="aurora-subtle">Lipides:</span> {{ selectedIngredient.lipides_100g }} g / 100g</p>
            </div>
            <div v-if="selectedIngredient.micronutrient_tag_labels?.length" class="mt-4 flex flex-wrap gap-2">
              <span
                v-for="tag in selectedIngredient.micronutrient_tag_labels"
                :key="`ingredient-detail-micro-${selectedIngredient.id}-${tag}`"
                class="glass-chip"
              >
                {{ tag }}
              </span>
            </div>
            <div v-if="selectedIngredient.benefit_tag_labels?.length" class="mt-4">
              <p class="text-xs uppercase tracking-[0.2em] aurora-muted">Vertus nutritionnelles</p>
              <div class="mt-2 flex flex-wrap gap-2">
                <span
                  v-for="tag in selectedIngredient.benefit_tag_labels"
                  :key="`ingredient-detail-benefit-${selectedIngredient.id}-${tag}`"
                  class="glass-chip"
                >
                  {{ tag }}
                </span>
              </div>
            </div>
            <div v-if="selectedIngredient.drawback_tag_labels?.length" class="mt-4">
              <p class="text-xs uppercase tracking-[0.2em] aurora-muted">Inconvenients nutritionnels</p>
              <div class="mt-2 flex flex-wrap gap-2">
                <span
                  v-for="tag in selectedIngredient.drawback_tag_labels"
                  :key="`ingredient-detail-drawback-${selectedIngredient.id}-${tag}`"
                  class="glass-chip"
                >
                  {{ tag }}
                </span>
              </div>
            </div>
          </div>
        </div>

        <form v-else class="mt-6 space-y-4" @submit.prevent="saveIngredient">
          <div class="grid gap-4 md:grid-cols-2">
            <input v-model="ingredientForm.nom" class="field" type="text" placeholder="Nom" />
            <input v-model="ingredientForm.icone" class="field" type="text" maxlength="16" placeholder="Icone ex: 🥒" />
            <input
              v-model="ingredientForm.categorie"
              :disabled="isCreateIngredientCategoryLocked"
              :readonly="isCreateIngredientCategoryLocked"
              class="field disabled:cursor-not-allowed disabled:opacity-70"
              type="text"
              placeholder="Categorie"
            />
            <input v-model="ingredientForm.image_url" class="field" type="url" placeholder="URL image" />
          </div>
          <div class="grid gap-4 md:grid-cols-[1fr_220px]">
            <label class="glass-card flex items-center gap-3 p-4">
              <input v-model="ingredientForm.is_perishable" class="h-4 w-4 rounded" type="checkbox" />
              <div>
                <p class="font-medium aurora-title">Produit perissable</p>
                <p class="text-xs aurora-subtle">Utilise une duree max pour la generation des courses.</p>
              </div>
            </label>
            <input
              v-model="ingredientForm.max_storage_days"
              :disabled="!ingredientForm.is_perishable"
              class="field disabled:cursor-not-allowed disabled:opacity-70"
              inputmode="numeric"
              min="0"
              type="number"
              placeholder="Duree max (jours)"
            />
          </div>
          <div class="glass-card space-y-3 p-4">
            <p class="text-sm aurora-subtle">Ou ajouter une photo depuis l'appareil</p>
            <input class="field" type="file" accept="image/*" capture="environment" @change="updateImageSelection('ingredient', $event)" />
            <div v-if="ingredientImagePreview" class="space-y-3">
              <div
                class="relative h-40 w-full overflow-hidden rounded-2xl border border-white/10 bg-black/20"
                :class="ingredientImageDragActive ? 'ring-2 ring-emerald-300/40' : ''"
                @pointerdown="startIngredientImageDrag"
                @pointermove="moveIngredientImageDrag"
                @pointerup="stopIngredientImageDrag"
                @pointerleave="stopIngredientImageDrag"
              >
                <img
                  :src="ingredientImagePreview"
                  alt="Apercu ingredient"
                  class="h-full w-full select-none object-cover"
                  :style="editingIngredientImageStyle"
                  draggable="false"
                />
              </div>
              <div class="grid gap-2 md:grid-cols-[1fr_auto] md:items-center">
                <label class="text-xs aurora-subtle">Zoom</label>
                <div class="flex items-center gap-3">
                  <input v-model="ingredientForm.image_zoom" class="w-48 accent-emerald-400" type="range" min="1" max="3" step="0.05" />
                  <span class="text-xs aurora-subtle">{{ Number(ingredientForm.image_zoom || 1).toFixed(2) }}x</span>
                </div>
              </div>
              <div class="flex items-center justify-between gap-3 text-xs aurora-subtle">
                <span>Glisser l'image pour ajuster le centrage</span>
                <span>{{ Math.round(Number(ingredientForm.image_focus_x || 50)) }}% / {{ Math.round(Number(ingredientForm.image_focus_y || 50)) }}%</span>
              </div>
            </div>
          </div>
          <div class="glass-card space-y-4 p-4">
            <div>
              <p class="font-medium aurora-title">Micronutriments et atouts</p>
              <p class="text-xs aurora-subtle">Selection multiple pour calcium, vitamines, fibres et autres elements utiles.</p>
            </div>
            <div class="grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
              <label
                v-for="option in ingredientMicronutrientOptions"
                :key="`ingredient-micro-${option.value}`"
                class="flex items-center gap-3 rounded-2xl border border-white/10 bg-white/5 px-3 py-2 text-sm"
              >
                <input
                  :checked="ingredientForm.micronutrient_tags.includes(option.value)"
                  class="h-4 w-4 rounded"
                  type="checkbox"
                  @change="toggleIngredientMicronutrient(option.value)"
                />
                <span>{{ option.label }}</span>
              </label>
            </div>
          </div>
          <textarea v-model="ingredientForm.preparation" class="field min-h-[100px]" placeholder="Preparation" />
          <div class="glass-card space-y-4 p-4">
            <div>
              <p class="font-medium aurora-title">Vertus nutritionnelles</p>
              <p class="text-xs aurora-subtle">Choisissez les principaux effets positifs attendus.</p>
            </div>
            <div class="grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
              <label
                v-for="option in ingredientBenefitOptions"
                :key="`ingredient-benefit-${option.value}`"
                class="flex items-center gap-3 rounded-2xl border border-white/10 bg-white/5 px-3 py-2 text-sm"
              >
                <input
                  :checked="ingredientForm.benefit_tags.includes(option.value)"
                  class="h-4 w-4 rounded"
                  type="checkbox"
                  @change="toggleIngredientListValue('benefit_tags', option.value)"
                />
                <span>{{ option.label }}</span>
              </label>
            </div>
          </div>
          <div class="glass-card space-y-4 p-4">
            <div>
              <p class="font-medium aurora-title">Inconvenients nutritionnels</p>
              <p class="text-xs aurora-subtle">Choisissez les limites principales à surveiller.</p>
            </div>
            <div class="grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
              <label
                v-for="option in ingredientDrawbackOptions"
                :key="`ingredient-drawback-${option.value}`"
                class="flex items-center gap-3 rounded-2xl border border-white/10 bg-white/5 px-3 py-2 text-sm"
              >
                <input
                  :checked="ingredientForm.drawback_tags.includes(option.value)"
                  class="h-4 w-4 rounded"
                  type="checkbox"
                  @change="toggleIngredientListValue('drawback_tags', option.value)"
                />
                <span>{{ option.label }}</span>
              </label>
            </div>
          </div>
          <div class="grid gap-4 md:grid-cols-2 xl:grid-cols-5">
            <input v-model="ingredientForm.unite_base" class="field" type="text" placeholder="Unite de base" />
            <input v-model="ingredientForm.calories_100g" class="field" inputmode="decimal" type="text" placeholder="Calories / 100g" />
            <input v-model="ingredientForm.proteines_100g" class="field" inputmode="decimal" type="text" placeholder="Proteines / 100g" />
            <input v-model="ingredientForm.glucides_100g" class="field" inputmode="decimal" type="text" placeholder="Glucides / 100g" />
            <input v-model="ingredientForm.lipides_100g" class="field" inputmode="decimal" type="text" placeholder="Lipides / 100g" />
          </div>
          <div class="flex flex-wrap gap-3">
            <button class="btn-primary" type="submit">{{ ingredientEditId ? "Mettre a jour" : "Enregistrer" }}</button>
            <button class="btn-secondary" type="button" @click="closeIngredientModal">Annuler</button>
          </div>
        </form>
      </div>
    </div>

    <div v-if="showWellbeingArticleModal" class="fixed inset-0 z-50 flex items-center justify-center bg-black/75 p-4">
      <div class="panel max-h-[90vh] w-full max-w-3xl overflow-y-auto p-4 sm:p-8">
        <div class="flex items-start justify-between gap-4">
          <div>
            <h2 class="text-2xl font-semibold">{{ wellbeingArticleModalMode === 'edit' ? 'Modifier un article bien-etre' : wellbeingArticleModalMode === 'detail' ? 'Details article bien-etre' : 'Ajouter un article bien-etre' }}</h2>
            <p class="mt-2 text-sm aurora-subtle">Catalogue des articles non alimentaires relies au bien-etre et aux courses.</p>
          </div>
          <button class="btn-secondary" type="button" @click="closeWellbeingArticleModal">Fermer</button>
        </div>

        <div v-if="wellbeingArticleModalMode === 'detail' && selectedWellbeingArticle" class="mt-6 space-y-4">
          <div class="glass-card p-5">
            <p class="text-3xl">{{ selectedWellbeingArticle.icone || "🧴" }}</p>
            <h3 class="mt-3 text-xl font-semibold">{{ selectedWellbeingArticle.nom }}</h3>
            <p class="mt-2 text-sm aurora-subtle">{{ selectedWellbeingArticle.categorie || "Sans categorie" }}</p>
            <div class="mt-4 flex flex-wrap gap-2">
              <span class="glass-chip">Unite: {{ selectedWellbeingArticle.unite_base || "piece" }}</span>
              <span class="glass-chip">{{ selectedWellbeingArticle.vendor_ids.length }} vendeur(s)</span>
            </div>
            <p v-if="selectedWellbeingArticle.description" class="mt-4 whitespace-pre-line text-sm aurora-muted">{{ selectedWellbeingArticle.description }}</p>
            <div v-if="selectedWellbeingArticle.vendor_ids.length" class="mt-4 flex flex-wrap gap-2">
              <span
                v-for="vendorId in selectedWellbeingArticle.vendor_ids"
                :key="`detail-article-vendor-${selectedWellbeingArticle.id}-${vendorId}`"
                class="glass-chip"
              >
                {{ getVendorName(vendorId) }}
              </span>
            </div>
          </div>
        </div>

        <form v-else class="mt-6 space-y-4" @submit.prevent="saveWellbeingArticle">
          <div class="grid gap-4 md:grid-cols-2">
            <input v-model="wellbeingArticleForm.nom" class="field" type="text" placeholder="Nom" />
            <input v-model="wellbeingArticleForm.icone" class="field" type="text" maxlength="16" placeholder="Icone ex: 🧽" />
            <input
              v-model="wellbeingArticleForm.categorie"
              :disabled="wellbeingArticleModalMode === 'create' && Boolean(selectedWellbeingArticleCategory)"
              :readonly="wellbeingArticleModalMode === 'create' && Boolean(selectedWellbeingArticleCategory)"
              class="field disabled:cursor-not-allowed disabled:opacity-70"
              type="text"
              placeholder="Categorie"
            />
            <input v-model="wellbeingArticleForm.unite_base" class="field" type="text" placeholder="Unite de base ex: piece, litre, paquet" />
          </div>
          <textarea v-model="wellbeingArticleForm.description" class="field min-h-[120px]" placeholder="Description ou usage" />
          <div class="glass-card space-y-4 p-4">
            <div class="flex items-center justify-between gap-3">
              <div>
                <p class="font-medium aurora-title">Vendeurs disponibles</p>
                <p class="text-xs aurora-subtle">Selectionnez les vendeurs autorises pour cet article.</p>
              </div>
              <span class="glass-chip">{{ wellbeingArticleForm.vendor_ids.length }} selectionne(s)</span>
            </div>
            <div class="grid gap-3 sm:grid-cols-2">
              <label
                v-for="vendor in vendors"
                :key="`wellbeing-article-vendor-${vendor.id}`"
                class="flex items-start gap-3 rounded-2xl border border-white/10 bg-white/5 p-3"
              >
                <input
                  :checked="wellbeingArticleForm.vendor_ids.includes(vendor.id)"
                  class="mt-1 h-4 w-4 rounded accent-emerald-400"
                  type="checkbox"
                  @change="toggleWellbeingArticleVendor(vendor.id, ($event.target as HTMLInputElement).checked)"
                />
                <div class="min-w-0">
                  <p class="font-medium text-stone-100">{{ vendor.nom }}</p>
                  <p class="text-xs aurora-subtle">{{ vendor.city_nom }}</p>
                </div>
              </label>
            </div>
          </div>
          <div class="flex flex-wrap gap-3">
            <button class="btn-primary" type="submit">{{ wellbeingArticleEditId ? "Mettre a jour" : "Enregistrer" }}</button>
            <button class="btn-secondary" type="button" @click="closeWellbeingArticleModal">Annuler</button>
          </div>
        </form>
      </div>
    </div>

    <div v-if="showExerciseModal" class="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
      <div class="panel max-h-[90vh] w-full max-w-3xl overflow-y-auto p-4 sm:p-8">
        <div class="flex items-start justify-between gap-4">
          <div>
            <h2 class="text-2xl font-semibold">{{ exerciseModalMode === 'edit' ? 'Modifier un exercice' : exerciseModalMode === 'detail' ? 'Details exercice' : 'Ajouter un exercice' }}</h2>
            <p class="mt-2 text-sm aurora-subtle">Gestion detaillee de la bibliotheque exercice.</p>
          </div>
          <button class="btn-secondary" type="button" @click="closeExerciseModal">Fermer</button>
        </div>

        <div v-if="exerciseModalMode === 'detail' && selectedExercise" class="mt-6 space-y-4">
          <div class="glass-card p-5">
            <p class="text-3xl">{{ inferExerciseIcon(selectedExercise) }}</p>
            <h3 class="mt-3 text-xl font-semibold">{{ selectedExercise.nom }}</h3>
            <p class="mt-2 text-sm aurora-subtle">{{ formatExerciseGroupLabel(selectedExercise.groupe_musculaire) }}</p>
            <p class="text-sm aurora-muted">{{ selectedExercise.niveau }}</p>
            <p v-if="selectedExercise.benefit_summary" class="mt-4 text-sm aurora-subtle">{{ selectedExercise.benefit_summary }}</p>
            <div v-if="selectedExercise.quality_tags" class="mt-3 flex flex-wrap gap-2">
              <span
                v-for="tag in selectedExercise.quality_tags.split(',').map((item) => item.trim()).filter(Boolean)"
                :key="`exercise-tag-${selectedExercise.id}-${tag}`"
                class="rounded-full border border-white/10 bg-white/5 px-2.5 py-1 text-[11px] aurora-subtle"
              >
                {{ tag }}
              </span>
            </div>
            <p class="mt-4 text-sm aurora-muted">{{ selectedExercise.preparation || "Aucune preparation" }}</p>
            <p v-if="selectedExercise.description" class="mt-2 text-sm aurora-subtle">{{ selectedExercise.description }}</p>
          </div>
        </div>

        <form v-else class="mt-6 space-y-4" @submit.prevent="saveExercise">
          <div class="grid gap-4 md:grid-cols-2">
            <input v-model="exerciseForm.nom" class="field" type="text" placeholder="Nom" />
            <input v-model="exerciseForm.icone" class="field" type="text" maxlength="16" placeholder="Icone ex: 🏋️" />
            <select
              v-model="exerciseForm.groupe_musculaire"
              :disabled="isCreateExerciseGroupLocked"
              class="field disabled:cursor-not-allowed disabled:opacity-70"
            >
              <option value="epaules">Epaules</option>
              <option value="bras">Bras</option>
              <option value="dos">Dos</option>
              <option value="jambes">Jambes</option>
              <option value="abdominaux">Abdominaux</option>
              <option value="pectoraux">Pectoraux</option>
              <option value="cardio">Cardio</option>
              <option value="full_body">Full body</option>
            </select>
            <select v-model="exerciseForm.niveau" class="field">
              <option value="debutant">Debutant</option>
              <option value="intermediaire">Intermediaire</option>
              <option value="avance">Avance</option>
            </select>
            <input v-model="exerciseForm.image_url" class="field md:col-span-2" type="url" placeholder="URL image" />
          </div>
          <div class="glass-card space-y-3 p-4">
            <p class="text-sm aurora-subtle">Ou ajouter une photo depuis l'appareil</p>
            <input class="field" type="file" accept="image/*" capture="environment" @change="updateImageSelection('exercise', $event)" />
            <img v-if="exerciseImagePreview" :src="exerciseImagePreview" alt="Apercu exercice" class="h-40 w-full rounded-2xl object-cover" />
          </div>
          <div class="flex flex-wrap gap-3">
            <button class="btn-secondary" type="button" @click="prefillExerciseAnalysis">
              Pre-remplir l'analyse
            </button>
          </div>
          <input v-model="exerciseForm.benefit_summary" class="field" type="text" placeholder="Benefice principal ex: stabilite du tronc et posture" />
          <input v-model="exerciseForm.quality_tags" class="field" type="text" placeholder="Tags separes par des virgules ex: force,hypertrophie,posture" />
          <textarea v-model="exerciseForm.preparation" class="field min-h-[100px]" placeholder="Preparation" />
          <textarea v-model="exerciseForm.description" class="field min-h-[100px]" placeholder="Consigne ou description" />
          <div class="flex flex-wrap gap-3">
            <button class="btn-primary" type="submit">{{ exerciseEditId ? "Mettre a jour" : "Enregistrer" }}</button>
            <button class="btn-secondary" type="button" @click="closeExerciseModal">Annuler</button>
          </div>
        </form>
      </div>
    </div>

    <div v-if="showRecipeModal" class="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
      <div class="panel max-h-[90vh] w-full max-w-4xl overflow-y-auto p-4 sm:p-8">
        <div class="flex items-start justify-between gap-4">
          <div>
            <h2 class="text-2xl font-semibold">{{ recipeModalMode === 'edit' ? 'Modifier une recette' : recipeModalMode === 'detail' ? 'Details recette' : 'Ajouter une recette' }}</h2>
            <p class="mt-2 text-sm aurora-subtle">Gestion detaillee de la bibliotheque recettes.</p>
          </div>
          <button class="btn-secondary" type="button" @click="closeRecipeModal">Fermer</button>
        </div>

        <div v-if="recipeModalMode === 'detail' && selectedRecipe" class="mt-6 space-y-4">
          <img v-if="resolveImageSrc(selectedRecipe)" :src="resolveImageSrc(selectedRecipe)" :alt="selectedRecipe.nom" class="h-52 w-full rounded-2xl object-cover" />
          <div class="glass-card p-5">
            <h3 class="text-xl font-semibold">{{ recipeIcon(selectedRecipe) }} {{ selectedRecipe.nom }}</h3>
            <p class="mt-2 text-sm aurora-subtle">{{ formatRecipeCategoryLabel(selectedRecipe.categorie_repas) }}</p>
            <p class="text-sm aurora-muted">{{ formatRecipeObjectiveLabel(selectedRecipe.objectif_adapte) }}</p>
            <div class="mt-4 grid gap-2 text-sm aurora-muted sm:grid-cols-2">
              <p><span class="aurora-subtle">Calories:</span> {{ formatCurrency(getRecipeMetrics(selectedRecipe).calories) }} kcal</p>
              <p><span class="aurora-subtle">Proteines:</span> {{ formatCurrency(getRecipeMetrics(selectedRecipe).proteines) }} g</p>
              <p><span class="aurora-subtle">Glucides:</span> {{ formatCurrency(getRecipeMetrics(selectedRecipe).glucides) }} g</p>
              <p><span class="aurora-subtle">Lipides:</span> {{ formatCurrency(getRecipeMetrics(selectedRecipe).lipides) }} g</p>
              <p class="sm:col-span-2">
                <span class="aurora-subtle">Cout minimum estime:</span>
                {{ getRecipeMetrics(selectedRecipe).hasPrice ? `${formatCurrency(getRecipeMetrics(selectedRecipe).cout)}` : "Indisponible" }}
              </p>
            </div>
            <p v-if="selectedRecipe.preparation" class="mt-4 whitespace-pre-line text-sm aurora-subtle">{{ selectedRecipe.preparation }}</p>
            <div class="mt-4 space-y-2 text-sm aurora-muted">
              <p v-for="ingredient in selectedRecipe.recipe_ingredients" :key="`detail-recipe-${selectedRecipe.id}-${ingredient.ingredient}-${ingredient.unite}`">
                {{ ingredient.ingredient_nom }} - {{ ingredient.quantite }} {{ ingredient.unite }}
              </p>
            </div>
          </div>
        </div>

        <form v-else class="mt-6 space-y-4" @submit.prevent="saveRecipe">
          <div class="grid gap-4 md:grid-cols-2">
            <input v-model="recipeForm.nom" class="field" type="text" placeholder="Nom" />
            <input v-model="recipeForm.icone" class="field" type="text" maxlength="16" placeholder="Icone" />
          </div>
          <div class="grid gap-4 md:grid-cols-2">
            <input v-model="recipeForm.image_url" class="field" type="url" placeholder="URL image" />
          </div>
          <div class="glass-card space-y-3 p-4">
            <p class="text-sm aurora-subtle">Ou ajouter une photo depuis l'appareil</p>
            <input class="field" type="file" accept="image/*" capture="environment" @change="updateImageSelection('recipe', $event)" />
            <img v-if="recipeImagePreview" :src="recipeImagePreview" alt="Apercu recette" class="h-40 w-full rounded-2xl object-cover" />
          </div>
          <div class="grid gap-4 md:grid-cols-2">
            <select v-model="recipeForm.categorie_repas" class="field">
              <option value="petit_dejeuner">Petit dejeuner</option>
              <option value="dejeuner">Dejeuner</option>
              <option value="diner">Diner</option>
              <option value="collation">Collation</option>
            </select>
            <select v-model="recipeForm.objectif_adapte" class="field">
              <option value="">Sans objectif</option>
              <option value="perte_poids">Perte de poids</option>
              <option value="prise_masse">Prise de masse</option>
              <option value="sechage">Sechage</option>
              <option value="alimentation_saine">Alimentation saine</option>
            </select>
          </div>
          <label class="inline-flex items-center gap-3 text-sm text-stone-300">
            <input v-model="recipeForm.actif" type="checkbox" class="h-4 w-4 accent-emerald-400" />
            <span>Recette active</span>
          </label>
          <textarea v-model="recipeForm.preparation" class="field min-h-[120px]" placeholder="Preparation" />
          <div class="space-y-3">
            <div class="flex items-center justify-between gap-4">
              <p class="text-sm aurora-subtle">Ingredients de la recette</p>
              <button class="btn-secondary" type="button" @click="addRecipeIngredientRow">Ajouter ingredient</button>
            </div>
            <div v-for="(item, index) in recipeForm.recipe_ingredients" :key="index" class="grid gap-3 md:grid-cols-[1.4fr_0.8fr_0.8fr_auto]">
              <select v-model.number="item.ingredient" class="field">
                <option :value="0">Choisir un ingredient</option>
                <option v-for="ingredient in ingredients" :key="ingredient.id" :value="ingredient.id">{{ ingredient.nom }}</option>
              </select>
              <input v-model="item.quantite" class="field" inputmode="decimal" type="text" placeholder="Quantite" />
              <input v-model="item.unite" class="field" type="text" placeholder="Unite" />
              <button class="btn-secondary" type="button" @click="removeRecipeIngredientRow(index)">Retirer</button>
            </div>
          </div>
          <div class="flex flex-wrap gap-3">
            <button class="btn-primary" type="submit">{{ recipeEditId ? "Mettre a jour" : "Enregistrer" }}</button>
            <button class="btn-secondary" type="button" @click="closeRecipeModal">Annuler</button>
          </div>
        </form>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
const adminAssetsVersion = "2026-06-23-upload-images-1"
const props = withDefaults(defineProps<{
  forcedSection?: "users" | "catalog" | "coach" | "recipes" | "ingredients" | "exercises"
}>(), {
  forcedSection: undefined,
})

type AdminUser = {
  id: number
  username: string
  email: string
  is_staff: boolean
  is_superuser: boolean
  is_active: boolean
}

type CoachAdherence = {
  user_id: number
  username: string
  summary: null | {
    total_items: number
    completed_items: number
    remaining_items: number
    adherence_rate: number
  }
  insights?: {
    weight_delta: number | null
    meal_adherence_rate: number
    workout_adherence_rate: number
    weight_message: string
    meal_message: string
    sport_message: string
    appreciation: string[]
  }
  items: Array<{
    id: number
    exercise_nom: string
    date_prevue: string | null
    jour_semaine: string
    semaine_index: number
    completed: boolean
  }>
}

type Ingredient = {
  id: number
  nom: string
  icone: string
  categorie: string
  is_perishable?: boolean
  max_storage_days?: number | null
  image?: string | null
  image_url: string
  image_file_url?: string | null
  image_focus_x?: number | string | null
  image_focus_y?: number | string | null
  image_zoom?: number | string | null
  preparation: string
  unite_base: string
  calories_100g: string | number
  proteines_100g: string | number
  glucides_100g: string | number
  lipides_100g: string | number
  micronutrient_tags?: string[]
  micronutrient_tag_labels?: string[]
  benefit_tags?: string[]
  benefit_tag_labels?: string[]
  drawback_tags?: string[]
  drawback_tag_labels?: string[]
}

type Recipe = {
  id: number
  nom: string
  icone?: string
  image?: string | null
  image_url: string
  image_file_url?: string | null
  preparation: string
  categorie_repas: string
  actif?: boolean
  objectif_adapte: string
  recipe_ingredients: Array<{
    ingredient: number
    ingredient_nom: string
    quantite: string
    unite: string
  }>
}

type Exercise = {
  id: number
  nom: string
  icone?: string
  groupe_musculaire: string
  niveau: string
  image?: string | null
  image_url: string
  image_file_url?: string | null
  preparation: string
  description: string
  benefit_summary: string
  quality_tags: string
}

type City = {
  id: number
  nom: string
}

type Vendor = {
  id: number
  nom: string
  city: number
  city_nom: string
  description: string
}

type IngredientPrice = {
  id: number
  ingredient: number
  ingredient_nom: string
  vendor: number
  vendor_nom: string
  city_id: number
  city_nom: string
  prix: string | number | null
  date_dernier_prix: string
  created_at: string
  updated_at: string
}

type WellbeingArticle = {
  id: number
  nom: string
  icone: string
  categorie: string
  unite_base: string
  description: string
  vendor_ids: number[]
}

type WellbeingArticlePrice = {
  id: number
  article: number
  article_nom: string
  vendor: number
  vendor_nom: string
  city_id: number
  city_nom: string
  prix: string | number | null
  date_dernier_prix: string
  created_at: string
  updated_at: string
}

type CatalogTab = "cities" | "vendors" | "ingredient-prices" | "wellbeing-articles" | "wellbeing-article-prices"

const route = useRoute()
const auth = useAuth()
const { request } = useApi()
const sections = [
  { key: "users", label: "Utilisateurs", icon: "👤" },
  { key: "catalog", label: "Approvisionnement", icon: "🛍️" },
  { key: "coach", label: "Coach", icon: "🧑‍🏫" },
  { key: "recipes", label: "Recettes", icon: "🥗" },
  { key: "ingredients", label: "Ingredients", icon: "🥒" },
  { key: "exercises", label: "Exercices", icon: "🏋️" },
]
const catalogSections = new Set<CatalogTab>(["cities", "vendors", "ingredient-prices", "wellbeing-articles", "wellbeing-article-prices"])
const routeSection = computed(() => props.forcedSection || (typeof route.query.section === "string" ? route.query.section : "users"))
const routeCatalogTab = computed(() => (
  typeof route.query.tab === "string"
    ? route.query.tab
    : (typeof route.query.section === "string" && catalogSections.has(route.query.section as CatalogTab)
        ? route.query.section
        : "cities")
))
const activeSection = ref(catalogSections.has(routeSection.value as CatalogTab) ? "catalog" : routeSection.value)
const catalogTab = ref<CatalogTab>(catalogSections.has(routeCatalogTab.value as CatalogTab) ? (routeCatalogTab.value as CatalogTab) : "cities")
const feedback = ref("")
const today = new Date().toISOString().slice(0, 10)

const cityForm = reactive({
  nom: "",
})
const cityEditId = ref<number | null>(null)
const vendorForm = reactive({
  nom: "",
  city: 0,
  description: "",
})
const vendorEditId = ref<number | null>(null)
const wellbeingArticleForm = reactive({
  nom: "",
  icone: "",
  categorie: "",
  unite_base: "piece",
  description: "",
  vendor_ids: [] as number[],
})
const wellbeingArticleViewMode = ref<"cards" | "table">("cards")
const selectedWellbeingArticleCategory = ref<string | null>(null)
const showWellbeingArticleModal = ref(false)
const wellbeingArticleModalMode = ref<"create" | "edit" | "detail">("create")
const wellbeingArticleEditId = ref<number | null>(null)
const selectedWellbeingArticle = ref<WellbeingArticle | null>(null)
const ingredientPriceDrafts = reactive<Record<number, {
  ingredient: number
  vendor: number
  prix: string
  date_dernier_prix: string
  editId: number | null
}>>({})
const wellbeingArticlePriceDrafts = reactive<Record<number, {
  article: number
  vendor: number
  prix: string
  date_dernier_prix: string
  editId: number | null
}>>({})
const catalogCityFilter = ref(0)
const selectedPriceCategory = ref<string | null>(null)
const ingredientForm = reactive({
  nom: "",
  icone: "",
  categorie: "",
  is_perishable: false,
  max_storage_days: "",
  image_url: "",
  image_focus_x: 50,
  image_focus_y: 50,
  image_zoom: 1,
  preparation: "",
  unite_base: "g",
  calories_100g: "",
  proteines_100g: "",
  glucides_100g: "",
  lipides_100g: "",
  micronutrient_tags: [] as string[],
  benefit_tags: [] as string[],
  drawback_tags: [] as string[],
})
const ingredientMicronutrientOptions = [
  { value: "calcium", label: "Calcium" },
  { value: "iron", label: "Fer" },
  { value: "magnesium", label: "Magnesium" },
  { value: "potassium", label: "Potassium" },
  { value: "zinc", label: "Zinc" },
  { value: "vitamin_a", label: "Vitamine A" },
  { value: "vitamin_b", label: "Vitamine B" },
  { value: "vitamin_b9", label: "Vitamine B9" },
  { value: "vitamin_b12", label: "Vitamine B12" },
  { value: "vitamin_c", label: "Vitamine C" },
  { value: "vitamin_d", label: "Vitamine D" },
  { value: "vitamin_e", label: "Vitamine E" },
  { value: "fiber", label: "Fibres" },
  { value: "omega_3", label: "Omega 3" },
  { value: "antioxidants", label: "Antioxydants" },
]
const ingredientBenefitOptions = [
  { value: "satiety", label: "Satiété" },
  { value: "muscle_support", label: "Soutien musculaire" },
  { value: "digestion", label: "Digestion" },
  { value: "energy", label: "Energie" },
  { value: "immunity", label: "Immunité" },
  { value: "bone_health", label: "Santé osseuse" },
  { value: "heart_health", label: "Santé cardiovasculaire" },
  { value: "brain_health", label: "Soutien cérébral" },
  { value: "hydration", label: "Hydratation" },
  { value: "antioxidant_support", label: "Protection antioxydante" },
  { value: "blood_sugar_stability", label: "Stabilité glycémique" },
]
const ingredientDrawbackOptions = [
  { value: "high_calorie", label: "Densité calorique élevée" },
  { value: "high_sugar", label: "Teneur élevée en sucre" },
  { value: "high_fat", label: "Teneur élevée en lipides" },
  { value: "high_saturated_fat", label: "Richesse en graisses saturées" },
  { value: "high_salt", label: "Teneur élevée en sel" },
  { value: "digestive_sensitivity", label: "Sensibilité digestive possible" },
  { value: "lactose_sensitivity", label: "Sensibilité au lactose" },
  { value: "portion_control", label: "Portions à surveiller" },
]
const ingredientViewMode = ref<"cards" | "table">("cards")
const selectedIngredientCategory = ref<string | null>(null)
const collapsedIngredientCategories = ref<Record<string, boolean>>({})
const showIngredientModal = ref(false)
const ingredientModalMode = ref<"create" | "edit" | "detail">("create")
const ingredientEditId = ref<number | null>(null)
const selectedIngredient = ref<Ingredient | null>(null)
const ingredientImageFile = ref<File | null>(null)
const ingredientImagePreview = ref("")
const ingredientImageDragActive = ref(false)
const recipeForm = reactive({
  nom: "",
  icone: "",
  image_url: "",
  preparation: "",
  categorie_repas: "dejeuner",
  objectif_adapte: "",
  actif: true,
  recipe_ingredients: [
    { ingredient: 0, quantite: "", unite: "g" },
  ],
})
const recipeImageFile = ref<File | null>(null)
const recipeImagePreview = ref("")
const recipeViewMode = ref<"cards" | "table">("cards")
const selectedRecipeCategory = ref<string | null>(null)
const showRecipeModal = ref(false)
const recipeModalMode = ref<"create" | "edit" | "detail">("create")
const recipeEditId = ref<number | null>(null)
const selectedRecipe = ref<Recipe | null>(null)
const exerciseForm = reactive({
  nom: "",
  icone: "",
  groupe_musculaire: "full_body",
  niveau: "debutant",
  image_url: "",
  preparation: "",
  description: "",
  benefit_summary: "",
  quality_tags: "",
})
const exerciseViewMode = ref<"cards" | "table">("cards")
const selectedExerciseGroupKey = ref<string | null>(null)
const showOnlyIncompleteExercises = ref(false)
const showExerciseModal = ref(false)
const exerciseModalMode = ref<"create" | "edit" | "detail">("create")
const exerciseEditId = ref<number | null>(null)
const selectedExercise = ref<Exercise | null>(null)
const exerciseImageFile = ref<File | null>(null)
const exerciseImagePreview = ref("")
const coachForm = reactive({
  user_id: 0,
  date_debut: today,
  frequence_semaine: 3,
  duree_semaines: 4,
})
const userForm = reactive({
  username: "",
  email: "",
  password: "",
  is_staff: false,
  is_superuser: false,
  is_active: true,
})
const adherenceData = ref<CoachAdherence | null>(null)

await auth.ensureLoaded()

const asyncDataOptions = {
  server: false,
  default: () => [],
}

const { data: usersData, refresh: refreshUsers } = await useAsyncData("admin-users", async () => {
  if (!auth.user.value?.is_staff && !auth.user.value?.is_superuser) {
    return []
  }
  const response = await request<{ results?: AdminUser[] } | AdminUser[]>("/auth/admin/users/", { method: "GET" })
  return unwrapApiList(response)
}, asyncDataOptions)
const ingredientsData = ref<Ingredient[]>([])
const citiesData = ref<City[]>([])
const vendorsData = ref<Vendor[]>([])
const wellbeingArticlesData = ref<WellbeingArticle[]>([])
const wellbeingArticlePricesData = ref<WellbeingArticlePrice[]>([])
const ingredientPricesData = ref<IngredientPrice[]>([])
const recipesData = ref<Recipe[]>([])
const exercisesData = ref<Exercise[]>([])

const users = computed(() => usersData.value || [])
const ingredients = computed(() => ingredientsData.value || [])
const wellbeingArticles = computed(() => wellbeingArticlesData.value || [])
const groupedWellbeingArticlesForAdmin = computed(() => {
  const groups = new Map<string, WellbeingArticle[]>()
  for (const article of wellbeingArticles.value) {
    const category = (article.categorie || "Sans categorie").trim() || "Sans categorie"
    if (!groups.has(category)) {
      groups.set(category, [])
    }
    groups.get(category)?.push(article)
  }
  return Array.from(groups.entries())
    .sort((a, b) => safeLocaleCompare(a[0], b[0]))
    .map(([category, items]) => ({
      category,
      items: [...items].sort((a, b) => safeLocaleCompare(a.nom, b.nom)),
    }))
})
const selectedWellbeingArticleGroup = computed(() => {
  if (!selectedWellbeingArticleCategory.value) {
    return null
  }
  return groupedWellbeingArticlesForAdmin.value.find((group) => group.category === selectedWellbeingArticleCategory.value) || null
})
const groupedIngredients = computed(() => {
  const groups = new Map<string, Ingredient[]>()
  for (const ingredient of ingredients.value) {
    const category = (ingredient.categorie || "Sans categorie").trim() || "Sans categorie"
    if (!groups.has(category)) {
      groups.set(category, [])
    }
    groups.get(category)?.push(ingredient)
  }
  return Array.from(groups.entries())
    .sort((a, b) => safeLocaleCompare(a[0], b[0]))
    .map(([category, items]) => ({
      category,
      items: [...items].sort((a, b) => safeLocaleCompare(a.nom, b.nom)),
    }))
})

const selectedIngredientGroup = computed(() => {
  if (!selectedIngredientCategory.value) {
    return null
  }
  return groupedIngredients.value.find((group) => group.category === selectedIngredientCategory.value) || null
})
const ingredientCreateButtonLabel = computed(() => {
  const rawCategory = selectedIngredientCategory.value?.trim()
  if (!rawCategory || rawCategory.toLowerCase() === "sans categorie") {
    return "Ajouter un ingredient"
  }

  const normalizedCategory = rawCategory.toLowerCase()
  const singularMap: Record<string, string> = {
    feculents: "un feculent",
    legumes: "un legume",
    fruits: "un fruit",
    condiments: "un condiment",
    oleagineux: "un oleagineux",
    proteines: "une proteine",
    epices: "une epice",
    boissons: "une boisson",
    legume: "un legume",
    fruit: "un fruit",
    feculent: "un feculent",
    condiment: "un condiment",
    oleagineux: "un oleagineux",
    proteine: "une proteine",
    epice: "une epice",
    boisson: "une boisson",
  }
  if (singularMap[normalizedCategory]) {
    return `Ajouter ${singularMap[normalizedCategory]}`
  }

  if (normalizedCategory.endsWith("s")) {
    return `Ajouter un ${rawCategory.slice(0, -1)}`
  }

  return `Ajouter un ${rawCategory}`
})
const selectedPriceIngredientGroup = computed(() => {
  if (!selectedPriceCategory.value) {
    return null
  }
  return groupedIngredients.value.find((group) => group.category === selectedPriceCategory.value) || null
})

const isCreateIngredientCategoryLocked = computed(() => (
  ingredientModalMode.value === "create" && Boolean(selectedIngredientCategory.value)
))

watch(routeSection, (value) => {
  activeSection.value = catalogSections.has(value as CatalogTab) ? "catalog" : value
}, { immediate: true })

watch(routeCatalogTab, (value) => {
  if (catalogSections.has(value as CatalogTab)) {
    catalogTab.value = value as CatalogTab
  }
}, { immediate: true })

watch(groupedIngredients, (groups) => {
  const nextState: Record<string, boolean> = {}
  for (const group of groups) {
    nextState[group.category] = collapsedIngredientCategories.value[group.category] ?? false
  }
  collapsedIngredientCategories.value = nextState
  if (selectedIngredientCategory.value && !groups.some((group) => group.category === selectedIngredientCategory.value)) {
    selectedIngredientCategory.value = null
  }
  if (selectedPriceCategory.value && !groups.some((group) => group.category === selectedPriceCategory.value)) {
    selectedPriceCategory.value = null
  }
}, { immediate: true })

watch(groupedWellbeingArticlesForAdmin, (groups) => {
  if (selectedWellbeingArticleCategory.value && !groups.some((group) => group.category === selectedWellbeingArticleCategory.value)) {
    selectedWellbeingArticleCategory.value = null
  }
}, { immediate: true })

const cities = computed(() => citiesData.value || [])
const vendors = computed(() => vendorsData.value || [])
const ingredientPrices = computed(() => ingredientPricesData.value || [])
const wellbeingArticlePrices = computed(() => wellbeingArticlePricesData.value || [])
const recipes = computed(() => recipesData.value || [])
const exercises = computed(() => exercisesData.value || [])
function isExerciseAnalysisIncomplete(exercise: Exercise) {
  return !exercise.benefit_summary?.trim() || !exercise.quality_tags?.trim()
}
const visibleExercises = computed(() => (
  showOnlyIncompleteExercises.value
    ? exercises.value.filter((exercise) => isExerciseAnalysisIncomplete(exercise))
    : exercises.value
))
const groupedExercises = computed(() => {
  const groups = new Map<string, Exercise[]>()
  for (const exercise of visibleExercises.value) {
    const group = formatExerciseGroupLabel(exercise.groupe_musculaire)
    if (!groups.has(group)) {
      groups.set(group, [])
    }
    groups.get(group)?.push(exercise)
  }
  return Array.from(groups.entries())
    .sort((a, b) => safeLocaleCompare(a[0], b[0]))
    .map(([group, items]) => ({
      group,
      items: [...items].sort((a, b) => safeLocaleCompare(a.nom, b.nom)),
    }))
})
const selectedExerciseGroup = computed(() => {
  if (!selectedExerciseGroupKey.value) {
    return null
  }
  return groupedExercises.value.find((group) => group.group === selectedExerciseGroupKey.value) || null
})
const selectedExerciseGroupValue = computed(() => {
  if (!selectedExerciseGroupKey.value) {
    return ""
  }
  const normalized = selectedExerciseGroupKey.value.trim().toLowerCase()
  const groupEntry = Object.entries({
    epaules: "Epaules",
    bras: "Bras",
    dos: "Dos",
    jambes: "Jambes",
    abdominaux: "Abdominaux",
    pectoraux: "Pectoraux",
    cardio: "Cardio",
    full_body: "Full body",
  }).find(([, label]) => label.toLowerCase() === normalized)
  return groupEntry?.[0] || ""
})
const isCreateExerciseGroupLocked = computed(() => (
  exerciseModalMode.value === "create" && Boolean(selectedExerciseGroupValue.value)
))

watch(groupedExercises, (groups) => {
  if (selectedExerciseGroupKey.value && !groups.some((group) => group.group === selectedExerciseGroupKey.value)) {
    selectedExerciseGroupKey.value = null
  }
}, { immediate: true })

const filteredVendors = computed(() => {
  if (!catalogCityFilter.value) {
    return vendors.value
  }
  return vendors.value.filter((vendor) => vendor.city === catalogCityFilter.value)
})
const priceVendorOptions = computed(() => {
  if (!catalogCityFilter.value) {
    return vendors.value
  }
  return vendors.value.filter((vendor) => vendor.city === catalogCityFilter.value)
})
const filteredIngredientPrices = computed(() => {
  if (!catalogCityFilter.value) {
    return ingredientPrices.value
  }
  return ingredientPrices.value.filter((price) => price.city_id === catalogCityFilter.value)
})
const groupedRecipes = computed(() => {
  const groups = new Map<string, Recipe[]>()
  for (const recipe of recipes.value) {
    const category = formatRecipeCategoryLabel(recipe.categorie_repas)
    if (!groups.has(category)) {
      groups.set(category, [])
    }
    groups.get(category)?.push(recipe)
  }
  return Array.from(groups.entries())
    .sort((a, b) => safeLocaleCompare(a[0], b[0]))
    .map(([category, items]) => ({
      category,
      items: [...items].sort((a, b) => safeLocaleCompare(a.nom, b.nom)),
    }))
})
const selectedRecipeGroup = computed(() => {
  if (!selectedRecipeCategory.value) {
    return null
  }
  return groupedRecipes.value.find((group) => group.category === selectedRecipeCategory.value) || null
})

watch(groupedRecipes, (groups) => {
  if (selectedRecipeCategory.value && !groups.some((group) => group.category === selectedRecipeCategory.value)) {
    selectedRecipeCategory.value = null
  }
}, { immediate: true })

function toNumber(value: string | number | null | undefined) {
  if (typeof value === "number") {
    return Number.isFinite(value) ? value : 0
  }
  const parsed = Number(String(value || 0).replace(",", "."))
  return Number.isFinite(parsed) ? parsed : 0
}

function safeLocaleCompare(left: string | null | undefined, right: string | null | undefined) {
  return String(left || "").localeCompare(String(right || ""), "fr")
}

function formatNutrientValue(value: number, unit: string) {
  return `${new Intl.NumberFormat("fr-FR", {
    minimumFractionDigits: 0,
    maximumFractionDigits: 1,
  }).format(value)} ${unit} / 100g`
}

function getMaxIngredientByMetric(items: Ingredient[], metric: keyof Pick<Ingredient, "calories_100g" | "proteines_100g" | "glucides_100g" | "lipides_100g">) {
  if (!items.length) {
    return null
  }
  return items.reduce((best, current) => {
    return toNumber(current[metric]) > toNumber(best[metric]) ? current : best
  })
}

function getMinIngredientByMetric(items: Ingredient[], metric: keyof Pick<Ingredient, "calories_100g" | "proteines_100g" | "glucides_100g" | "lipides_100g">) {
  if (!items.length) {
    return null
  }
  return items.reduce((best, current) => {
    return toNumber(current[metric]) < toNumber(best[metric]) ? current : best
  })
}

function getIngredientCategoryHighlights(items: Ingredient[]) {
  const highestCalories = getMaxIngredientByMetric(items, "calories_100g")
  const highestProteins = getMaxIngredientByMetric(items, "proteines_100g")
  const highestCarbs = getMaxIngredientByMetric(items, "glucides_100g")
  const lowestCalories = getMinIngredientByMetric(items, "calories_100g")

  return [
    highestCalories && {
      key: "highest-calories",
      icon: "🔥",
      label: "Plus calorique",
      name: highestCalories.nom,
      value: formatNutrientValue(toNumber(highestCalories.calories_100g), "kcal"),
      tone: "border-red-400/30 bg-red-300/10 text-red-100",
    },
    highestProteins && {
      key: "highest-proteins",
      icon: "💪",
      label: "Plus proteine",
      name: highestProteins.nom,
      value: formatNutrientValue(toNumber(highestProteins.proteines_100g), "g"),
      tone: "border-emerald-400/30 bg-emerald-300/10 text-emerald-100",
    },
    highestCarbs && {
      key: "highest-carbs",
      icon: "⚡",
      label: "Plus glucidique",
      name: highestCarbs.nom,
      value: formatNutrientValue(toNumber(highestCarbs.glucides_100g), "g"),
      tone: "border-orange-400/40 bg-orange-300/15 text-orange-100",
    },
    lowestCalories && {
      key: "lowest-calories",
      icon: "🌿",
      label: "Plus leger",
      name: lowestCalories.nom,
      value: formatNutrientValue(toNumber(lowestCalories.calories_100g), "kcal"),
      tone: "border-emerald-400/30 bg-emerald-300/10 text-emerald-100",
    },
  ].filter(Boolean) as Array<{ key: string; icon: string; label: string; name: string; value: string; tone: string }>
}

function getIngredientComparisonBadges(
  ingredient: Ingredient,
  items: Ingredient[],
) {
  const badges: Array<{ icon: string; label: string }> = []
  const highestCalories = getMaxIngredientByMetric(items, "calories_100g")
  const highestProteins = getMaxIngredientByMetric(items, "proteines_100g")
  const highestCarbs = getMaxIngredientByMetric(items, "glucides_100g")
  const highestLipids = getMaxIngredientByMetric(items, "lipides_100g")
  const lowestCalories = getMinIngredientByMetric(items, "calories_100g")

  if (highestCalories?.id === ingredient.id) {
    badges.push({ icon: "🔥", label: "Très calorique", tone: "border-red-400/30 bg-red-300/10 text-red-100" })
  }
  if (highestProteins?.id === ingredient.id) {
    badges.push({ icon: "💪", label: "Top proteines", tone: "border-emerald-400/30 bg-emerald-300/10 text-emerald-100" })
  }
  if (highestCarbs?.id === ingredient.id) {
    badges.push({ icon: "⚡", label: "Top glucides", tone: "border-orange-400/40 bg-orange-300/15 text-orange-100" })
  }
  if (highestLipids?.id === ingredient.id) {
    badges.push({ icon: "🥑", label: "Top lipides", tone: "border-fuchsia-400/30 bg-fuchsia-300/10 text-fuchsia-100" })
  }
  if (lowestCalories?.id === ingredient.id) {
    badges.push({ icon: "🌿", label: "Le plus leger", tone: "border-emerald-400/30 bg-emerald-300/10 text-emerald-100" })
  }

  return badges
}

function getIngredientMetricValueClass(
  ingredient: Ingredient,
  items: Ingredient[],
  metric: keyof Pick<Ingredient, "calories_100g" | "proteines_100g" | "glucides_100g" | "lipides_100g">,
) {
  const highest = getMaxIngredientByMetric(items, metric)
  const lowestCalories = metric === "calories_100g" ? getMinIngredientByMetric(items, "calories_100g") : null

  if (highest?.id === ingredient.id) {
    if (metric === "calories_100g") {
      return "font-semibold text-red-300"
    }
    if (metric === "glucides_100g") {
      return "font-semibold text-orange-300"
    }
    return "font-semibold text-emerald-300"
  }

  if (lowestCalories?.id === ingredient.id) {
    return "font-semibold text-emerald-300"
  }

  return "text-stone-100"
}

function cleanDecimal(value: string) {
  const trimmed = value.trim()
  return trimmed ? trimmed.replace(",", ".") : 0
}

function cleanOptionalDecimal(value: string) {
  const trimmed = value.trim()
  return trimmed ? trimmed.replace(",", ".") : null
}

function formatCurrency(value: string | number | null | undefined) {
  if (value === null || value === undefined || value === "") {
    return "Prix a relever"
  }
  const amount = typeof value === "number" ? value : Number(value || 0)
  return new Intl.NumberFormat("fr-FR", {
    minimumFractionDigits: 0,
    maximumFractionDigits: 2,
  }).format(amount)
}

function getVendorName(vendorId: number) {
  return vendors.value.find((vendor) => vendor.id === vendorId)?.nom || `Vendeur #${vendorId}`
}

function getIngredientPriceUnitLabel(uniteBase: string | null | undefined) {
  const unit = String(uniteBase || "").trim().toLowerCase()
  if (!unit || unit === "g") {
    return "100 g"
  }
  if (unit === "ml") {
    return "100 ml"
  }
  if (unit === "kg") {
    return "1 kg"
  }
  if (unit === "l") {
    return "1 L"
  }
  if (unit === "piece" || unit === "pièce" || unit === "pcs") {
    return "piece"
  }
  return unit
}

function getIngredientPriceLabel(ingredient: Pick<Ingredient, "unite_base"> | null | undefined) {
  return `Prix pour ${getIngredientPriceUnitLabel(ingredient?.unite_base)}`
}

function formatRecipeCategoryLabel(category: string) {
  const labels: Record<string, string> = {
    petit_dejeuner: "Petit dejeuner",
    dejeuner: "Dejeuner",
    diner: "Diner",
    collation: "Collation",
  }
  return labels[category] || category || "Autres"
}

function formatRecipeObjectiveLabel(objective: string) {
  const labels: Record<string, string> = {
    perte_poids: "Perte de poids",
    prise_masse: "Prise de masse",
    sechage: "Sechage",
    alimentation_saine: "Alimentation saine",
  }
  return labels[objective] || (objective ? objective : "Objectif libre")
}

function recipeIcon(recipe: Pick<Recipe, "icone" | "categorie_repas"> | null | undefined) {
  const customIcon = String(recipe?.icone || "").trim()
  if (customIcon) {
    return customIcon
  }
  const defaults: Record<string, string> = {
    petit_dejeuner: "🍳",
    dejeuner: "🍽️",
    diner: "🥘",
    collation: "🍎",
  }
  return defaults[recipe?.categorie_repas || ""] || "🥗"
}

function getRecipeIngredientReference(ingredientId: number) {
  return ingredients.value.find((ingredient) => ingredient.id === ingredientId) || null
}

function convertRecipeQuantityToBaseUnit(
  quantity: string | number,
  quantityUnit: string | null | undefined,
  ingredient: Ingredient | null,
) {
  const amount = toNumber(quantity)
  if (!ingredient) {
    return amount
  }
  const itemUnit = String(quantityUnit || ingredient.unite_base || "").trim().toLowerCase()
  const baseUnit = String(ingredient.unite_base || "").trim().toLowerCase()

  if (itemUnit === baseUnit) {
    return amount
  }

  if (baseUnit === "g" && itemUnit === "kg") {
    return amount * 1000
  }
  if (baseUnit === "kg" && itemUnit === "g") {
    return amount / 1000
  }
  if (baseUnit === "ml" && itemUnit === "l") {
    return amount * 1000
  }
  if (baseUnit === "l" && itemUnit === "ml") {
    return amount / 1000
  }

  return amount
}

function getBestPriceForIngredient(ingredientId: number) {
  const prices = getPricesForIngredient(ingredientId)
  if (!prices.length) {
    return null
  }
  return prices.reduce((best, current) => (
    toNumber(current.prix) < toNumber(best.prix) ? current : best
  ))
}

function getRecipeMetrics(recipe: Recipe) {
  let calories = 0
  let proteines = 0
  let glucides = 0
  let lipides = 0
  let cout = 0
  let hasPrice = false

  for (const item of recipe.recipe_ingredients) {
    const ingredient = getRecipeIngredientReference(item.ingredient)
    if (!ingredient) {
      continue
    }
    const normalizedQty = convertRecipeQuantityToBaseUnit(item.quantite, item.unite, ingredient)
    const baseUnit = String(ingredient.unite_base || "").trim().toLowerCase()

    if (baseUnit === "g" || baseUnit === "ml") {
      const factor = normalizedQty / 100
      calories += factor * toNumber(ingredient.calories_100g)
      proteines += factor * toNumber(ingredient.proteines_100g)
      glucides += factor * toNumber(ingredient.glucides_100g)
      lipides += factor * toNumber(ingredient.lipides_100g)
    }

    const bestPrice = getBestPriceForIngredient(item.ingredient)
    if (!bestPrice) {
      continue
    }
    const priceValue = toNumber(bestPrice.prix)
    if (baseUnit === "g" || baseUnit === "ml") {
      cout += (normalizedQty / 100) * priceValue
      hasPrice = true
    } else if (baseUnit === "kg" || baseUnit === "l") {
      cout += normalizedQty * priceValue
      hasPrice = true
    } else if (baseUnit === "piece" || baseUnit === "pièce" || baseUnit === "pcs") {
      cout += normalizedQty * priceValue
      hasPrice = true
    }
  }

  return {
    calories,
    proteines,
    glucides,
    lipides,
    cout,
    hasPrice,
  }
}

function getRecipeMaxMetric(
  items: Recipe[],
  metric: "calories" | "proteines" | "glucides" | "lipides" | "cout",
) {
  if (!items.length) {
    return null
  }
  return items.reduce((best, current) => (
    getRecipeMetrics(current)[metric] > getRecipeMetrics(best)[metric] ? current : best
  ))
}

function getRecipeMinMetric(
  items: Recipe[],
  metric: "calories" | "proteines" | "glucides" | "lipides" | "cout",
) {
  if (!items.length) {
    return null
  }
  return items.reduce((best, current) => (
    getRecipeMetrics(current)[metric] < getRecipeMetrics(best)[metric] ? current : best
  ))
}

function getRecipeComparisonBadges(recipe: Recipe, items: Recipe[]) {
  const badges: Array<{ icon: string; label: string; tone: string }> = []
  const highestCalories = getRecipeMaxMetric(items, "calories")
  const highestProteins = getRecipeMaxMetric(items, "proteines")
  const highestCarbs = getRecipeMaxMetric(items, "glucides")
  const lowestCost = getRecipeMinMetric(items, "cout")

  if (highestCalories?.id === recipe.id) {
    badges.push({ icon: "🔥", label: "Très calorique", tone: "border-red-400/30 bg-red-300/10 text-red-100" })
  }
  if (highestProteins?.id === recipe.id) {
    badges.push({ icon: "💪", label: "Top proteines", tone: "border-emerald-400/30 bg-emerald-300/10 text-emerald-100" })
  }
  if (highestCarbs?.id === recipe.id) {
    badges.push({ icon: "⚡", label: "Top glucides", tone: "border-orange-400/40 bg-orange-300/15 text-orange-100" })
  }
  if (lowestCost?.id === recipe.id && getRecipeMetrics(recipe).hasPrice) {
    badges.push({ icon: "💸", label: "Plus economique", tone: "border-sky-400/30 bg-sky-300/10 text-sky-100" })
  }

  return badges
}

function getCityVendorCount(cityId: number) {
  return vendors.value.filter((vendor) => vendor.city === cityId).length
}

function formatExerciseGroupLabel(group: string) {
  const labels: Record<string, string> = {
    epaules: "Epaules",
    bras: "Bras",
    dos: "Dos",
    jambes: "Jambes",
    abdominaux: "Abdominaux",
    pectoraux: "Pectoraux",
    cardio: "Cardio",
    full_body: "Full body",
  }
  return labels[group] || group || "Autres"
}

function formatExerciseLevelLabel(level: string) {
  const labels: Record<string, string> = {
    debutant: "Debutant",
    intermediaire: "Intermediaire",
    avance: "Avance",
  }
  return labels[level] || level || "Non precise"
}

function inferExerciseGroupIcon(items: Exercise[]) {
  return items[0] ? inferExerciseIcon(items[0]) : "🏋️"
}

function summarizeExerciseLevels(items: Exercise[]) {
  const counts = {
    debutant: 0,
    intermediaire: 0,
    avance: 0,
  }
  for (const item of items) {
    if (item.niveau in counts) {
      counts[item.niveau as keyof typeof counts] += 1
    }
  }
  return [
    counts.debutant ? `${counts.debutant} debutant${counts.debutant > 1 ? "s" : ""}` : "",
    counts.intermediaire ? `${counts.intermediaire} intermediaire${counts.intermediaire > 1 ? "s" : ""}` : "",
    counts.avance ? `${counts.avance} avance${counts.avance > 1 ? "s" : ""}` : "",
  ].filter(Boolean).join(" · ")
}

function inferExerciseIcon(exercise: Pick<Exercise, "nom" | "groupe_musculaire" | "icone">) {
  if (exercise.icone) {
    return exercise.icone
  }
  const name = (exercise.nom || "").toLowerCase()
  if (name.includes("squat")) return "🦵"
  if (name.includes("fente")) return "🦵"
  if (name.includes("pompe")) return "💪"
  if (name.includes("traction")) return "🏋️"
  if (name.includes("rowing")) return "🏋️"
  if (name.includes("planche")) return "🧱"
  if (name.includes("crunch")) return "🧱"
  if (name.includes("burpee")) return "🔥"
  if (name.includes("jump")) return "🔥"
  const byGroup: Record<string, string> = {
    epaules: "🏋️",
    bras: "💪",
    dos: "🏋️",
    jambes: "🦵",
    abdominaux: "🧱",
    pectoraux: "🏋️",
    cardio: "🔥",
    full_body: "🤸",
  }
  return byGroup[exercise.groupe_musculaire] || "🏋️"
}

function buildExerciseAnalysisDraft(exercise: Pick<Exercise, "nom" | "groupe_musculaire" | "niveau">) {
  const normalized = (exercise.nom || "").trim().toLowerCase()
  const group = (exercise.groupe_musculaire || "").trim().toLowerCase()
  const tags = new Set<string>()
  let benefitSummary = "Soutient le renforcement general."

  if (group === "cardio") {
    benefitSummary = "Ameliore l'endurance cardio et augmente la depense energetique."
    tags.add("endurance")
    tags.add("depense")
    tags.add("cardio")
  } else if (group === "abdominaux") {
    benefitSummary = "Renforce la stabilite du tronc et soutient la posture."
    tags.add("stabilite")
    tags.add("posture")
  } else if (group === "jambes") {
    benefitSummary = "Developpe la force du bas du corps et la puissance globale."
    tags.add("force")
    tags.add("puissance-bas-du-corps")
  } else if (group === "dos") {
    benefitSummary = "Travaille le tirage, la posture et l'equilibre du haut du corps."
    tags.add("tirage")
    tags.add("posture")
  } else if (group === "pectoraux") {
    benefitSummary = "Renforce la poussee et le volume du haut du corps."
    tags.add("poussee")
    tags.add("hypertrophie")
  } else if (group === "epaules") {
    benefitSummary = "Ameliore la stabilite et la force des epaules."
    tags.add("poussee")
    tags.add("renforcement")
  } else if (group === "bras") {
    benefitSummary = "Renforce les bras en travail accessoire ou analytique."
    tags.add("renforcement")
  } else if (group === "full_body") {
    benefitSummary = "Mobilise plusieurs chaines musculaires et augmente la depense globale."
    tags.add("depense")
    tags.add("renforcement")
    tags.add("full-body")
  }

  if (["intermediaire", "avance"].includes(exercise.niveau || "")) {
    tags.add("progression")
  }
  if (["squat", "deadlift", "souleve", "hip thrust", "fente", "leg press"].some((keyword) => normalized.includes(keyword))) {
    tags.add("force")
  }
  if (["curl", "extension", "elevation", "fly"].some((keyword) => normalized.includes(keyword))) {
    tags.add("hypertrophie")
  }
  if (["traction", "rowing", "tirage"].some((keyword) => normalized.includes(keyword))) {
    tags.add("tirage")
  }
  if (["pompe", "developpe", "press", "dips"].some((keyword) => normalized.includes(keyword))) {
    tags.add("poussee")
  }
  if (["burpee", "jump", "course", "velo", "marche", "corde", "rameur"].some((keyword) => normalized.includes(keyword))) {
    tags.add("endurance")
    tags.add("depense")
  }
  if (["gainage", "planche", "crunch", "ab wheel"].some((keyword) => normalized.includes(keyword))) {
    tags.add("stabilite")
    tags.add("posture")
  }

  return {
    benefitSummary,
    qualityTags: Array.from(tags).join(","),
  }
}

function prefillExerciseAnalysis() {
  const draft = buildExerciseAnalysisDraft({
    nom: exerciseForm.nom,
    groupe_musculaire: exerciseForm.groupe_musculaire,
    niveau: exerciseForm.niveau,
  })
  if (!exerciseForm.benefit_summary.trim()) {
    exerciseForm.benefit_summary = draft.benefitSummary
  }
  if (!exerciseForm.quality_tags.trim()) {
    exerciseForm.quality_tags = draft.qualityTags
  }
}

async function prefillAllIncompleteExercises() {
  const incompleteExercises = exercises.value.filter((exercise) => isExerciseAnalysisIncomplete(exercise))
  if (!incompleteExercises.length) {
    feedback.value = "Tous les exercices ont deja une analyse."
    return
  }

  let updatedCount = 0
  try {
    for (const exercise of incompleteExercises) {
      const draft = buildExerciseAnalysisDraft(exercise)
      const body = new FormData()
      let hasChanges = false

      if (!exercise.benefit_summary?.trim()) {
        body.append("benefit_summary", draft.benefitSummary)
        hasChanges = true
      }
      if (!exercise.quality_tags?.trim()) {
        body.append("quality_tags", draft.qualityTags)
        hasChanges = true
      }

      if (!hasChanges) {
        continue
      }

      await request(`/fitness/exercises/${exercise.id}/`, { method: "PATCH", body })
      updatedCount += 1
    }

    feedback.value = updatedCount
      ? `${updatedCount} exercice(s) pre-remplis automatiquement.`
      : "Aucun exercice a mettre a jour."
    await refreshExercises()
  } catch (error: any) {
    feedback.value = error?.data?.detail || "Impossible de pre-remplir tous les exercices."
  }
}

function resolveImageSrc(item: { image_file_url?: string | null; image_url?: string | null }) {
  return item.image_file_url || item.image_url || ""
}

function clampPercentage(value: number) {
  return Math.max(0, Math.min(100, value))
}

function clampZoom(value: number) {
  return Math.max(1, Math.min(3, value))
}

function ingredientImageStyle(item: Pick<Ingredient, "image_focus_x" | "image_focus_y" | "image_zoom">) {
  const x = clampPercentage(Number(item.image_focus_x ?? 50))
  const y = clampPercentage(Number(item.image_focus_y ?? 50))
  const zoom = clampZoom(Number(item.image_zoom ?? 1))
  return {
    objectPosition: `${x}% ${y}%`,
    transform: `scale(${zoom})`,
    transformOrigin: "center center",
  }
}

const editingIngredientImageStyle = computed(() => ({
  objectPosition: `${clampPercentage(Number(ingredientForm.image_focus_x || 50))}% ${clampPercentage(Number(ingredientForm.image_focus_y || 50))}%`,
  transform: `scale(${clampZoom(Number(ingredientForm.image_zoom || 1))})`,
  transformOrigin: "center center",
}))

function isIngredientCategoryCollapsed(category: string) {
  return Boolean(collapsedIngredientCategories.value[category])
}

function toggleIngredientCategory(category: string) {
  collapsedIngredientCategories.value = {
    ...collapsedIngredientCategories.value,
    [category]: !collapsedIngredientCategories.value[category],
  }
}

function resetCityForm() {
  cityForm.nom = ""
  cityEditId.value = null
}

function startCityEdit(city: City) {
  cityEditId.value = city.id
  cityForm.nom = city.nom
}

function cancelCityEdit() {
  resetCityForm()
}

function resetVendorForm() {
  vendorForm.nom = ""
  vendorForm.city = 0
  vendorForm.description = ""
  vendorEditId.value = null
}

function resetWellbeingArticleForm() {
  wellbeingArticleForm.nom = ""
  wellbeingArticleForm.icone = ""
  wellbeingArticleForm.categorie = ""
  wellbeingArticleForm.unite_base = "piece"
  wellbeingArticleForm.description = ""
  wellbeingArticleForm.vendor_ids = []
  wellbeingArticleEditId.value = null
}

function startWellbeingArticleEdit(article: WellbeingArticle) {
  wellbeingArticleEditId.value = article.id
  wellbeingArticleForm.nom = article.nom
  wellbeingArticleForm.icone = article.icone || ""
  wellbeingArticleForm.categorie = article.categorie || ""
  wellbeingArticleForm.unite_base = article.unite_base || "piece"
  wellbeingArticleForm.description = article.description || ""
  wellbeingArticleForm.vendor_ids = [...(article.vendor_ids || [])]
}

function cancelWellbeingArticleEdit() {
  resetWellbeingArticleForm()
}

function openWellbeingArticleCreateModal() {
  resetWellbeingArticleForm()
  if (selectedWellbeingArticleCategory.value) {
    wellbeingArticleForm.categorie = selectedWellbeingArticleCategory.value
  }
  wellbeingArticleModalMode.value = "create"
  showWellbeingArticleModal.value = true
}

function openWellbeingArticleEditModal(article: WellbeingArticle) {
  startWellbeingArticleEdit(article)
  wellbeingArticleModalMode.value = "edit"
  selectedWellbeingArticle.value = article
  showWellbeingArticleModal.value = true
}

function openWellbeingArticleDetailModal(article: WellbeingArticle) {
  selectedWellbeingArticle.value = article
  wellbeingArticleModalMode.value = "detail"
  showWellbeingArticleModal.value = true
}

function closeWellbeingArticleModal() {
  showWellbeingArticleModal.value = false
  if (wellbeingArticleModalMode.value !== "detail") {
    resetWellbeingArticleForm()
  }
  wellbeingArticleModalMode.value = "create"
  selectedWellbeingArticle.value = null
}

function toggleWellbeingArticleVendor(vendorId: number, checked: boolean) {
  const ids = new Set(wellbeingArticleForm.vendor_ids)
  if (checked) ids.add(vendorId)
  else ids.delete(vendorId)
  wellbeingArticleForm.vendor_ids = Array.from(ids)
}

function startVendorEdit(vendor: Vendor) {
  vendorEditId.value = vendor.id
  vendorForm.nom = vendor.nom
  vendorForm.city = vendor.city
  vendorForm.description = vendor.description || ""
}

function cancelVendorEdit() {
  resetVendorForm()
}

function getIngredientPriceDraft(ingredientId: number) {
  if (!ingredientPriceDrafts[ingredientId]) {
    ingredientPriceDrafts[ingredientId] = {
      ingredient: ingredientId,
      vendor: 0,
      prix: "",
      date_dernier_prix: today,
      editId: null,
    }
  }
  return ingredientPriceDrafts[ingredientId]
}

function resetIngredientPriceDraft(ingredientId: number) {
  ingredientPriceDrafts[ingredientId] = {
    ingredient: ingredientId,
    vendor: 0,
    prix: "",
    date_dernier_prix: today,
    editId: null,
  }
}

function getWellbeingArticlePriceDraft(articleId: number) {
  if (!wellbeingArticlePriceDrafts[articleId]) {
    wellbeingArticlePriceDrafts[articleId] = {
      article: articleId,
      vendor: 0,
      prix: "",
      date_dernier_prix: today,
      editId: null,
    }
  }
  return wellbeingArticlePriceDrafts[articleId]
}

function resetWellbeingArticlePriceDraft(articleId: number) {
  wellbeingArticlePriceDrafts[articleId] = {
    article: articleId,
    vendor: 0,
    prix: "",
    date_dernier_prix: today,
    editId: null,
  }
}

function startWellbeingArticlePriceCreateForArticle(articleId: number) {
  resetWellbeingArticlePriceDraft(articleId)
}

function startWellbeingArticlePriceEdit(price: WellbeingArticlePrice) {
  wellbeingArticlePriceDrafts[price.article] = {
    article: price.article,
    vendor: price.vendor,
    prix: String(price.prix),
    date_dernier_prix: price.date_dernier_prix,
    editId: price.id,
  }
  catalogCityFilter.value = price.city_id || 0
}

function cancelWellbeingArticlePriceEdit(articleId: number) {
  resetWellbeingArticlePriceDraft(articleId)
}

function getPricesForWellbeingArticle(articleId: number) {
  return wellbeingArticlePrices.value
    .filter((price) => price.article === articleId && (!catalogCityFilter.value || price.city_id === catalogCityFilter.value))
    .sort((a, b) => safeLocaleCompare(a.vendor_nom, b.vendor_nom))
}

function startIngredientPriceCreateForIngredient(ingredientId: number) {
  resetIngredientPriceDraft(ingredientId)
}

function startIngredientPriceEdit(price: IngredientPrice) {
  ingredientPriceDrafts[price.ingredient] = {
    ingredient: price.ingredient,
    vendor: price.vendor,
    prix: String(price.prix),
    date_dernier_prix: price.date_dernier_prix,
    editId: price.id,
  }
  catalogCityFilter.value = price.city_id || 0
}

function cancelIngredientPriceEdit(ingredientId: number) {
  resetIngredientPriceDraft(ingredientId)
}

function getPricesForIngredient(ingredientId: number) {
  return filteredIngredientPrices.value
    .filter((price) => price.ingredient === ingredientId)
    .sort((a, b) => safeLocaleCompare(a.vendor_nom, b.vendor_nom))
}

function updateImageSelection(target: "ingredient" | "recipe" | "exercise", event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0] || null
  const preview = file ? URL.createObjectURL(file) : ""

  if (target === "ingredient") {
    if (ingredientImagePreview.value.startsWith("blob:")) {
      URL.revokeObjectURL(ingredientImagePreview.value)
    }
    ingredientImageFile.value = file
    if (file) {
      ingredientImagePreview.value = preview
      ingredientForm.image_focus_x = 50
      ingredientForm.image_focus_y = 50
      ingredientForm.image_zoom = 1
    }
    return
  }

  if (target === "recipe") {
    if (recipeImagePreview.value.startsWith("blob:")) {
      URL.revokeObjectURL(recipeImagePreview.value)
    }
    recipeImageFile.value = file
    if (file) {
      recipeImagePreview.value = preview
    }
    return
  }

  if (exerciseImagePreview.value.startsWith("blob:")) {
    URL.revokeObjectURL(exerciseImagePreview.value)
  }
  exerciseImageFile.value = file
  if (file) {
    exerciseImagePreview.value = preview
  }
}

function resetImageSelection(target: "ingredient" | "recipe" | "exercise") {
  if (target === "ingredient") {
    if (ingredientImagePreview.value.startsWith("blob:")) {
      URL.revokeObjectURL(ingredientImagePreview.value)
    }
    ingredientImageFile.value = null
    ingredientImagePreview.value = ""
    ingredientImageDragActive.value = false
    return
  }

  if (target === "recipe") {
    if (recipeImagePreview.value.startsWith("blob:")) {
      URL.revokeObjectURL(recipeImagePreview.value)
    }
    recipeImageFile.value = null
    recipeImagePreview.value = ""
    return
  }

  if (exerciseImagePreview.value.startsWith("blob:")) {
    URL.revokeObjectURL(exerciseImagePreview.value)
  }
  exerciseImageFile.value = null
  exerciseImagePreview.value = ""
}

function resetIngredientForm() {
  ingredientForm.nom = ""
  ingredientForm.icone = ""
  ingredientForm.categorie = ""
  ingredientForm.is_perishable = false
  ingredientForm.max_storage_days = ""
  ingredientForm.image_url = ""
  ingredientForm.image_focus_x = 50
  ingredientForm.image_focus_y = 50
  ingredientForm.image_zoom = 1
  ingredientForm.preparation = ""
  ingredientForm.unite_base = "g"
  ingredientForm.calories_100g = ""
  ingredientForm.proteines_100g = ""
  ingredientForm.glucides_100g = ""
  ingredientForm.lipides_100g = ""
  ingredientForm.micronutrient_tags = []
  ingredientForm.benefit_tags = []
  ingredientForm.drawback_tags = []
  ingredientEditId.value = null
  selectedIngredient.value = null
  resetImageSelection("ingredient")
}

function resetRecipeForm() {
  recipeForm.nom = ""
  recipeForm.icone = ""
  recipeForm.image_url = ""
  recipeForm.preparation = ""
  recipeForm.categorie_repas = "dejeuner"
  recipeForm.objectif_adapte = ""
  recipeForm.actif = true
  recipeForm.recipe_ingredients = [{ ingredient: 0, quantite: "", unite: "g" }]
  recipeEditId.value = null
  selectedRecipe.value = null
  resetImageSelection("recipe")
}

function resetExerciseForm() {
  exerciseForm.nom = ""
  exerciseForm.icone = ""
  exerciseForm.groupe_musculaire = "full_body"
  exerciseForm.niveau = "debutant"
  exerciseForm.image_url = ""
  exerciseForm.preparation = ""
  exerciseForm.description = ""
  exerciseForm.benefit_summary = ""
  exerciseForm.quality_tags = ""
  exerciseEditId.value = null
  selectedExercise.value = null
  resetImageSelection("exercise")
}

function openIngredientCreateModal() {
  resetIngredientForm()
  ingredientForm.categorie = selectedIngredientCategory.value || ""
  ingredientModalMode.value = "create"
  showIngredientModal.value = true
}

function openExerciseCreateModal() {
  resetExerciseForm()
  exerciseForm.groupe_musculaire = selectedExerciseGroupValue.value || "full_body"
  exerciseModalMode.value = "create"
  showExerciseModal.value = true
}

function openRecipeCreateModal() {
  resetRecipeForm()
  recipeModalMode.value = "create"
  showRecipeModal.value = true
}

function openIngredientEditModal(ingredient: Ingredient) {
  ingredientModalMode.value = "edit"
  ingredientEditId.value = ingredient.id
  selectedIngredient.value = ingredient
  ingredientForm.nom = ingredient.nom
  ingredientForm.icone = ingredient.icone || ""
  ingredientForm.categorie = ingredient.categorie || ""
  ingredientForm.is_perishable = Boolean(ingredient.is_perishable)
  ingredientForm.max_storage_days = ingredient.max_storage_days != null ? String(ingredient.max_storage_days) : ""
  ingredientForm.image_url = ingredient.image_url || ""
  ingredientForm.image_focus_x = Number(ingredient.image_focus_x ?? 50)
  ingredientForm.image_focus_y = Number(ingredient.image_focus_y ?? 50)
  ingredientForm.image_zoom = Number(ingredient.image_zoom ?? 1)
  ingredientForm.preparation = ingredient.preparation || ""
  ingredientForm.unite_base = ingredient.unite_base || "g"
  ingredientForm.calories_100g = String(ingredient.calories_100g || "")
  ingredientForm.proteines_100g = String(ingredient.proteines_100g || "")
  ingredientForm.glucides_100g = String(ingredient.glucides_100g || "")
  ingredientForm.lipides_100g = String(ingredient.lipides_100g || "")
  ingredientForm.micronutrient_tags = Array.isArray(ingredient.micronutrient_tags) ? [...ingredient.micronutrient_tags] : []
  ingredientForm.benefit_tags = Array.isArray(ingredient.benefit_tags) ? [...ingredient.benefit_tags] : []
  ingredientForm.drawback_tags = Array.isArray(ingredient.drawback_tags) ? [...ingredient.drawback_tags] : []
  resetImageSelection("ingredient")
  ingredientImagePreview.value = resolveImageSrc(ingredient)
  showIngredientModal.value = true
}

function toggleIngredientMicronutrient(value: string) {
  toggleIngredientListValue("micronutrient_tags", value)
}

function toggleIngredientListValue(field: "micronutrient_tags" | "benefit_tags" | "drawback_tags", value: string) {
  if (ingredientForm[field].includes(value)) {
    ingredientForm[field] = ingredientForm[field].filter((item) => item !== value)
    return
  }
  ingredientForm[field] = [...ingredientForm[field], value]
}

function openIngredientDetailModal(ingredient: Ingredient) {
  selectedIngredient.value = ingredient
  ingredientModalMode.value = "detail"
  showIngredientModal.value = true
}

function openRecipeEditModal(recipe: Recipe) {
  recipeModalMode.value = "edit"
  recipeEditId.value = recipe.id
  selectedRecipe.value = recipe
  recipeForm.nom = recipe.nom
  recipeForm.icone = recipe.icone || ""
  recipeForm.image_url = recipe.image_url || ""
  recipeForm.preparation = recipe.preparation || ""
  recipeForm.categorie_repas = recipe.categorie_repas || "dejeuner"
  recipeForm.objectif_adapte = recipe.objectif_adapte || ""
  recipeForm.actif = recipe.actif ?? true
  recipeForm.recipe_ingredients = recipe.recipe_ingredients.length
    ? recipe.recipe_ingredients.map((item) => ({
        ingredient: item.ingredient,
        quantite: String(item.quantite || ""),
        unite: item.unite || "g",
      }))
    : [{ ingredient: 0, quantite: "", unite: "g" }]
  resetImageSelection("recipe")
  showRecipeModal.value = true
}

function openRecipeDetailModal(recipe: Recipe) {
  selectedRecipe.value = recipe
  recipeModalMode.value = "detail"
  showRecipeModal.value = true
}

function openExerciseEditModal(exercise: Exercise) {
  exerciseModalMode.value = "edit"
  exerciseEditId.value = exercise.id
  selectedExercise.value = exercise
  exerciseForm.nom = exercise.nom
  exerciseForm.icone = inferExerciseIcon(exercise)
  exerciseForm.groupe_musculaire = exercise.groupe_musculaire || "full_body"
  exerciseForm.niveau = exercise.niveau || "debutant"
  exerciseForm.image_url = exercise.image_url || ""
  exerciseForm.preparation = exercise.preparation || ""
  exerciseForm.description = exercise.description || ""
  exerciseForm.benefit_summary = exercise.benefit_summary || ""
  exerciseForm.quality_tags = exercise.quality_tags || ""
  resetImageSelection("exercise")
  showExerciseModal.value = true
}

function openExerciseDetailModal(exercise: Exercise) {
  selectedExercise.value = exercise
  exerciseModalMode.value = "detail"
  showExerciseModal.value = true
}

function closeIngredientModal() {
  showIngredientModal.value = false
  if (ingredientModalMode.value !== "detail") {
    resetIngredientForm()
  }
  ingredientModalMode.value = "create"
  selectedIngredient.value = null
}

function closeExerciseModal() {
  showExerciseModal.value = false
  if (exerciseModalMode.value !== "detail") {
    resetExerciseForm()
  }
  exerciseModalMode.value = "create"
  selectedExercise.value = null
}

function closeRecipeModal() {
  showRecipeModal.value = false
  if (recipeModalMode.value !== "detail") {
    resetRecipeForm()
  }
  recipeModalMode.value = "create"
  selectedRecipe.value = null
}

function updateIngredientImageFocusFromPointer(event: PointerEvent) {
  const currentTarget = event.currentTarget as HTMLElement | null
  if (!currentTarget) {
    return
  }
  const rect = currentTarget.getBoundingClientRect()
  const x = ((event.clientX - rect.left) / rect.width) * 100
  const y = ((event.clientY - rect.top) / rect.height) * 100
  ingredientForm.image_focus_x = Math.round(clampPercentage(x) * 100) / 100
  ingredientForm.image_focus_y = Math.round(clampPercentage(y) * 100) / 100
}

function startIngredientImageDrag(event: PointerEvent) {
  ingredientImageDragActive.value = true
  updateIngredientImageFocusFromPointer(event)
}

function moveIngredientImageDrag(event: PointerEvent) {
  if (!ingredientImageDragActive.value) {
    return
  }
  updateIngredientImageFocusFromPointer(event)
}

function stopIngredientImageDrag() {
  ingredientImageDragActive.value = false
}

function addRecipeIngredientRow() {
  recipeForm.recipe_ingredients.push({ ingredient: 0, quantite: "", unite: "g" })
}

function removeRecipeIngredientRow(index: number) {
  recipeForm.recipe_ingredients.splice(index, 1)
  if (!recipeForm.recipe_ingredients.length) {
    addRecipeIngredientRow()
  }
}

if (!auth.user.value?.is_staff && !auth.user.value?.is_superuser) {
  throw createError({ statusCode: 403, statusMessage: "Acces administrateur requis." })
}

onMounted(async () => {
  await Promise.all([
    refreshUsers(),
    refreshCities(),
    refreshVendors(),
    refreshIngredientPrices(),
    refreshWellbeingArticles(),
    refreshWellbeingArticlePrices(),
    refreshIngredients(),
    refreshRecipes(),
    refreshExercises(),
  ])
})

async function refreshIngredients() {
  const response = await request<Ingredient[] | { results?: Ingredient[] }>("/nutrition/ingredients/", {
    method: "GET",
    query: { _ts: Date.now() },
  })
  ingredientsData.value = unwrapApiList(response)
}

async function refreshCities() {
  const response = await request<City[] | { results?: City[] }>("/nutrition/cities/", {
    method: "GET",
    query: { _ts: Date.now() },
    headers: { "Cache-Control": "no-store" },
  })
  citiesData.value = unwrapApiList(response)
}

async function refreshVendors() {
  const response = await request<Vendor[] | { results?: Vendor[] }>("/nutrition/vendors/", {
    method: "GET",
    query: { _ts: Date.now() },
    headers: { "Cache-Control": "no-store" },
  })
  vendorsData.value = unwrapApiList(response)
}

async function refreshIngredientPrices() {
  const response = await request<IngredientPrice[] | { results?: IngredientPrice[] }>("/nutrition/ingredient-prices/", {
    method: "GET",
    query: { _ts: Date.now() },
    headers: { "Cache-Control": "no-store" },
  })
  ingredientPricesData.value = unwrapApiList(response)
}

async function refreshWellbeingArticles() {
  const response = await request<WellbeingArticle[] | { results?: WellbeingArticle[] }>("/nutrition/wellbeing-articles/", {
    method: "GET",
    query: { _ts: Date.now() },
    headers: { "Cache-Control": "no-store" },
  })
  wellbeingArticlesData.value = unwrapApiList(response)
}

async function refreshWellbeingArticlePrices() {
  const response = await request<WellbeingArticlePrice[] | { results?: WellbeingArticlePrice[] }>("/nutrition/wellbeing-article-prices/", {
    method: "GET",
    query: { _ts: Date.now() },
    headers: { "Cache-Control": "no-store" },
  })
  wellbeingArticlePricesData.value = unwrapApiList(response)
}

async function refreshRecipes() {
  const response = await request<Recipe[] | { results?: Recipe[] }>("/nutrition/recipes/", {
    method: "GET",
    query: { _ts: Date.now() },
    headers: { "Cache-Control": "no-store" },
  })
  recipesData.value = unwrapApiList(response)
}

async function refreshExercises() {
  const response = await request<Exercise[] | { results?: Exercise[] }>("/fitness/exercises/", {
    method: "GET",
    query: { _ts: Date.now() },
    headers: { "Cache-Control": "no-store" },
  })
  exercisesData.value = unwrapApiList(response).map((exercise) => ({
    ...exercise,
    icone: exercise.icone || inferExerciseIcon(exercise),
  }))
  if (import.meta.client) {
    console.log("admin exercises loaded", exercisesData.value.length, exercisesData.value.map((exercise) => exercise.nom))
  }
}

async function reloadCatalogData() {
  await Promise.all([
    refreshCities(),
    refreshVendors(),
    refreshIngredientPrices(),
    refreshWellbeingArticles(),
    refreshWellbeingArticlePrices(),
  ])
}

async function saveIngredient() {
  try {
    const body = new FormData()
    body.append("nom", ingredientForm.nom)
    body.append("icone", ingredientForm.icone)
    body.append("categorie", ingredientForm.categorie)
    body.append("is_perishable", ingredientForm.is_perishable ? "true" : "false")
    body.append(
      "max_storage_days",
      ingredientForm.is_perishable && String(ingredientForm.max_storage_days || "").trim()
        ? String(ingredientForm.max_storage_days).trim()
        : "",
    )
    body.append("image_url", ingredientForm.image_url)
    body.append("image_focus_x", String(ingredientForm.image_focus_x))
    body.append("image_focus_y", String(ingredientForm.image_focus_y))
    body.append("image_zoom", String(ingredientForm.image_zoom))
    body.append("preparation", ingredientForm.preparation)
    body.append("unite_base", ingredientForm.unite_base)
    body.append("calories_100g", String(cleanDecimal(ingredientForm.calories_100g)))
    body.append("proteines_100g", String(cleanDecimal(ingredientForm.proteines_100g)))
    body.append("glucides_100g", String(cleanDecimal(ingredientForm.glucides_100g)))
    body.append("lipides_100g", String(cleanDecimal(ingredientForm.lipides_100g)))
    body.append("micronutrient_tags", JSON.stringify(ingredientForm.micronutrient_tags))
    body.append("benefit_tags", JSON.stringify(ingredientForm.benefit_tags))
    body.append("drawback_tags", JSON.stringify(ingredientForm.drawback_tags))
    if (ingredientImageFile.value) {
      body.append("image", ingredientImageFile.value)
    }
    if (ingredientEditId.value) {
      await request(`/nutrition/ingredients/${ingredientEditId.value}/`, { method: "PATCH", body })
      feedback.value = "Ingredient mis a jour."
    } else {
      await request("/nutrition/ingredients/", { method: "POST", body })
      feedback.value = "Ingredient enregistre."
    }
    closeIngredientModal()
    await refreshIngredients()
  } catch (error: any) {
    feedback.value = error?.data?.detail || "Impossible d'enregistrer l'ingredient."
  }
}

async function deleteIngredient(ingredientId: number) {
  if (!window.confirm("Supprimer cet ingredient ?")) {
    return
  }
  try {
    await request(`/nutrition/ingredients/${ingredientId}/`, { method: "DELETE" })
    if (ingredientEditId.value === ingredientId) {
      closeIngredientModal()
    }
    feedback.value = "Ingredient supprime."
    await refreshIngredients()
  } catch (error: any) {
    feedback.value = error?.data?.detail || "Impossible de supprimer l'ingredient."
  }
}

function exportIngredientsExcel() {
  if (!import.meta.client) {
    return
  }
  window.open("/api/nutrition/ingredients/export-excel/", "_blank")
}

async function saveCity() {
  try {
    const payload = { nom: cityForm.nom.trim() }
    if (!payload.nom) {
      feedback.value = "Le nom de la ville est requis."
      return
    }
    if (cityEditId.value) {
      await request(`/nutrition/cities/${cityEditId.value}/`, { method: "PATCH", body: payload })
      feedback.value = "Ville mise a jour."
    } else {
      await request("/nutrition/cities/", { method: "POST", body: payload })
      feedback.value = "Ville creee."
    }
    resetCityForm()
    await reloadCatalogData()
  } catch (error: any) {
    feedback.value = error?.data?.detail || "Impossible d'enregistrer la ville."
  }
}

async function deleteCity(cityId: number) {
  if (!window.confirm("Supprimer cette ville ?")) {
    return
  }
  try {
    await request(`/nutrition/cities/${cityId}/`, { method: "DELETE" })
    feedback.value = "Ville supprimee."
    if (cityEditId.value === cityId) {
      resetCityForm()
    }
    await reloadCatalogData()
  } catch (error: any) {
    feedback.value = error?.data?.detail || "Impossible de supprimer la ville."
  }
}

async function saveVendor() {
  try {
    const payload = {
      nom: vendorForm.nom.trim(),
      city: vendorForm.city || null,
      description: vendorForm.description.trim(),
    }
    if (!payload.nom) {
      feedback.value = "Le nom du vendeur est requis."
      return
    }
    if (!payload.city) {
      feedback.value = "Choisissez une ville."
      return
    }
    if (vendorEditId.value) {
      await request(`/nutrition/vendors/${vendorEditId.value}/`, { method: "PATCH", body: payload })
      feedback.value = "Vendeur mis a jour."
    } else {
      await request("/nutrition/vendors/", { method: "POST", body: payload })
      feedback.value = "Vendeur cree."
    }
    resetVendorForm()
    await reloadCatalogData()
  } catch (error: any) {
    feedback.value = error?.data?.detail || "Impossible d'enregistrer le vendeur."
  }
}

async function saveWellbeingArticle() {
  try {
    const payload = {
      nom: wellbeingArticleForm.nom.trim(),
      icone: wellbeingArticleForm.icone.trim(),
      categorie: wellbeingArticleForm.categorie.trim(),
      unite_base: wellbeingArticleForm.unite_base.trim() || "piece",
      description: wellbeingArticleForm.description.trim(),
      vendor_ids: wellbeingArticleForm.vendor_ids,
    }
    if (!payload.nom) {
      feedback.value = "Le nom de l'article est requis."
      return
    }
    if (wellbeingArticleEditId.value) {
      await request(`/nutrition/wellbeing-articles/${wellbeingArticleEditId.value}/`, { method: "PATCH", body: payload })
      feedback.value = "Article bien-etre mis a jour."
    } else {
      await request("/nutrition/wellbeing-articles/", { method: "POST", body: payload })
      feedback.value = "Article bien-etre cree."
    }
    closeWellbeingArticleModal()
    await reloadCatalogData()
  } catch (error: any) {
    feedback.value = error?.data?.detail || "Impossible d'enregistrer l'article bien-etre."
  }
}

async function deleteWellbeingArticle(articleId: number) {
  if (!window.confirm("Supprimer cet article bien-etre ?")) {
    return
  }
  try {
    await request(`/nutrition/wellbeing-articles/${articleId}/`, { method: "DELETE" })
    if (wellbeingArticleEditId.value === articleId) {
      closeWellbeingArticleModal()
    }
    feedback.value = "Article bien-etre supprime."
    await reloadCatalogData()
  } catch (error: any) {
    feedback.value = error?.data?.detail || "Impossible de supprimer l'article bien-etre."
  }
}

async function deleteVendor(vendorId: number) {
  if (!window.confirm("Supprimer ce vendeur ?")) {
    return
  }
  try {
    await request(`/nutrition/vendors/${vendorId}/`, { method: "DELETE" })
    feedback.value = "Vendeur supprime."
    if (vendorEditId.value === vendorId) {
      resetVendorForm()
    }
    await reloadCatalogData()
  } catch (error: any) {
    feedback.value = error?.data?.detail || "Impossible de supprimer le vendeur."
  }
}

async function saveIngredientPrice(ingredientId: number) {
  try {
    const draft = getIngredientPriceDraft(ingredientId)
    const payload = {
      ingredient: draft.ingredient || null,
      vendor: draft.vendor || null,
      prix: cleanOptionalDecimal(draft.prix),
      date_dernier_prix: draft.date_dernier_prix,
    }
    if (!payload.ingredient) {
      feedback.value = "Choisissez un ingredient."
      return
    }
    if (!payload.vendor) {
      feedback.value = "Choisissez un vendeur."
      return
    }
    if (!payload.date_dernier_prix) {
      feedback.value = "La date du prix est requise."
      return
    }
    if (draft.editId) {
      await request(`/nutrition/ingredient-prices/${draft.editId}/`, { method: "PATCH", body: payload })
      feedback.value = "Prix mis a jour."
    } else {
      await request("/nutrition/ingredient-prices/", { method: "POST", body: payload })
      feedback.value = "Prix cree."
    }
    resetIngredientPriceDraft(ingredientId)
    await reloadCatalogData()
  } catch (error: any) {
    feedback.value = error?.data?.detail || "Impossible d'enregistrer le prix."
  }
}

async function deleteIngredientPrice(priceId: number) {
  if (!window.confirm("Supprimer ce prix ?")) {
    return
  }
  try {
    await request(`/nutrition/ingredient-prices/${priceId}/`, { method: "DELETE" })
    feedback.value = "Prix supprime."
    await reloadCatalogData()
  } catch (error: any) {
    feedback.value = error?.data?.detail || "Impossible de supprimer le prix."
  }
}

async function saveWellbeingArticlePrice(articleId: number) {
  try {
    const draft = getWellbeingArticlePriceDraft(articleId)
    const payload = {
      article: draft.article || null,
      vendor: draft.vendor || null,
      prix: cleanOptionalDecimal(draft.prix),
      date_dernier_prix: draft.date_dernier_prix,
    }
    if (!payload.article) {
      feedback.value = "Choisissez un article."
      return
    }
    if (!payload.vendor) {
      feedback.value = "Choisissez un vendeur."
      return
    }
    if (!payload.date_dernier_prix) {
      feedback.value = "La date du prix est requise."
      return
    }
    if (draft.editId) {
      await request(`/nutrition/wellbeing-article-prices/${draft.editId}/`, { method: "PATCH", body: payload })
      feedback.value = "Prix article bien-etre mis a jour."
    } else {
      await request("/nutrition/wellbeing-article-prices/", { method: "POST", body: payload })
      feedback.value = "Prix article bien-etre cree."
    }
    resetWellbeingArticlePriceDraft(articleId)
    await reloadCatalogData()
  } catch (error: any) {
    feedback.value = error?.data?.detail || "Impossible d'enregistrer le prix de l'article bien-etre."
  }
}

async function deleteWellbeingArticlePrice(priceId: number) {
  if (!window.confirm("Supprimer ce prix ?")) {
    return
  }
  try {
    await request(`/nutrition/wellbeing-article-prices/${priceId}/`, { method: "DELETE" })
    feedback.value = "Prix article bien-etre supprime."
    await reloadCatalogData()
  } catch (error: any) {
    feedback.value = error?.data?.detail || "Impossible de supprimer le prix de l'article bien-etre."
  }
}

async function createAdminUser() {
  try {
    await request<{ user: AdminUser }>("/auth/admin/users/", {
      method: "POST",
      body: {
        username: userForm.username,
        email: userForm.email,
        password: userForm.password,
        is_staff: userForm.is_staff,
        is_superuser: userForm.is_superuser,
        is_active: userForm.is_active,
      },
    })
    feedback.value = "Utilisateur cree avec succes."
    userForm.username = ""
    userForm.email = ""
    userForm.password = ""
    userForm.is_staff = false
    userForm.is_superuser = false
    userForm.is_active = true
    await refreshUsers()
  } catch (error: any) {
    feedback.value = error?.data?.detail || "Impossible de creer l'utilisateur."
  }
}

async function saveRecipe() {
  try {
    const body = new FormData()
    body.append("nom", recipeForm.nom)
    body.append("icone", recipeForm.icone.trim())
    body.append("image_url", recipeForm.image_url)
    body.append("preparation", recipeForm.preparation)
    body.append("categorie_repas", recipeForm.categorie_repas)
    body.append("objectif_adapte", recipeForm.objectif_adapte)
    body.append("actif", String(recipeForm.actif))
    body.append(
      "recipe_ingredients_json",
      JSON.stringify(
        recipeForm.recipe_ingredients
          .filter((item) => item.ingredient && item.quantite.trim())
          .map((item) => ({
            ingredient: item.ingredient,
            quantite: cleanDecimal(item.quantite),
            unite: item.unite || "g",
          })),
      ),
    )
    if (recipeImageFile.value) {
      body.append("image", recipeImageFile.value)
    }
    if (recipeEditId.value) {
      await request(`/nutrition/recipes/${recipeEditId.value}/`, { method: "PATCH", body })
      feedback.value = "Recette mise a jour."
    } else {
      await request("/nutrition/recipes/", { method: "POST", body })
      feedback.value = "Recette enregistree."
    }
    closeRecipeModal()
    await refreshRecipes()
  } catch (error: any) {
    feedback.value = error?.data?.detail || "Impossible d'enregistrer la recette."
  }
}

async function deleteRecipe(recipeId: number) {
  if (!window.confirm("Supprimer cette recette ?")) {
    return
  }
  try {
    await request(`/nutrition/recipes/${recipeId}/`, { method: "DELETE" })
    if (recipeEditId.value === recipeId) {
      closeRecipeModal()
    }
    feedback.value = "Recette supprimee."
    await refreshRecipes()
  } catch (error: any) {
    feedback.value = error?.data?.detail || "Impossible de supprimer la recette."
  }
}

async function saveExercise() {
  try {
    const body = new FormData()
    body.append("nom", exerciseForm.nom)
    body.append("icone", exerciseForm.icone.trim() || inferExerciseIcon(exerciseForm))
    body.append("groupe_musculaire", exerciseForm.groupe_musculaire)
    body.append("niveau", exerciseForm.niveau)
    body.append("image_url", exerciseForm.image_url)
    body.append("preparation", exerciseForm.preparation)
    body.append("description", exerciseForm.description)
    body.append("benefit_summary", exerciseForm.benefit_summary)
    body.append("quality_tags", exerciseForm.quality_tags)
    if (exerciseImageFile.value) {
      body.append("image", exerciseImageFile.value)
    }
    if (exerciseEditId.value) {
      await request(`/fitness/exercises/${exerciseEditId.value}/`, { method: "PATCH", body })
      feedback.value = "Exercice mis a jour."
    } else {
      await request("/fitness/exercises/", { method: "POST", body })
      feedback.value = "Exercice enregistre."
    }
    closeExerciseModal()
    await refreshExercises()
  } catch (error: any) {
    feedback.value = error?.data?.detail || "Impossible d'enregistrer l'exercice."
  }
}

async function deleteExercise(exerciseId: number) {
  if (!window.confirm("Supprimer cet exercice ?")) {
    return
  }
  try {
    await request(`/fitness/exercises/${exerciseId}/`, { method: "DELETE" })
    if (exerciseEditId.value === exerciseId) {
      closeExerciseModal()
    }
    feedback.value = "Exercice supprime."
    await refreshExercises()
  } catch (error: any) {
    feedback.value = error?.data?.detail || "Impossible de supprimer l'exercice."
  }
}

async function assignWorkoutPlan() {
  if (!coachForm.user_id) {
    feedback.value = "Choisissez un utilisateur."
    return
  }
  try {
    await request("/fitness/workout-plans/generate/", {
      method: "POST",
      body: {
        user_id: coachForm.user_id,
        date_debut: coachForm.date_debut,
        frequence_semaine: coachForm.frequence_semaine,
        duree_semaines: coachForm.duree_semaines,
        replace_active: true,
      },
    })
    feedback.value = "Programme assigne avec succes."
    await loadAdherence()
  } catch (error: any) {
    feedback.value = error?.data?.detail || "Impossible d'assigner le programme."
  }
}

async function loadAdherence() {
  if (!coachForm.user_id) {
    feedback.value = "Choisissez un utilisateur."
    return
  }
  try {
    adherenceData.value = await request<CoachAdherence>("/fitness/workout-plans/admin-adherence/", {
      method: "GET",
      query: { user_id: coachForm.user_id },
    })
  } catch (error: any) {
    feedback.value = error?.data?.detail || "Impossible de charger l'adherence."
  }
}
</script>

