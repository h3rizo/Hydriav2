<template>
  <section :class="containerClass">
    <div class="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
      <div class="max-w-3xl">
        <p class="aurora-kicker">{{ heroKicker }}</p>
        <h2 class="mt-2 text-2xl font-semibold aurora-title">{{ heroTitle }}</h2>
        <p class="mt-2 text-sm aurora-subtle">
          {{ heroCopy }}
        </p>
      </div>
      <div class="flex flex-wrap gap-2">
        <span v-if="showMealComposer" class="glass-chip">{{ meals.length }} repas visibles</span>
        <span class="glass-chip">{{ householdMembers.length }} membre(s) foyer</span>
        <button
          v-if="showHouseholdMemberModalTrigger"
          class="btn-secondary px-3 py-2 text-sm"
          type="button"
          @click="openMemberModal"
        >
          Ajouter membre
        </button>
        <button
          v-if="showMealModalTrigger"
          class="btn-primary px-3 py-2 text-sm"
          type="button"
          @click="openMealModal"
        >
          Nouveau repas
        </button>
      </div>
    </div>

    <p v-if="feedback" class="mt-4 text-sm text-emerald-300">{{ feedback }}</p>
    <p v-if="errorMessage" class="mt-2 text-sm text-rose-300">{{ errorMessage }}</p>

    <div :class="contentClass">
      <div class="space-y-6">
        <article v-if="showInlineMemberForm" class="glass-card p-5">
          <div class="flex items-center justify-between gap-3">
            <div>
              <p class="text-xs uppercase tracking-[0.24em] aurora-muted">Membres lies</p>
              <h3 class="mt-2 text-lg font-semibold">Ajouter un membre du foyer</h3>
            </div>
            <span class="glass-pill">Etendre le repas a un autre compte</span>
          </div>

          <form class="mt-5 space-y-4" @submit.prevent="createHouseholdMember">
            <div class="grid gap-4 md:grid-cols-2">
              <label class="space-y-2">
                <span class="text-sm aurora-subtle">Nom affiche</span>
                <input v-model="memberForm.name" class="field" type="text" placeholder="Ex: Marie" />
              </label>
              <label class="space-y-2">
                <span class="text-sm aurora-subtle">Relation</span>
                <input v-model="memberForm.relationship" class="field" type="text" placeholder="Ex: Conjointe, enfant, ami" />
              </label>
              <label class="space-y-2">
                <span class="text-sm aurora-subtle">Age</span>
                <input v-model.number="memberForm.age" class="field" type="number" min="0" max="120" />
              </label>
              <label class="space-y-2">
                <span class="text-sm aurora-subtle">Sexe</span>
                <select v-model="memberForm.sex" class="field">
                  <option value="">Selectionner</option>
                  <option value="F">F</option>
                  <option value="M">M</option>
                  <option value="Autre">Autre</option>
                </select>
              </label>
            </div>

            <div class="space-y-2">
              <span class="text-sm aurora-subtle">Lier a un autre utilisateur</span>
              <div class="relative">
                <input
                  v-model="profileSearchQuery"
                  class="field"
                  type="text"
                  autocomplete="off"
                  placeholder="Rechercher par nom, username ou email"
                  @focus="profileResultsOpen = true"
                />
                <div v-if="profileSearchPending" class="mt-2 text-xs aurora-muted">Recherche...</div>
                <div
                  v-if="profileResultsOpen && profileSearchResults.length"
                  class="absolute z-20 mt-2 max-h-64 w-full overflow-auto rounded-3xl border border-white/10 bg-[color:var(--app-bg-base)]/95 p-2 shadow-2xl backdrop-blur"
                >
                  <button
                    v-for="profile in profileSearchResults"
                    :key="profile.id"
                    class="flex w-full items-start justify-between gap-3 rounded-2xl px-3 py-3 text-left transition hover:bg-white/5"
                    type="button"
                    @click="selectLinkedProfile(profile)"
                  >
                    <div>
                      <p class="font-medium text-stone-100">{{ profile.display_name }}</p>
                      <p class="text-xs aurora-subtle">{{ profile.email || "Aucun email" }}</p>
                    </div>
                    <span class="glass-pill">Lier</span>
                  </button>
                </div>
              </div>
              <div v-if="selectedLinkedProfile" class="glass-card flex items-center justify-between gap-3 p-4">
                <div>
                  <p class="text-sm font-semibold text-stone-100">{{ selectedLinkedProfile.display_name }}</p>
                  <p class="text-xs aurora-subtle">{{ selectedLinkedProfile.email || selectedLinkedProfile.username }}</p>
                </div>
                <button class="btn-secondary px-3 py-2 text-sm" type="button" @click="clearLinkedProfile">Retirer le lien</button>
              </div>
            </div>

            <div class="flex flex-wrap gap-3">
              <button class="btn-primary" :disabled="memberPending" type="submit">
                <span>{{ memberPending ? "Enregistrement..." : "Ajouter le membre" }}</span>
              </button>
            </div>
          </form>
        </article>

        <article class="glass-card p-5">
          <div class="flex items-center justify-between gap-3">
            <div>
              <p class="text-xs uppercase tracking-[0.24em] aurora-muted">Foyer</p>
              <h3 class="mt-2 text-lg font-semibold">Participants disponibles</h3>
            </div>
          </div>
          <div class="mt-4 space-y-3">
            <div class="rounded-2xl border border-white/10 bg-white/5 px-4 py-3">
              <p class="text-sm font-semibold text-stone-100">Moi</p>
              <p class="text-xs aurora-subtle">Toujours disponible comme participant direct</p>
            </div>
            <div
              v-for="member in householdMembers"
              :key="member.id"
              class="rounded-2xl border border-white/10 bg-white/5 px-4 py-3"
            >
              <div class="flex items-start justify-between gap-3">
                <div>
                  <p class="text-sm font-semibold text-stone-100">{{ member.name }}</p>
                  <p class="text-xs aurora-subtle">
                    {{ member.relationship || "Membre foyer" }}
                    <template v-if="member.linked_profile_display_name">
                      · Lie a {{ member.linked_profile_display_name }}
                    </template>
                  </p>
                </div>
                <button class="btn-secondary px-3 py-2 text-sm" type="button" @click="toggleParticipantSelection(member.id)">
                  {{ participantSelected(member.id) ? "Retirer" : "Ajouter" }}
                </button>
              </div>
            </div>
            <p v-if="!householdMembers.length" class="text-sm aurora-muted">Aucun membre du foyer enregistre pour le moment.</p>
          </div>
        </article>
      </div>

      <div v-if="showMealComposer" class="space-y-6">
        <article v-if="showInlineMealForm" class="glass-card p-5">
          <div class="flex items-center justify-between gap-3">
            <div>
              <p class="text-xs uppercase tracking-[0.24em] aurora-muted">Nouveau repas</p>
              <h3 class="mt-2 text-lg font-semibold">Creer un repas collectif</h3>
            </div>
            <span class="glass-pill">Courses en total, stats en individuel</span>
          </div>

          <form class="mt-5 space-y-5" @submit.prevent="createMeal">
            <div class="grid gap-4 md:grid-cols-2">
              <label class="space-y-2 md:col-span-2">
                <span class="text-sm aurora-subtle">Titre</span>
                <input v-model="mealForm.title" class="field" type="text" placeholder="Ex: Riz au poulet" />
              </label>
            <label class="space-y-2">
              <span class="text-sm aurora-subtle">Date et heure</span>
              <input v-model="mealForm.eaten_at" class="field" type="datetime-local" />
            </label>
            <label class="space-y-2">
              <span class="text-sm aurora-subtle">Type de repas</span>
              <select v-model="mealForm.source_type" class="field">
                <option value="home_cooked">Cuisine maison</option>
                <option value="bought">Repas achete</option>
                <option value="restaurant">Restaurant</option>
              </select>
            </label>
            <label class="space-y-2">
              <span class="text-sm aurora-subtle">Portions preparees</span>
              <input
                v-model="mealForm.total_servings"
                class="field"
                :placeholder="mealNeedsShopping ? 'Ex: 4 portions cuisinees' : 'Ex: 2 portions achetees'"
                type="number"
                min="0.25"
                step="0.25"
              />
            </label>
            <label class="space-y-2 md:col-span-2">
              <span class="text-sm aurora-subtle">Notes</span>
              <textarea v-model="mealForm.notes" class="field min-h-[100px]" placeholder="Ex: tout le monde a mange le meme plat, enfant plus petite portion" />
            </label>
          </div>

          <div class="rounded-2xl border border-white/10 bg-white/5 px-4 py-3 text-sm aurora-subtle">
            <template v-if="mealNeedsShopping">
              Ce repas est cuisine par toi: les quantites servent aussi pour les courses.
            </template>
            <template v-else>
              Ce repas n'alimente pas les courses. Renseigne quand meme les ingredients estimes pour garder une analyse nutritionnelle correcte.
            </template>
          </div>

            <div class="space-y-3">
              <div class="flex items-center justify-between gap-3">
                <h4 class="text-sm font-semibold uppercase tracking-[0.22em] aurora-muted">Ingredients</h4>
                <button class="btn-secondary px-3 py-2 text-sm" type="button" @click="addIngredientRow">Ajouter une ligne</button>
              </div>

              <div v-for="(ingredientRow, index) in mealForm.ingredients" :key="ingredientRow.key" class="rounded-3xl border border-white/10 bg-white/5 p-4">
                <div class="grid gap-4 md:grid-cols-[1.4fr_0.7fr_0.6fr_auto]">
                  <label class="space-y-2">
                    <span class="text-sm aurora-subtle">Ingredient</span>
                    <select v-model.number="ingredientRow.ingredient" class="field">
                      <option :value="0">Selectionner</option>
                      <optgroup v-for="group in groupedIngredientOptions" :key="group.category" :label="group.category">
                        <option v-for="ingredient in group.items" :key="ingredient.id" :value="ingredient.id">
                          {{ ingredient.icon || "•" }} {{ ingredient.name }}
                        </option>
                      </optgroup>
                    </select>
                  </label>
                  <label class="space-y-2">
                    <span class="text-sm aurora-subtle">Quantite totale</span>
                    <input v-model="ingredientRow.quantity" class="field" type="number" min="0.01" step="0.01" />
                  </label>
                  <label class="space-y-2">
                    <span class="text-sm aurora-subtle">Unite</span>
                    <select v-model="ingredientRow.unit" class="field">
                      <option value="g">g</option>
                      <option value="kg">kg</option>
                    </select>
                  </label>
                  <div class="flex items-end">
                    <button class="btn-secondary px-3 py-3 text-sm" type="button" @click="removeIngredientRow(index)">Retirer</button>
                  </div>
                </div>
              </div>

              <div class="rounded-3xl border border-dashed border-white/10 p-4">
                <div class="grid gap-3 md:grid-cols-[1.2fr_0.7fr_0.6fr_auto]">
                  <input v-model="quickIngredient.name" class="field" type="text" placeholder="Nouvel ingredient" />
                  <input v-model="quickIngredient.kcal_per_100g" class="field" type="number" min="0" step="0.01" placeholder="kcal/100g" />
                  <select v-model="quickIngredient.default_unit" class="field">
                    <option value="g">g</option>
                    <option value="kg">kg</option>
                  </select>
                  <button class="btn-secondary" :disabled="ingredientPending" type="button" @click="createIngredient">Creer</button>
                </div>
              </div>
            </div>

            <div class="space-y-3">
              <div class="flex items-center justify-between gap-3">
                <h4 class="text-sm font-semibold uppercase tracking-[0.22em] aurora-muted">Participants</h4>
                <button class="btn-secondary px-3 py-2 text-sm" type="button" @click="addParticipantRow">Ajouter une ligne</button>
              </div>

              <div v-for="(participantRow, index) in mealForm.participants" :key="participantRow.key" class="rounded-3xl border border-white/10 bg-white/5 p-4">
                <div class="grid gap-4 md:grid-cols-[0.8fr_1.2fr_0.7fr_auto]">
                  <label class="space-y-2">
                    <span class="text-sm aurora-subtle">Type</span>
                    <select v-model="participantRow.targetType" class="field">
                      <option value="self">Moi</option>
                      <option value="household">Membre du foyer</option>
                    </select>
                  </label>
                  <label class="space-y-2">
                    <span class="text-sm aurora-subtle">Participant</span>
                    <select v-model.number="participantRow.household_member" class="field" :disabled="participantRow.targetType !== 'household'">
                      <option :value="0">Selectionner</option>
                      <option v-for="member in householdMembers" :key="member.id" :value="member.id">
                        {{ member.name }}{{ member.linked_profile_display_name ? ` · ${member.linked_profile_display_name}` : "" }}
                      </option>
                    </select>
                  </label>
                  <label class="space-y-2">
                    <span class="text-sm aurora-subtle">Portions mangees</span>
                    <input v-model="participantRow.servings_eaten" class="field" type="number" min="0.25" step="0.25" />
                  </label>
                  <div class="flex items-end">
                    <button class="btn-secondary px-3 py-3 text-sm" type="button" @click="removeParticipantRow(index)">Retirer</button>
                  </div>
                </div>
              </div>
            </div>

            <div class="flex flex-wrap gap-3">
              <button class="btn-primary" :disabled="mealPending" type="submit">
                <span>{{ mealPending ? "Enregistrement..." : "Creer le repas" }}</span>
              </button>
              <button class="btn-secondary" type="button" @click="resetMealForm">Reinitialiser</button>
            </div>
          </form>
        </article>

        <article class="glass-card p-5">
          <div class="flex items-center justify-between gap-3">
            <div>
              <p class="text-xs uppercase tracking-[0.24em] aurora-muted">Historique</p>
              <h3 class="mt-2 text-lg font-semibold">Repas visibles pour ce compte</h3>
            </div>
          </div>
          <div class="mt-4 space-y-4">
            <article v-for="meal in meals" :key="meal.id" class="rounded-3xl border border-white/10 bg-white/5 p-4">
              <div class="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <h4 class="text-lg font-semibold text-stone-100">{{ meal.title }}</h4>
                  <p class="mt-1 text-xs aurora-subtle">
                    {{ formatMealDate(meal.eaten_at) }} · {{ meal.total_servings }} portions preparees
                  </p>
                  <div class="mt-2">
                    <span class="rounded-full border px-2.5 py-1 text-[11px] font-medium" :class="mealSourceTone(meal.source_type)">
                      {{ meal.source_type_label || meal.source_type }}
                    </span>
                  </div>
                  <p class="mt-2 text-sm aurora-subtle">
                    Cree par {{ meal.created_by?.user?.username || "profil" }}
                  </p>
                </div>
                <div class="flex flex-wrap gap-2">
                  <span v-for="participant in meal.participants" :key="participant.id" class="glass-pill">
                    {{ participant.participant_name }} · {{ participant.servings_eaten }} portion(s)
                  </span>
                </div>
              </div>
              <div class="mt-4 grid gap-3 md:grid-cols-2">
                <div class="rounded-2xl border border-white/10 bg-black/10 p-3">
                  <p class="text-xs uppercase tracking-[0.22em] aurora-muted">Ingredients</p>
                  <ul class="mt-2 space-y-1 text-sm aurora-subtle">
                    <li v-for="ingredient in meal.ingredients" :key="ingredient.id">
                      {{ ingredient.ingredient?.name }} · {{ ingredient.quantity }} {{ ingredient.unit }}
                    </li>
                  </ul>
                </div>
                <div class="rounded-2xl border border-white/10 bg-black/10 p-3">
                  <p class="text-xs uppercase tracking-[0.22em] aurora-muted">Analyse individuelle</p>
                  <ul class="mt-2 space-y-1 text-sm aurora-subtle">
                    <li v-for="participant in meal.participants" :key="`nutrition-${participant.id}`">
                      {{ participant.participant_name }} · {{ formatNutrition(participant.nutrition_totals?.kcal) }} kcal
                    </li>
                  </ul>
                </div>
              </div>
            </article>
            <p v-if="!meals.length" class="text-sm aurora-muted">Aucun repas partage visible pour le moment.</p>
          </div>
        </article>
      </div>
    </div>

    <Teleport to="body">
      <div
        v-if="showMemberModal"
        class="shared-meal-modal-overlay"
        @click.self="closeMemberModal"
      >
        <article class="shared-meal-modal-panel max-h-[90vh] w-full max-w-3xl overflow-y-auto p-5">
          <div class="flex items-center justify-between gap-3">
            <div>
              <p class="text-xs uppercase tracking-[0.24em] aurora-muted">Membres lies</p>
              <h3 class="mt-2 text-lg font-semibold">Ajouter un membre du foyer</h3>
            </div>
            <button class="btn-secondary px-3 py-2 text-sm" type="button" @click="closeMemberModal">Fermer</button>
          </div>

          <form class="mt-5 space-y-4" @submit.prevent="createHouseholdMember">
            <div class="grid gap-4 md:grid-cols-2">
              <label class="space-y-2">
                <span class="text-sm aurora-subtle">Nom affiche</span>
                <input v-model="memberForm.name" class="field" type="text" placeholder="Ex: Marie" />
              </label>
              <label class="space-y-2">
                <span class="text-sm aurora-subtle">Relation</span>
                <input v-model="memberForm.relationship" class="field" type="text" placeholder="Ex: Conjointe, enfant, ami" />
              </label>
              <label class="space-y-2">
                <span class="text-sm aurora-subtle">Age</span>
                <input v-model.number="memberForm.age" class="field" type="number" min="0" max="120" />
              </label>
              <label class="space-y-2">
                <span class="text-sm aurora-subtle">Sexe</span>
                <select v-model="memberForm.sex" class="field">
                  <option value="">Selectionner</option>
                  <option value="F">F</option>
                  <option value="M">M</option>
                  <option value="Autre">Autre</option>
                </select>
              </label>
            </div>

            <div class="space-y-2">
              <span class="text-sm aurora-subtle">Lier a un autre utilisateur</span>
              <div class="relative">
                <input
                  v-model="profileSearchQuery"
                  class="field"
                  type="text"
                  autocomplete="off"
                  placeholder="Rechercher par nom, username ou email"
                  @focus="profileResultsOpen = true"
                />
                <div v-if="profileSearchPending" class="mt-2 text-xs aurora-muted">Recherche...</div>
                <div
                  v-if="profileResultsOpen && profileSearchResults.length"
                  class="absolute z-20 mt-2 max-h-64 w-full overflow-auto rounded-3xl border border-white/10 bg-[color:var(--app-bg-base)]/95 p-2 shadow-2xl backdrop-blur"
                >
                  <button
                    v-for="profile in profileSearchResults"
                    :key="profile.id"
                    class="flex w-full items-start justify-between gap-3 rounded-2xl px-3 py-3 text-left transition hover:bg-white/5"
                    type="button"
                    @click="selectLinkedProfile(profile)"
                  >
                    <div>
                      <p class="font-medium text-stone-100">{{ profile.display_name }}</p>
                      <p class="text-xs aurora-subtle">{{ profile.email || "Aucun email" }}</p>
                    </div>
                    <span class="glass-pill">Lier</span>
                  </button>
                </div>
              </div>
              <div v-if="selectedLinkedProfile" class="glass-card flex items-center justify-between gap-3 p-4">
                <div>
                  <p class="text-sm font-semibold text-stone-100">{{ selectedLinkedProfile.display_name }}</p>
                  <p class="text-xs aurora-subtle">{{ selectedLinkedProfile.email || selectedLinkedProfile.username }}</p>
                </div>
                <button class="btn-secondary px-3 py-2 text-sm" type="button" @click="clearLinkedProfile">Retirer le lien</button>
              </div>
            </div>

            <div class="flex flex-wrap gap-3">
              <button class="btn-primary" :disabled="memberPending" type="submit">
                <span>{{ memberPending ? "Enregistrement..." : "Ajouter le membre" }}</span>
              </button>
            </div>
          </form>
        </article>
      </div>

      <div
        v-if="showMealModal"
        class="shared-meal-modal-overlay"
        @click.self="closeMealModal"
      >
        <article class="shared-meal-modal-panel max-h-[90vh] w-full max-w-5xl overflow-y-auto p-5">
        <div class="flex items-center justify-between gap-3">
          <div>
            <p class="text-xs uppercase tracking-[0.24em] aurora-muted">Nouveau repas</p>
            <h3 class="mt-2 text-lg font-semibold">Creer un repas collectif</h3>
          </div>
          <button class="btn-secondary px-3 py-2 text-sm" type="button" @click="closeMealModal">Fermer</button>
        </div>

        <form class="mt-5 space-y-5" @submit.prevent="createMeal">
          <div class="grid gap-4 md:grid-cols-2">
            <label class="space-y-2 md:col-span-2">
              <span class="text-sm aurora-subtle">Titre</span>
              <input v-model="mealForm.title" class="field" type="text" placeholder="Ex: Riz au poulet" />
            </label>
            <label class="space-y-2">
              <span class="text-sm aurora-subtle">Date et heure</span>
              <input v-model="mealForm.eaten_at" class="field" type="datetime-local" />
            </label>
            <label class="space-y-2">
              <span class="text-sm aurora-subtle">Type de repas</span>
              <select v-model="mealForm.source_type" class="field">
                <option value="home_cooked">Cuisine maison</option>
                <option value="bought">Repas achete</option>
                <option value="restaurant">Restaurant</option>
              </select>
            </label>
            <label class="space-y-2">
              <span class="text-sm aurora-subtle">Portions preparees</span>
              <input
                v-model="mealForm.total_servings"
                class="field"
                :placeholder="mealNeedsShopping ? 'Ex: 4 portions cuisinees' : 'Ex: 2 portions achetees'"
                type="number"
                min="0.25"
                step="0.25"
              />
            </label>
            <label class="space-y-2 md:col-span-2">
              <span class="text-sm aurora-subtle">Notes</span>
              <textarea v-model="mealForm.notes" class="field min-h-[100px]" placeholder="Ex: tout le monde a mange le meme plat, enfant plus petite portion" />
            </label>
          </div>

          <div class="rounded-2xl border border-white/10 bg-white/5 px-4 py-3 text-sm aurora-subtle">
            <template v-if="mealNeedsShopping">
              Ce repas est cuisine par toi: les quantites servent aussi pour les courses.
            </template>
            <template v-else>
              Ce repas n'alimente pas les courses. Renseigne quand meme les ingredients estimes pour garder une analyse nutritionnelle correcte.
            </template>
          </div>

          <div class="space-y-3">
            <div class="flex items-center justify-between gap-3">
              <h4 class="text-sm font-semibold uppercase tracking-[0.22em] aurora-muted">Ingredients</h4>
              <button class="btn-secondary px-3 py-2 text-sm" type="button" @click="addIngredientRow">Ajouter une ligne</button>
            </div>

            <div v-for="(ingredientRow, index) in mealForm.ingredients" :key="ingredientRow.key" class="rounded-3xl border border-white/10 bg-white/5 p-4">
              <div class="grid gap-4 md:grid-cols-[1.4fr_0.7fr_0.6fr_auto]">
                <label class="space-y-2">
                  <span class="text-sm aurora-subtle">Ingredient</span>
                  <select v-model.number="ingredientRow.ingredient" class="field">
                    <option :value="0">Selectionner</option>
                    <optgroup v-for="group in groupedIngredientOptions" :key="group.category" :label="group.category">
                      <option v-for="ingredient in group.items" :key="ingredient.id" :value="ingredient.id">
                        {{ ingredient.icon || "•" }} {{ ingredient.name }}
                      </option>
                    </optgroup>
                  </select>
                </label>
                <label class="space-y-2">
                  <span class="text-sm aurora-subtle">Quantite totale</span>
                  <input v-model="ingredientRow.quantity" class="field" type="number" min="0.01" step="0.01" />
                </label>
                <label class="space-y-2">
                  <span class="text-sm aurora-subtle">Unite</span>
                  <select v-model="ingredientRow.unit" class="field">
                    <option value="g">g</option>
                    <option value="kg">kg</option>
                  </select>
                </label>
                <div class="flex items-end">
                  <button class="btn-secondary px-3 py-3 text-sm" type="button" @click="removeIngredientRow(index)">Retirer</button>
                </div>
              </div>
            </div>

            <div class="rounded-3xl border border-dashed border-white/10 p-4">
              <div class="grid gap-3 md:grid-cols-[1.2fr_0.7fr_0.6fr_auto]">
                <input v-model="quickIngredient.name" class="field" type="text" placeholder="Nouvel ingredient" />
                <input v-model="quickIngredient.kcal_per_100g" class="field" type="number" min="0" step="0.01" placeholder="kcal/100g" />
                <select v-model="quickIngredient.default_unit" class="field">
                  <option value="g">g</option>
                  <option value="kg">kg</option>
                </select>
                <button class="btn-secondary" :disabled="ingredientPending" type="button" @click="createIngredient">Creer</button>
              </div>
            </div>
          </div>

          <div class="space-y-3">
            <div class="flex items-center justify-between gap-3">
              <h4 class="text-sm font-semibold uppercase tracking-[0.22em] aurora-muted">Participants</h4>
              <button class="btn-secondary px-3 py-2 text-sm" type="button" @click="addParticipantRow">Ajouter une ligne</button>
            </div>

            <div v-for="(participantRow, index) in mealForm.participants" :key="participantRow.key" class="rounded-3xl border border-white/10 bg-white/5 p-4">
              <div class="grid gap-4 md:grid-cols-[0.8fr_1.2fr_0.7fr_auto]">
                <label class="space-y-2">
                  <span class="text-sm aurora-subtle">Type</span>
                  <select v-model="participantRow.targetType" class="field">
                    <option value="self">Moi</option>
                    <option value="household">Membre du foyer</option>
                  </select>
                </label>
                <label class="space-y-2">
                  <span class="text-sm aurora-subtle">Participant</span>
                  <select v-model.number="participantRow.household_member" class="field" :disabled="participantRow.targetType !== 'household'">
                    <option :value="0">Selectionner</option>
                    <option v-for="member in householdMembers" :key="member.id" :value="member.id">
                      {{ member.name }}{{ member.linked_profile_display_name ? ` Â· ${member.linked_profile_display_name}` : "" }}
                    </option>
                  </select>
                </label>
                <label class="space-y-2">
                  <span class="text-sm aurora-subtle">Portions mangees</span>
                  <input v-model="participantRow.servings_eaten" class="field" type="number" min="0.25" step="0.25" />
                </label>
                <div class="flex items-end">
                  <button class="btn-secondary px-3 py-3 text-sm" type="button" @click="removeParticipantRow(index)">Retirer</button>
                </div>
              </div>
            </div>
          </div>

          <div class="flex flex-wrap gap-3">
            <button class="btn-primary" :disabled="mealPending" type="submit">
              <span>{{ mealPending ? "Enregistrement..." : "Creer le repas" }}</span>
            </button>
            <button class="btn-secondary" type="button" @click="resetMealForm">Reinitialiser</button>
          </div>
        </form>
        </article>
      </div>
    </Teleport>
  </section>
</template>

<script setup lang="ts">
type ProfileLookup = {
  id: number
  username: string
  email: string
  first_name: string
  last_name: string
  display_name: string
}

type HouseholdMember = {
  id: number
  name: string
  relationship: string
  age: number | null
  sex: string
  linked_profile: number | null
  linked_profile_display_name?: string
}

type IngredientOption = {
  id: number
  name: string
  category: string
  icon: string
  default_unit: string
  kcal_per_100g: string | null
}

type PaginatedResponse<T> = {
  results?: T[]
}

type MealRead = {
  id: number
  title: string
  eaten_at: string
  source_type: "home_cooked" | "bought" | "restaurant"
  source_type_label?: string
  total_servings: string
  notes: string
  created_by?: { user?: { username?: string } }
  ingredients: Array<{
    id: number
    quantity: string
    unit: string
    ingredient?: { name?: string }
  }>
  participants: Array<{
    id: number
    participant_name: string
    servings_eaten: string
    nutrition_totals?: {
      kcal?: string
    }
  }>
}

const { request } = useApi()
const props = withDefaults(defineProps<{
  mode?: "full" | "profile"
}>(), {
  mode: "full",
})

const feedback = ref("")
const errorMessage = ref("")
const meals = ref<MealRead[]>([])
const ingredientOptions = ref<IngredientOption[]>([])
const householdMembers = ref<HouseholdMember[]>([])
const profileSearchResults = ref<ProfileLookup[]>([])
const profileSearchQuery = ref("")
const profileSearchPending = ref(false)
const profileResultsOpen = ref(false)
const selectedLinkedProfile = ref<ProfileLookup | null>(null)
const memberPending = ref(false)
const ingredientPending = ref(false)
const mealPending = ref(false)
const selfProfileId = ref<number | null>(null)
const showMemberModal = ref(false)
const showMealModal = ref(false)
const showMealComposer = computed(() => props.mode === "full")
const showInlineMemberForm = computed(() => props.mode === "profile")
const showInlineMealForm = computed(() => props.mode === "profile" && showMealComposer.value)
const showHouseholdMemberModalTrigger = computed(() => props.mode === "full")
const showMealModalTrigger = computed(() => props.mode === "full" && showMealComposer.value)
const containerClass = computed(() => props.mode === "full" ? "panel p-6 md:p-8" : "rounded-[30px] border border-white/10 bg-white/5 p-5")
const contentClass = computed(() => props.mode === "full" ? "mt-6 grid gap-6 xl:grid-cols-[0.92fr_1.08fr]" : "mt-6")
const heroKicker = computed(() => props.mode === "full" ? "Repas partages" : "Foyer")
const heroTitle = computed(() => props.mode === "full"
  ? "Cuisine pour la famille, analyse par personne"
  : "Famille et participants de repas")
const heroCopy = computed(() => props.mode === "full"
  ? "Les quantites restent totales pour les courses et la preparation. Un repas peut aussi etre achete ou pris au restaurant: pas de courses a faire, mais les ingredients restent suivis pour l'analyse nutritionnelle."
  : "Definis ici les personnes de ton foyer et lie-les a un autre compte si elles doivent recevoir automatiquement les repas partages.")

const memberForm = reactive({
  name: "",
  relationship: "",
  age: null as number | null,
  sex: "",
})

const quickIngredient = reactive({
  name: "",
  default_unit: "g",
  kcal_per_100g: "",
})

const ingredientCategoryOrder = [
  "Proteines",
  "Viandes",
  "Poissons",
  "Oeufs",
  "Legumineuses",
  "Feculents",
  "Cereales",
  "Legumes",
  "Fruits",
  "Produits laitiers",
  "Matieres grasses",
  "Epices",
  "Condiments",
  "Boissons",
  "Sans categorie",
]

function normalizeCategoryLabel(value: string) {
  return value
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .trim()
    .toLowerCase()
}

const ingredientCategoryRank = new Map(
  ingredientCategoryOrder.map((category, index) => [normalizeCategoryLabel(category), index]),
)

const groupedIngredientOptions = computed(() => {
  const groups = new Map<string, IngredientOption[]>()
  for (const ingredient of ingredientOptions.value) {
    const key = ingredient.category || "Sans categorie"
    if (!groups.has(key)) {
      groups.set(key, [])
    }
    groups.get(key)!.push(ingredient)
  }
  return Array.from(groups.entries())
    .map(([category, items]) => ({
      category,
      items: [...items].sort((a, b) => a.name.localeCompare(b.name, "fr")),
    }))
    .sort((a, b) => {
      const rankA = ingredientCategoryRank.get(normalizeCategoryLabel(a.category))
      const rankB = ingredientCategoryRank.get(normalizeCategoryLabel(b.category))
      if (rankA !== undefined || rankB !== undefined) {
        return (rankA ?? Number.MAX_SAFE_INTEGER) - (rankB ?? Number.MAX_SAFE_INTEGER)
      }
      return a.category.localeCompare(b.category, "fr")
    })
})

type IngredientRow = {
  key: string
  ingredient: number
  quantity: string
  unit: string
}

type ParticipantRow = {
  key: string
  targetType: "self" | "household"
  household_member: number
  servings_eaten: string
}

const mealForm = reactive({
  title: "",
  eaten_at: toDateTimeLocal(new Date()),
  source_type: "home_cooked" as "home_cooked" | "bought" | "restaurant",
  total_servings: "1.00",
  notes: "",
  ingredients: [newIngredientRow()],
  participants: [newSelfParticipantRow()],
})

function newIngredientRow(): IngredientRow {
  return {
    key: crypto.randomUUID(),
    ingredient: 0,
    quantity: "100",
    unit: "g",
  }
}

function newSelfParticipantRow(): ParticipantRow {
  return {
    key: crypto.randomUUID(),
    targetType: "self",
    household_member: 0,
    servings_eaten: "1.00",
  }
}

function newHouseholdParticipantRow(): ParticipantRow {
  return {
    key: crypto.randomUUID(),
    targetType: "household",
    household_member: 0,
    servings_eaten: "1.00",
  }
}

function resetMealForm() {
  mealForm.title = ""
  mealForm.eaten_at = toDateTimeLocal(new Date())
  mealForm.source_type = "home_cooked"
  mealForm.total_servings = "1.00"
  mealForm.notes = ""
  mealForm.ingredients = [newIngredientRow()]
  mealForm.participants = [newSelfParticipantRow()]
}

const mealNeedsShopping = computed(() => mealForm.source_type === "home_cooked")

function addIngredientRow() {
  mealForm.ingredients.push(newIngredientRow())
}

function removeIngredientRow(index: number) {
  if (mealForm.ingredients.length === 1) {
    mealForm.ingredients.splice(0, 1, newIngredientRow())
    return
  }
  mealForm.ingredients.splice(index, 1)
}

function addParticipantRow() {
  mealForm.participants.push(newHouseholdParticipantRow())
}

function removeParticipantRow(index: number) {
  if (mealForm.participants.length === 1) {
    mealForm.participants.splice(0, 1, newSelfParticipantRow())
    return
  }
  mealForm.participants.splice(index, 1)
}

function participantSelected(memberId: number) {
  return mealForm.participants.some((participant) => participant.targetType === "household" && participant.household_member === memberId)
}

function toggleParticipantSelection(memberId: number) {
  const existingIndex = mealForm.participants.findIndex((participant) => participant.targetType === "household" && participant.household_member === memberId)
  if (existingIndex >= 0) {
    removeParticipantRow(existingIndex)
    return
  }
  const row = newHouseholdParticipantRow()
  row.household_member = memberId
  mealForm.participants.push(row)
}

function clearLinkedProfile() {
  selectedLinkedProfile.value = null
  profileSearchQuery.value = ""
  profileSearchResults.value = []
}

function openMemberModal() {
  showMemberModal.value = true
}

function closeMemberModal() {
  showMemberModal.value = false
  profileResultsOpen.value = false
}

function openMealModal() {
  showMealModal.value = true
}

function closeMealModal() {
  showMealModal.value = false
}

function selectLinkedProfile(profile: ProfileLookup) {
  selectedLinkedProfile.value = profile
  profileSearchQuery.value = profile.display_name
  profileResultsOpen.value = false
}

function cleanNumber(value: string) {
  return value.trim().replace(",", ".")
}

function formatMealDate(value: string) {
  return new Intl.DateTimeFormat("fr-FR", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value))
}

function formatNutrition(value?: string) {
  return new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 0 }).format(Number(value || 0))
}

function mealSourceTone(sourceType?: string) {
  if (sourceType === "restaurant") return "border-amber-300/30 bg-amber-300/10 text-amber-50"
  if (sourceType === "bought") return "border-cyan-300/30 bg-cyan-300/10 text-cyan-50"
  return "border-emerald-300/30 bg-emerald-300/10 text-emerald-50"
}

function toDateTimeLocal(date: Date) {
  const local = new Date(date.getTime() - (date.getTimezoneOffset() * 60000))
  return local.toISOString().slice(0, 16)
}

function extractErrorMessage(error: any, fallback: string) {
  const payload = error?.data || error?.response?._data || null
  if (payload?.detail) {
    return payload.detail
  }
  if (payload && typeof payload === "object") {
    return Object.entries(payload)
      .map(([key, value]) => `${key}: ${Array.isArray(value) ? value.join(", ") : value}`)
      .join(" | ")
  }
  return error?.message || fallback
}

function unwrapList<T>(payload: T[] | PaginatedResponse<T>) {
  return Array.isArray(payload) ? payload : (payload.results || [])
}

async function loadSelfProfile() {
  const profile = await request<{ id: number }>("/auth/profile/me/", { method: "GET" })
  selfProfileId.value = profile.id
}

async function loadHouseholdMembers() {
  const response = await request<HouseholdMember[] | PaginatedResponse<HouseholdMember>>("/auth/household-members/", { method: "GET" })
  householdMembers.value = unwrapList(response)
}

async function loadIngredients() {
  const response = await request<IngredientOption[] | PaginatedResponse<IngredientOption>>("/auth/ingredients/", { method: "GET" })
  ingredientOptions.value = unwrapList(response)
}

async function loadMeals() {
  const response = await request<MealRead[] | PaginatedResponse<MealRead>>("/auth/meals/", { method: "GET" })
  meals.value = unwrapList(response)
}

async function createHouseholdMember() {
  if (!memberForm.name.trim()) {
    errorMessage.value = "Le nom du membre est requis."
    return
  }
  memberPending.value = true
  feedback.value = ""
  errorMessage.value = ""
  try {
    await request("/auth/household-members/", {
      method: "POST",
      body: {
        name: memberForm.name.trim(),
        relationship: memberForm.relationship.trim(),
        age: memberForm.age || null,
        sex: memberForm.sex,
        linked_profile: selectedLinkedProfile.value?.id || null,
      },
    })
    memberForm.name = ""
    memberForm.relationship = ""
    memberForm.age = null
    memberForm.sex = ""
    clearLinkedProfile()
    await loadHouseholdMembers()
    feedback.value = "Membre du foyer ajoute."
    if (props.mode === "full") {
      closeMemberModal()
    }
  } catch (error: any) {
    errorMessage.value = extractErrorMessage(error, "Impossible d'ajouter ce membre.")
  } finally {
    memberPending.value = false
  }
}

async function createIngredient() {
  if (!quickIngredient.name.trim()) {
    errorMessage.value = "Le nom de l'ingredient est requis."
    return
  }
  ingredientPending.value = true
  feedback.value = ""
  errorMessage.value = ""
  try {
    const ingredient = await request<IngredientOption>("/auth/ingredients/", {
      method: "POST",
      body: {
        name: quickIngredient.name.trim(),
        default_unit: quickIngredient.default_unit,
        kcal_per_100g: quickIngredient.kcal_per_100g ? cleanNumber(quickIngredient.kcal_per_100g) : null,
      },
    })
    quickIngredient.name = ""
    quickIngredient.default_unit = "g"
    quickIngredient.kcal_per_100g = ""
    await loadIngredients()
    const lastRow = mealForm.ingredients[mealForm.ingredients.length - 1]
    if (lastRow && !lastRow.ingredient) {
      lastRow.ingredient = ingredient.id
      lastRow.unit = ingredient.default_unit || "g"
    }
    feedback.value = "Ingredient ajoute."
  } catch (error: any) {
    errorMessage.value = extractErrorMessage(error, "Impossible de creer cet ingredient.")
  } finally {
    ingredientPending.value = false
  }
}

async function createMeal() {
  if (!mealForm.title.trim()) {
    errorMessage.value = "Le titre du repas est requis."
    return
  }
  const ingredients = mealForm.ingredients
    .filter((ingredient) => ingredient.ingredient && ingredient.quantity)
    .map((ingredient) => ({
      ingredient: ingredient.ingredient,
      quantity: cleanNumber(ingredient.quantity),
      unit: ingredient.unit,
    }))

  const participants = mealForm.participants.map((participant) => {
    if (participant.targetType === "self") {
      return {
        profile: selfProfileId.value,
        servings_eaten: cleanNumber(participant.servings_eaten),
      }
    }
    return {
      household_member: participant.household_member,
      servings_eaten: cleanNumber(participant.servings_eaten),
    }
  }).filter((participant) => participant.servings_eaten)

  if (!ingredients.length) {
    errorMessage.value = "Ajoute au moins un ingredient."
    return
  }
  if (!participants.length) {
    errorMessage.value = "Ajoute au moins un participant."
    return
  }

  mealPending.value = true
  feedback.value = ""
  errorMessage.value = ""
  try {
    await request("/auth/meals/", {
      method: "POST",
      body: {
        title: mealForm.title.trim(),
        eaten_at: new Date(mealForm.eaten_at).toISOString(),
        source_type: mealForm.source_type,
        total_servings: cleanNumber(mealForm.total_servings),
        notes: mealForm.notes.trim(),
        shopping_done_by: mealNeedsShopping.value ? selfProfileId.value : null,
        cooked_by: mealNeedsShopping.value ? selfProfileId.value : null,
        ingredients,
        participants,
      },
    })
    resetMealForm()
    await loadMeals()
    feedback.value = "Repas partage cree."
    if (props.mode === "full") {
      closeMealModal()
    }
  } catch (error: any) {
    errorMessage.value = extractErrorMessage(error, "Impossible de creer ce repas.")
  } finally {
    mealPending.value = false
  }
}

watch(profileSearchQuery, async (value) => {
  const query = value.trim()
  if (!query || selectedLinkedProfile.value?.display_name === query) {
    profileSearchResults.value = []
    return
  }
  profileSearchPending.value = true
  try {
    const response = await request<ProfileLookup[] | PaginatedResponse<ProfileLookup>>("/auth/profiles/search/", {
      method: "GET",
      query: { q: query },
    })
    profileSearchResults.value = unwrapList(response)
  } catch {
    profileSearchResults.value = []
  } finally {
    profileSearchPending.value = false
  }
})

watch(householdMembers, (members) => {
  for (const participant of mealForm.participants) {
    if (participant.targetType === "household" && participant.household_member) {
      const exists = members.some((member) => member.id === participant.household_member)
      if (!exists) {
        participant.household_member = 0
      }
    }
  }
})

await Promise.all([
  loadSelfProfile(),
  loadIngredients(),
  loadMeals(),
  loadHouseholdMembers(),
])
</script>

<style scoped>
.shared-meal-modal-overlay {
  position: fixed;
  inset: 0;
  z-index: 200;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 1rem;
  background:
    linear-gradient(180deg, rgba(2, 6, 23, 0.88), rgba(2, 6, 23, 0.8)),
    rgba(15, 23, 42, 0.82);
  backdrop-filter: blur(10px);
}

.shared-meal-modal-panel {
  position: relative;
  z-index: 201;
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 2rem;
  background:
    linear-gradient(180deg, rgba(15, 23, 42, 0.98), rgba(17, 24, 39, 0.96));
  box-shadow: 0 28px 90px rgba(2, 6, 23, 0.55);
}
</style>
