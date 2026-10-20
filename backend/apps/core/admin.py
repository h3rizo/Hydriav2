from django.contrib import admin
from apps.core.models import (
    PartnerQuarterlyReportArchive,
    DocumentSource,
    ExtractedDocumentImage,
    DocumentationModule,
    IndicatorDefinition,
    CalculationRule,
    KnownLimitation,
    TestProtocol,
    TestExecution,
    DocumentationChangeLog,
    WidgetAuthToken,
    FiltreSauvegarde,
)

# Legacy models removed - all models migrated to dedicated apps:
# - geography.models for Region, District, Commune, Village
# - organization.models for Organisation, Base


@admin.register(PartnerQuarterlyReportArchive)
class PartnerQuarterlyReportArchiveAdmin(admin.ModelAdmin):
    list_display = (
        'organisation',
        'report_year',
        'report_quarter',
        'scope_level',
        'region',
        'district',
        'commune',
        'is_user_uploaded',
        'uploaded_by',
        'generated_at',
        'is_automatic',
    )
    list_filter = (
        'report_year',
        'report_quarter',
        'scope_level',
        'is_automatic',
        'is_user_uploaded',
        'organisation',
    )
    search_fields = (
        'organisation__nom_organisation',
        'region__nom_region',
        'district__nom_district',
        'commune__nom_commune',
        'scope_key',
    )


@admin.register(DocumentSource)
class DocumentSourceAdmin(admin.ModelAdmin):
    list_display = ('source_file_name', 'file_type', 'status', 'images_count', 'scanned_at')
    list_filter = ('file_type', 'status', 'scanned_at')
    search_fields = ('source_file_name', 'source_file_path', 'relative_path')


@admin.register(ExtractedDocumentImage)
class ExtractedDocumentImageAdmin(admin.ModelAdmin):
    list_display = ('extracted_file_name', 'document_source', 'source_page_number', 'status', 'is_duplicate', 'created_at')
    list_filter = ('status', 'is_duplicate', 'document_source__file_type', 'created_at')
    search_fields = ('extracted_file_name', 'original_internal_name', 'document_source__source_file_name', 'document_source__source_file_path')


class IndicatorDefinitionInline(admin.TabularInline):
    model = IndicatorDefinition
    extra = 0


class CalculationRuleInline(admin.TabularInline):
    model = CalculationRule
    extra = 0


class KnownLimitationInline(admin.TabularInline):
    model = KnownLimitation
    extra = 0


class TestProtocolInline(admin.TabularInline):
    model = TestProtocol
    extra = 0
    fields = ('code', 'test_type', 'status', 'criticality', 'last_executed_at')
    readonly_fields = ('last_executed_at',)


@admin.register(DocumentationModule)
class DocumentationModuleAdmin(admin.ModelAdmin):
    list_display = ('name', 'validation_status', 'is_priority', 'is_active', 'display_order', 'last_reviewed_at')
    list_filter = ('validation_status', 'is_priority', 'is_active')
    search_fields = ('name', 'short_name', 'objective', 'target_audience')
    prepopulated_fields = {'slug': ('name',)}
    inlines = [IndicatorDefinitionInline, CalculationRuleInline, KnownLimitationInline, TestProtocolInline]


@admin.register(IndicatorDefinition)
class IndicatorDefinitionAdmin(admin.ModelAdmin):
    list_display = ('name', 'module', 'refresh_frequency', 'display_order')
    list_filter = ('refresh_frequency', 'module')
    search_fields = ('name', 'objective', 'formula')
    prepopulated_fields = {'slug': ('name',)}


@admin.register(CalculationRule)
class CalculationRuleAdmin(admin.ModelAdmin):
    list_display = ('title', 'module', 'display_order')
    list_filter = ('module',)
    search_fields = ('title', 'description', 'formula')


@admin.register(KnownLimitation)
class KnownLimitationAdmin(admin.ModelAdmin):
    list_display = ('title', 'module', 'severity', 'status', 'display_order')
    list_filter = ('severity', 'status', 'module')
    search_fields = ('title', 'description', 'impact', 'workaround')


class TestExecutionInline(admin.TabularInline):
    model = TestExecution
    extra = 0
    fields = ('executed_at', 'status', 'executed_by_name', 'result_obtained')


@admin.register(TestProtocol)
class TestProtocolAdmin(admin.ModelAdmin):
    list_display = ('code', 'module', 'test_type', 'status', 'criticality', 'last_executed_at')
    list_filter = ('module', 'test_type', 'status', 'criticality')
    search_fields = ('code', 'objective', 'expected_result', 'comment')
    inlines = [TestExecutionInline]


@admin.register(TestExecution)
class TestExecutionAdmin(admin.ModelAdmin):
    list_display = ('protocol', 'executed_at', 'status', 'executed_by_name')
    list_filter = ('status', 'protocol__module', 'protocol__test_type')
    search_fields = ('protocol__code', 'executed_by_name', 'result_obtained', 'comment')


@admin.register(DocumentationChangeLog)
class DocumentationChangeLogAdmin(admin.ModelAdmin):
    list_display = ('title', 'module', 'entry_type', 'happened_on')
    list_filter = ('entry_type', 'module', 'happened_on')
    search_fields = ('title', 'details')


@admin.register(WidgetAuthToken)
class WidgetAuthTokenAdmin(admin.ModelAdmin):
    list_display = ('user', 'scope', 'device_label', 'created_at', 'last_used_at')
    list_filter = ('scope', 'created_at')
    search_fields = ('user__username', 'device_label', 'key')
    readonly_fields = ('key', 'created_at', 'last_used_at')


@admin.register(FiltreSauvegarde)
class FiltreSauvegardeAdmin(admin.ModelAdmin):
    list_display = ('nom', 'page_key', 'cree_par', 'updated_at')
    list_filter = ('page_key',)
    search_fields = ('nom', 'page_key')
