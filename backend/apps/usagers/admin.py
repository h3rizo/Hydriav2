from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html

from .models import (
    AvisRepresentant,
    RepresentantUsager,
    ReseauAvailabilitySlot,
    ReseauMagicLink,
    ReseauMeetingSession,
    ReseauParticipant,
    ReseauParticipantAvailability,
    ReseauMeeting,
    Autorite,
    Reunion,
    ParticipantReunion,
    DecisionReunion,
    PieceJointeReunion,
    PointageReunionDiameX,
)
from .services_reseau import build_absolute_url


@admin.register(RepresentantUsager)
class RepresentantUsagerAdmin(admin.ModelAdmin):
    list_display = ('nom', 'village', 'contact', 'actif')
    list_filter = ('actif',)
    search_fields = ('nom', 'contact', 'village__nom_village')


@admin.register(AvisRepresentant)
class AvisRepresentantAdmin(admin.ModelAdmin):
    list_display = ('representant', 'date_avis', 'employe', 'reunion', 'score_satisfaction')
    list_filter = ('date_avis',)
    search_fields = ('representant__nom', 'remarque')


@admin.register(Autorite)
class AutoriteAdmin(admin.ModelAdmin):
    list_display = ('nom', 'fonction', 'commune', 'contact', 'actif')
    list_filter = ('actif', 'commune')
    search_fields = ('nom', 'fonction', 'contact')


class ParticipantReunionInline(admin.TabularInline):
    model = ParticipantReunion
    extra = 1
    fields = ('type_participant', 'representant', 'point_eau', 'employe', 'autorite', 'nom_libre', 'fonction_libre', 'contact_libre', 'present')


class DecisionReunionInline(admin.TabularInline):
    model = DecisionReunion
    extra = 1
    fields = ('description', 'responsable', 'date_echeance', 'statut', 'date_realisation')


class PieceJointeReunionInline(admin.TabularInline):
    model = PieceJointeReunion
    extra = 1
    fields = ('type_piece', 'fichier', 'legende', 'uploaded_by')


class PointageReunionDiameXInline(admin.TabularInline):
    model = PointageReunionDiameX
    extra = 0
    fields = ('numero_diamex', 'base_diamex', 'date_transaction', 'description', 'compte_code', 'montant', 'pointe_par')
    readonly_fields = ('date_transaction', 'description', 'compte_code', 'montant')


@admin.register(Reunion)
class ReunionAdmin(admin.ModelAdmin):
    list_display = ('objet', 'commune', 'date_reunion', 'organise_par', 'nb_participants', 'nb_decisions_en_cours', 'montant_depense_total')
    list_filter = ('commune', 'date_reunion')
    search_fields = ('objet', 'compte_rendu', 'recommandations', 'commune__nom_commune')
    date_hierarchy = 'date_reunion'
    inlines = [ParticipantReunionInline, DecisionReunionInline, PieceJointeReunionInline, PointageReunionDiameXInline]


@admin.register(DecisionReunion)
class DecisionReunionAdmin(admin.ModelAdmin):
    list_display = ('reunion', 'description', 'responsable', 'date_echeance', 'statut', 'est_en_retard')
    list_filter = ('statut',)
    search_fields = ('description', 'reunion__objet')


@admin.register(PointageReunionDiameX)
class PointageReunionDiameXAdmin(admin.ModelAdmin):
    list_display = ('reunion', 'numero_diamex', 'base_diamex', 'date_transaction', 'montant', 'pointe_par')
    list_filter = ('compte_code',)
    search_fields = ('numero_diamex', 'base_diamex', 'description', 'reunion__objet')


class ReseauParticipantInline(admin.TabularInline):
    model = ReseauParticipant
    extra = 1
    fields = ('nom', 'email', 'telephone', 'organisation', 'google_calendar_email', 'actif')


class ReseauAvailabilitySlotInline(admin.TabularInline):
    model = ReseauAvailabilitySlot
    extra = 1


@admin.register(ReseauMeetingSession)
class ReseauMeetingSessionAdmin(admin.ModelAdmin):
    list_display = ('titre', 'slug', 'statut', 'seuil_confirmation', 'confirmed_slot')
    prepopulated_fields = {'slug': ('titre',)}
    list_filter = ('statut',)
    search_fields = ('titre', 'slug')
    inlines = [ReseauParticipantInline, ReseauAvailabilitySlotInline]


@admin.register(ReseauParticipant)
class ReseauParticipantAdmin(admin.ModelAdmin):
    list_display = ('nom', 'email', 'telephone', 'organisation', 'session', 'actif', 'last_login_at', 'access_link', 'copy_access_link')
    list_filter = ('actif', 'session')
    search_fields = ('nom', 'email', 'telephone', 'organisation')
    readonly_fields = ('access_link_detail', 'copy_access_link_detail')
    fieldsets = (
        (None, {
            'fields': ('session', 'nom', 'email', 'telephone', 'organisation', 'google_calendar_email', 'actif', 'last_login_at')
        }),
        ("Acces", {
            'fields': ('access_link_detail', 'copy_access_link_detail')
        }),
    )

    def access_link(self, obj):
        path = reverse('usagers:reseau_magic_login', kwargs={'token': str(obj.id)})
        url = build_absolute_url(path)
        return format_html('<a href="{}" target="_blank">Ouvrir le lien</a>', url)
    access_link.short_description = "Lien d'acces"

    def access_link_detail(self, obj):
        if not obj.pk:
            return "Enregistrez d'abord le participant."
        path = reverse('usagers:reseau_magic_login', kwargs={'token': str(obj.id)})
        url = build_absolute_url(path)
        return format_html(
            '<div style="max-width:720px;word-break:break-all;">'
            '<a href="{0}" target="_blank">{0}</a>'
            '</div>',
            url,
        )
    access_link_detail.short_description = "URL complete d'acces"

    def copy_access_link(self, obj):
        path = reverse('usagers:reseau_magic_login', kwargs={'token': str(obj.id)})
        url = build_absolute_url(path)
        return format_html(
            '<button type="button" onclick="navigator.clipboard.writeText(\'{}\'); this.innerText=\'Lien copie\';" '
            'style="padding:6px 10px;border-radius:8px;border:1px solid #0ea5e9;background:#e0f2fe;color:#0f172a;cursor:pointer;">'
            'Copier le lien</button>',
            url,
        )
    copy_access_link.short_description = "Copie"

    def copy_access_link_detail(self, obj):
        if not obj.pk:
            return "Enregistrez d'abord le participant."
        return self.copy_access_link(obj)
    copy_access_link_detail.short_description = "Copier le lien d'acces"


@admin.register(ReseauAvailabilitySlot)
class ReseauAvailabilitySlotAdmin(admin.ModelAdmin):
    list_display = ('session', 'start_at', 'end_at', 'is_active')
    list_filter = ('session', 'is_active')


@admin.register(ReseauParticipantAvailability)
class ReseauParticipantAvailabilityAdmin(admin.ModelAdmin):
    list_display = ('participant', 'slot', 'created_at')
    list_filter = ('slot__session',)


@admin.register(ReseauMagicLink)
class ReseauMagicLinkAdmin(admin.ModelAdmin):
    list_display = ('participant', 'expires_at', 'used_at', 'created_at')
    list_filter = ('participant__session',)


@admin.register(ReseauMeeting)
class ReseauMeetingAdmin(admin.ModelAdmin):
    list_display = ('session', 'slot', 'status', 'completed_at')
    list_filter = ('session',)
