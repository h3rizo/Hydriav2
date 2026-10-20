package mg.hydria.app.calculator

import android.content.Context
import android.content.ClipData
import android.content.ClipboardManager
import android.content.Intent
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import android.net.Uri
import android.os.Bundle
import android.text.InputType
import android.view.Gravity
import android.view.HapticFeedbackConstants
import android.view.View
import android.view.inputmethod.InputMethodManager
import android.widget.Button
import android.widget.EditText
import android.widget.FrameLayout
import android.widget.HorizontalScrollView
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.core.widget.doAfterTextChanged
import mg.hydria.app.Tone
import mg.hydria.app.HydriaColors
import mg.hydria.app.HydriaFeedback
import mg.hydria.app.HydriaType
import mg.hydria.app.HydriaUi
import mg.hydria.app.HydriaWindow
import mg.hydria.app.OfflineStore
import mg.hydria.app.R
import mg.hydria.shared.calculator.SalarySimulation
import mg.hydria.shared.calculator.SalaryResult
import mg.hydria.shared.calculator.SalaryConfig
import mg.hydria.shared.calculator.SalaryInput
import mg.hydria.shared.calculator.GpsConversion
import mg.hydria.shared.calculator.GpsCoordinate
import mg.hydria.shared.calculator.ExpressionResult
import mg.hydria.shared.calculator.ExpressionError
import java.math.BigDecimal
import java.text.DecimalFormat
import java.text.DecimalFormatSymbols
import java.text.DateFormat
import java.util.Date
import java.util.Locale
import org.maplibre.android.MapLibre
import org.maplibre.android.camera.CameraUpdateFactory
import org.maplibre.android.geometry.LatLng
import org.maplibre.android.annotations.Marker
import org.maplibre.android.annotations.MarkerOptions
import org.maplibre.android.maps.MapView
import org.maplibre.android.maps.MapLibreMap
import org.maplibre.android.maps.Style

class AdvancedCalculatorActivity : AppCompatActivity() {
    private lateinit var repository: CalculatorRepository
    private lateinit var offlineStore: OfflineStore
    private lateinit var content: FrameLayout
    private lateinit var tabBar: LinearLayout
    private var wideLayout = false
    private var state = CalculatorState()
    private var activeExpressionField: EditText? = null
    private var gpsMapView: MapView? = null
    private var gpsMap: MapLibreMap? = null
    private var gpsMarker: Marker? = null
    private var gpsUsingOfflineStyle = false
    private var activityStarted = false
    private var activityResumed = false
    private var gpsLatitudeField: EditText? = null
    private var gpsLongitudeField: EditText? = null
    private var gpsCombinedView: TextView? = null
    private var phoneGps: mg.hydria.app.navigation.location.TerrainLocationController? = null
    private var phoneGpsStatus: TextView? = null
    private var phoneGpsButton: Button? = null
    private var phoneGpsBest: android.location.Location? = null
    private var phoneGpsStartedAt = 0L
    private val phoneGpsHandler = android.os.Handler(android.os.Looper.getMainLooper())
    private val phoneGpsTimeout = Runnable { finishPhoneGps() }
    private val locationPermission = registerForActivityResult(
        androidx.activity.result.contract.ActivityResultContracts.RequestMultiplePermissions()
    ) { granted ->
        if (granted.values.any { it }) startPhoneGps() else toast(getString(R.string.gps_phone_denied))
    }
    private val totalCriterionViews = mutableMapOf<String, TextView>()
    private val cashCriterionViews = mutableMapOf<String, TextView>()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        HydriaColors.bind(this)
        HydriaType.bind(this)
        offlineStore = OfflineStore(this)
        if (offlineStore.accountKey.isBlank()) {
            Toast.makeText(this, R.string.calculator_session_required, Toast.LENGTH_LONG).show()
            finish()
            return
        }
        repository = CalculatorRepository(offlineStore, offlineStore.accountKey)
        state = repository.load()
        MapLibre.getInstance(applicationContext)
        buildUi()
    }

    private fun buildUi() {
        val root = vertical().apply { setBackgroundColor(HydriaColors.background) }
        root.addView(horizontal(12).apply {
            setBackgroundColor(HydriaColors.backgroundDeep)
            gravity = Gravity.CENTER_VERTICAL
            addView(secondaryButton("←", getString(R.string.calculator_back)) { finish() }, fixed(52, 48))
            addView(vertical().apply {
                addView(label(getString(R.string.calculator_title), 20f, true))
                addView(label(getString(R.string.calculator_offline_ready), 11f, false, HydriaColors.success))
            }, LinearLayout.LayoutParams(0, -2, 1f).apply { marginStart = dp(10) })
            // « Tout effacer » (et non « AC », nom de la touche du pavé qui ne vide que la ligne active) : CALC_VOL-04.
            addView(secondaryButton(getString(R.string.calculator_clear_memory)) { confirmClearMemory() }.apply { textSize = 12f }, fixed(96, 48))
        }, matchWrap())
        wideLayout = HydriaWindow.of(this).isTablet
        content = FrameLayout(this).apply { setBackgroundColor(HydriaColors.background) }
        if (wideLayout) {
            // Tablette : menu d'onglets vertical de 132 dp, plus de bande à faire défiler.
            tabBar = vertical(6).apply { setBackgroundColor(HydriaColors.backgroundDeep) }
            root.addView(horizontal(0).apply {
                addView(tabBar, LinearLayout.LayoutParams(dp(132), LinearLayout.LayoutParams.MATCH_PARENT))
                addView(content, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.MATCH_PARENT, 1f))
            }, LinearLayout.LayoutParams(-1, 0, 1f))
        } else {
            // Pas de marge verticale : les puces (WRAP_CONTENT) sont bornées à la hauteur utile de la
            // bande ; avec 8 dp de marge dans 58 dp elles tombaient à 42 dp, sous les 48 dp tactiles.
            tabBar = horizontal(8).apply { setPadding(dp(8), 0, dp(8), 0) }
            root.addView(HorizontalScrollView(this).apply {
                isHorizontalScrollBarEnabled = false
                setBackgroundColor(HydriaColors.backgroundDeep)
                addView(tabBar, FrameLayout.LayoutParams(FrameLayout.LayoutParams.WRAP_CONTENT, FrameLayout.LayoutParams.MATCH_PARENT))
            }, matchWrap(58))
            root.addView(content, LinearLayout.LayoutParams(-1, 0, 1f))
        }
        setContentView(root)
        renderTabs()
        renderContent()
    }

    private fun renderTabs() {
        tabBar.removeAllViews()
        CalculatorTab.entries.forEach { tab ->
            val chip = HydriaUi.chip(this, getString(tab.labelResource()), state.selectedTab == tab).apply {
                contentDescription = text
                setOnClickListener {
                    state = repository.save(state.copy(selectedTab = tab))
                    renderTabs(); renderContent()
                }
            }
            // Hauteur libre : la puce mesure 48 dp (zone tactile), sa pastille visible 34 dp.
            val params = if (wideLayout) {
                LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT)
            } else {
                LinearLayout.LayoutParams(LinearLayout.LayoutParams.WRAP_CONTENT, LinearLayout.LayoutParams.WRAP_CONTENT).apply { marginEnd = dp(7) }
            }
            tabBar.addView(chip, params)
        }
    }

    private fun renderContent() {
        if (state.selectedTab != CalculatorTab.GPS) { releaseGpsMap(); stopPhoneGps() }
        content.removeAllViews()
        activeExpressionField = null
        when (state.selectedTab) {
            CalculatorTab.CALCULATIONS -> renderCalculations()
            CalculatorTab.SALARY -> renderSalary()
            CalculatorTab.QUOTE -> renderQuote()
            CalculatorTab.TOTAL -> renderTotal()
            CalculatorTab.CASH -> renderCash()
            CalculatorTab.GPS -> renderGps()
        }
    }

    private fun renderSalary() {
        val config = SalaryConfigRepository(offlineStore, offlineStore.accountKey).current()
        val page = vertical(14)
        val notice = offlineStore.salaryConfigNotice
        val statusText = when {
            notice == "formula_incompatible" -> getString(R.string.salary_config_incompatible)
            notice == "checksum_invalid" || notice == "config_incomplete" -> getString(R.string.salary_config_invalid)
            config == null -> getString(R.string.salary_config_required)
            !isOnline() -> getString(R.string.salary_config_offline, config.effectiveFrom, config.version)
            else -> getString(R.string.salary_config_current, config.version, config.effectiveFrom)
        }
        page.addView(HydriaUi.badge(this, statusText, when {
            config == null || notice == "formula_incompatible" -> Tone.WARNING
            notice.isNotBlank() -> Tone.WARNING
            else -> Tone.SUCCESS
        }))
        val scrollBody = vertical(10)
        val draft = state.salaryDraft
        scrollBody.addView(horizontal(8).apply {
            addView(selectionButton(getString(R.string.salary_from_net), draft.basis == SalaryBasis.NET) {
                updateSalaryDraft(draft.copy(basis = SalaryBasis.NET), true)
            }, weighted().apply { marginEnd = dp(4) })
            addView(selectionButton(getString(R.string.salary_from_gross), draft.basis == SalaryBasis.GROSS) {
                updateSalaryDraft(draft.copy(basis = SalaryBasis.GROSS), true)
            }, weighted().apply { marginStart = dp(4) })
        }, matchWrap(52, top = 8))
        scrollBody.addView(HorizontalScrollView(this).apply {
            isHorizontalScrollBarEnabled = false
            addView(horizontal(6).apply {
                SalaryMode.entries.forEach { mode ->
                    addView(selectionButton(getString(mode.labelResource()), draft.mode == mode) {
                        updateSalaryDraft(state.salaryDraft.copy(mode = mode), true)
                    }, LinearLayout.LayoutParams(dp(145), dp(48)).apply { marginEnd = dp(6) })
                }
            })
        }, matchWrap(54, top = 8))
        val results = vertical(10)
        fun invalidate() { results.removeAllViews() }
        scrollBody.addView(salaryTextField(
            getString(if (draft.basis == SalaryBasis.NET) R.string.salary_target_net else R.string.salary_target_gross),
            draft.target,
        ) { updateSalaryDraft(state.salaryDraft.copy(target = it)); invalidate() }, matchWrap(52, top = 8))
        scrollBody.addView(salaryIntegerField(getString(R.string.salary_dependents), draft.dependents) {
            updateSalaryDraft(state.salaryDraft.copy(dependents = it)); invalidate()
        }, matchWrap(52, top = 8))
        if (draft.mode == SalaryMode.PRORATA || draft.mode == SalaryMode.DAILY) {
            scrollBody.addView(salaryIntegerField(getString(if (draft.mode == SalaryMode.PRORATA) R.string.salary_days_presence else R.string.salary_days_worked), draft.days) {
                updateSalaryDraft(state.salaryDraft.copy(days = it)); invalidate()
            }, matchWrap(52, top = 8))
        }
        if (draft.mode == SalaryMode.GUARDIAN && config != null) addGuardianFields(scrollBody, config, results)
        scrollBody.addView(primaryButton(getString(R.string.salary_simulate)) {
            if (config == null) toast(getString(R.string.salary_config_required)) else simulateSalary(config, results)
        }, matchWrap(54, top = 10))
        scrollBody.addView(results, matchWrap(top = 10))
        page.addView(ScrollView(this).apply { addView(scrollBody) }, LinearLayout.LayoutParams(-1, 0, 1f).apply { topMargin = dp(8) })
        content.addView(page, FrameLayout.LayoutParams(-1, -1))
    }

    private fun addGuardianFields(parent: LinearLayout, config: SalaryConfig, results: LinearLayout) {
        val p = config.parameters
        fun percent(value: BigDecimal) = formatDecimal(value.multiply(BigDecimal("100")))
        val fields = listOf(
            Triple(R.string.salary_night_hours, percent(p.nightRate), state.salaryDraft.nightHours),
            Triple(R.string.salary_sunday_hours, percent(p.sundayRate), state.salaryDraft.sundayHours),
            Triple(R.string.salary_holiday_hours, percent(p.officialHolidayRate), state.salaryDraft.officialHolidayHours),
            Triple(R.string.salary_decree_hours, percent(p.decreePaidHolidayRate), state.salaryDraft.decreePaidHolidayHours),
            Triple(R.string.salary_may_first_hours, percent(p.mayFirstRate), state.salaryDraft.mayFirstHours),
            Triple(R.string.salary_replacement_hours, percent(p.guardianReplacementRate), state.salaryDraft.replacementHours),
            Triple(R.string.salary_ordinary_replacement_hours, percent(p.guardianOrdinaryReplacementExtraRate), state.salaryDraft.ordinaryReplacementHours),
        )
        fields.forEachIndexed { index, (resource, rate, value) ->
            parent.addView(salaryTextField(getString(resource, rate), value) { updated ->
                val current = state.salaryDraft
                val next = when (index) {
                    0 -> current.copy(nightHours = updated)
                    1 -> current.copy(sundayHours = updated)
                    2 -> current.copy(officialHolidayHours = updated)
                    3 -> current.copy(decreePaidHolidayHours = updated)
                    4 -> current.copy(mayFirstHours = updated)
                    5 -> current.copy(replacementHours = updated)
                    else -> current.copy(ordinaryReplacementHours = updated)
                }
                updateSalaryDraft(next); results.removeAllViews()
            }, matchWrap(52, top = 8))
        }
    }

    private fun simulateSalary(config: SalaryConfig, container: LinearLayout) {
        val draft = state.salaryDraft
        fun decimal(value: String) = DecimalInput.parse(value)
        val target = decimal(draft.target)
        val dependents = draft.dependents.trim().toIntOrNull()
        val days = draft.days.trim().toIntOrNull() ?: 0
        val hours = listOf(draft.nightHours, draft.sundayHours, draft.officialHolidayHours, draft.decreePaidHolidayHours,
            draft.mayFirstHours, draft.replacementHours, draft.ordinaryReplacementHours).map(::decimal)
        val earlyError = when {
            target == null || target <= BigDecimal.ZERO -> SalaryInputError.TARGET
            dependents == null || dependents < 0 -> SalaryInputError.DEPENDENTS
            hours.any { it == null } -> SalaryInputError.HOURS
            else -> null
        }
        val simulation = if (earlyError != null) SalarySimulation.Invalid(earlyError) else SalaryEngine(config).simulate(SalaryInput(
            basis = draft.basis, target = target!!, dependents = dependents!!, mode = draft.mode, days = days,
            nightHours = hours[0]!!, sundayHours = hours[1]!!, officialHolidayHours = hours[2]!!,
            decreePaidHolidayHours = hours[3]!!, mayFirstHours = hours[4]!!, replacementHours = hours[5]!!,
            ordinaryReplacementHours = hours[6]!!,
        ))
        container.removeAllViews()
        when (val res = simulation) {
            is SalarySimulation.Invalid -> container.addView(label(getString(res.error.messageResource()), 14f, true, HydriaColors.error))
            is SalarySimulation.Success -> renderSalaryResult(container, res.result, config)
        }
    }

    private fun renderSalaryResult(parent: LinearLayout, result: SalaryResult, config: SalaryConfig) {
        parent.addView(label(getString(R.string.salary_results), 22f, true))
        listOf(
            R.string.salary_base_gross to result.baseGross,
            R.string.salary_total_gross to result.totalGross,
            R.string.salary_net_obtained to result.netRounded,
            R.string.salary_net_difference to result.netDifference,
            R.string.salary_cnaps_base to result.cnapsBase,
            R.string.salary_cnaps to result.employeeCnaps,
            R.string.salary_mutual to result.healthMutual,
            R.string.salary_taxable_base to result.taxableBase,
            R.string.salary_tax_deduction to result.taxDeduction,
            R.string.salary_irsa to result.irsa,
            R.string.salary_majoration_night to result.majorations.night,
            R.string.salary_majoration_sunday to result.majorations.sunday,
            R.string.salary_majoration_holiday to result.majorations.officialHoliday,
            R.string.salary_majoration_decree to result.majorations.decreePaidHoliday,
            R.string.salary_majoration_may to result.majorations.mayFirst,
            R.string.salary_majoration_replacement to result.majorations.replacement,
        ).forEach { (resource, amount) -> parent.addView(moneyRow(getString(resource), amount), matchWrap(top = 6)) }
        val p = config.parameters
        parent.addView(label(getString(R.string.salary_assumptions, formatMoney(p.minimumSalary), formatDecimal(p.cnapsCeilingMultiplier),
            formatMoney(p.dependentIrsaDeduction), formatMoney(p.minimumIrsa)), 12f, false, HydriaColors.textSecondary), matchWrap(top = 10))
        parent.addView(label(getString(R.string.salary_irsa_brackets), 18f, true), matchWrap(top = 12))
        result.brackets.forEach { bracket ->
            parent.addView(label(getString(R.string.salary_bracket, bracket.order, formatMoney(bracket.lowerBound),
                formatMoney(bracket.upperBound), formatDecimal(bracket.ratePercent), formatMoney(bracket.taxableAmount),
                formatMoney(bracket.tax)), 12f, false, HydriaColors.textSecondary), matchWrap(top = 6))
        }
    }

    private fun moneyRow(title: String, amount: BigDecimal): View = horizontal(10).apply {
        HydriaUi.card(this)
        addView(label(title, 13f, false, HydriaColors.textSecondary), LinearLayout.LayoutParams(0, -2, 1f))
        addView(label(getString(R.string.calculator_amount_ariary, formatMoney(amount)), 15f, true,
            if (amount.signum() < 0) HydriaColors.error else HydriaColors.text))
    }

    private fun salaryTextField(hintValue: String, value: String, changed: (String) -> Unit): EditText =
        decimalInput(hintValue, value).apply { doAfterTextChanged { changed(it?.toString().orEmpty()) } }

    private fun salaryIntegerField(hintValue: String, value: String, changed: (String) -> Unit): EditText =
        input(hintValue).apply {
            inputType = InputType.TYPE_CLASS_NUMBER or InputType.TYPE_NUMBER_FLAG_SIGNED
            setText(value); doAfterTextChanged { changed(it?.toString().orEmpty()) }
        }

    private fun updateSalaryDraft(draft: SalaryDraft, rerender: Boolean = false) {
        state = repository.save(state.copy(salaryDraft = draft))
        if (rerender) renderContent()
    }

    private fun selectionButton(value: String, selected: Boolean, action: () -> Unit): Button = Button(this).apply {
        text = value; HydriaUi.styleSecondary(this, selected); setOnClickListener { action() }
    }

    private fun isOnline(): Boolean {
        val manager = getSystemService(Context.CONNECTIVITY_SERVICE) as ConnectivityManager
        val network = manager.activeNetwork ?: return false
        return manager.getNetworkCapabilities(network)?.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET) == true
    }

    private fun renderCalculations() {
        val page = vertical(14)
        page.addView(horizontal().apply {
            addView(HydriaUi.badge(this@AdvancedCalculatorActivity,
                resources.getQuantityString(R.plurals.calculator_saved_lines, state.calculationLines.size, state.calculationLines.size), Tone.INFO))
            addView(HydriaUi.badge(this@AdvancedCalculatorActivity,
                getString(R.string.calculator_active_line, state.activeCalculationLine + 1), Tone.SUCCESS),
                LinearLayout.LayoutParams(-2, -2).apply { marginStart = dp(8) })
        })
        page.addView(horizontal().apply {
            addView(primaryButton(getString(R.string.calculator_add_line)) { addLine() }, weighted().apply { marginEnd = dp(4) })
            addView(secondaryButton(getString(R.string.calculator_recalculate)) { recalculate() }, weighted().apply { marginStart = dp(4); marginEnd = dp(4) })
            addView(secondaryButton(getString(R.string.calculator_clear_calculations)) { confirmClearCalculations() }, weighted().apply { marginStart = dp(4) })
        }, matchWrap(52, top = 10))
        val lines = vertical(10)
        if (wideLayout) lines.addView(calculationTableHeader(), matchWrap(top = 4))
        state.calculationLines.forEachIndexed { index, line ->
            lines.addView(
                if (wideLayout) calculationTableRow(index, line) else calculationCard(index, line),
                if (wideLayout) matchWrap(top = 6) else matchWrap(),
            )
        }
        val linesScroll = ScrollView(this).apply { addView(lines) }
        if (wideLayout) {
            // Pavé fixe à droite (392 dp), surmonté des jetons de référence : la liste ne bouge pas.
            page.addView(horizontal(0).apply {
                addView(linesScroll, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.MATCH_PARENT, 1f))
                addView(vertical(0).apply {
                    addView(referenceStrip(), matchWrap(48))
                    addView(keypad(), matchWrap(top = 8))
                }, LinearLayout.LayoutParams(dp(392), LinearLayout.LayoutParams.MATCH_PARENT).apply { marginStart = dp(12) })
            }, LinearLayout.LayoutParams(-1, 0, 1f).apply { topMargin = dp(10) })
        } else {
            page.addView(linesScroll, LinearLayout.LayoutParams(-1, 0, 1f).apply { topMargin = dp(10) })
            page.addView(referenceStrip(), matchWrap(48, top = 8))
            page.addView(keypad(), matchWrap(top = 6))
        }
        content.addView(page, FrameLayout.LayoutParams(-1, -1))
    }

    /** En-tête du tableau des lignes (tablette). */
    private fun calculationTableHeader(): View = horizontal(0).apply {
        setPadding(dp(6), dp(2), dp(6), dp(2))
        fun cell(t: String, params: LinearLayout.LayoutParams, end: Boolean = false) = addView(
            TextView(this@AdvancedCalculatorActivity).apply {
                text = t
                textSize = 9.5f
                typeface = HydriaType.display(600)
                letterSpacing = 0.06f
                setTextColor(HydriaColors.textMuted)
                if (end) gravity = Gravity.END
            }, params,
        )
        cell("", LinearLayout.LayoutParams(dp(48), -2))
        cell("LIBELLÉ", LinearLayout.LayoutParams(0, -2, 1.1f).apply { marginStart = dp(4) })
        cell("EXPRESSION", LinearLayout.LayoutParams(0, -2, 1.5f).apply { marginStart = dp(4) })
        cell("RÉSULTAT", LinearLayout.LayoutParams(dp(168), -2).apply { marginStart = dp(6) }, end = true)
        addView(View(this@AdvancedCalculatorActivity), LinearLayout.LayoutParams(dp(44), 1))
    }

    /**
     * Ligne du tableau des calculs (tablette) : L· libellé · expression · résultat · supprimer.
     * Résultat en monospace aligné à droite ; ligne en erreur = filet rouge + message.
     */
    private fun calculationTableRow(index: Int, line: CalculationLine): View {
        val active = index == state.activeCalculationLine
        val row = horizontal(0).apply {
            gravity = Gravity.CENTER_VERTICAL
            setPadding(dp(6), dp(4), dp(6), dp(4))
            minimumHeight = dp(52)
            isClickable = true
            when {
                line.error != null -> HydriaUi.accentedCard(this, Tone.ERROR)
                active -> HydriaUi.accentedCard(this, Tone.INFO)
                else -> background = HydriaUi.rounded(
                    this@AdvancedCalculatorActivity, HydriaColors.surface, 10f, HydriaColors.outlineSoft,
                )
            }
            elevation = 0f
            setOnClickListener { activateLine(index) }
        }
        row.addView(TextView(this).apply {
            text = "L${index + 1}"
            typeface = HydriaType.numeral(700)
            textSize = 12f
            gravity = Gravity.CENTER
            setTextColor(if (active) HydriaColors.cyan else HydriaColors.textMuted)
        }, LinearLayout.LayoutParams(dp(48), -2))
        row.addView(input(getString(R.string.calculator_label_hint)).apply {
            setText(line.label)
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_CAP_SENTENCES
            textSize = 13f
            doAfterTextChanged { value ->
                val rows = state.calculationLines.toMutableList()
                rows[index] = rows[index].copy(label = value?.toString().orEmpty().take(200))
                state = repository.save(state.copy(calculationLines = rows))
            }
        }, LinearLayout.LayoutParams(0, dp(44), 1.1f).apply { marginStart = dp(4) })
        val expressionField = input(getString(R.string.calculator_expression_hint)).apply {
            setText(line.expression)
            inputType = InputType.TYPE_CLASS_TEXT
            typeface = HydriaType.numeral(500)
            textSize = 14f
            showSoftInputOnFocus = false
            isCursorVisible = true
            setOnClickListener { activateLine(index, selectionStart.coerceAtLeast(0)) }
            setOnFocusChangeListener { _, focused -> if (focused) hideKeyboard(this) }
        }
        row.addView(expressionField, LinearLayout.LayoutParams(0, dp(44), 1.5f).apply { marginStart = dp(4) })
        if (active) activeExpressionField = expressionField
        val err = line.error
        val res = line.result
        row.addView(TextView(this).apply {
            text = when {
                err != null -> getString(err.messageResource())
                res != null -> formatDecimal(res)
                else -> "—"
            }
            typeface = HydriaType.numeral(700)
            textSize = 15f
            letterSpacing = -0.03f
            gravity = Gravity.END
            maxLines = 2
            setTextColor(when {
                err != null -> HydriaColors.error
                res != null -> HydriaColors.success
                else -> HydriaColors.textSecondary
            })
        }, LinearLayout.LayoutParams(dp(168), -2).apply { marginStart = dp(6) })
        row.addView(
            secondaryButton("×", getString(R.string.calculator_delete_line, index + 1)) { deleteLine(index) }.apply {
                minHeight = dp(40)
                minimumHeight = dp(40)
                setPadding(0, 0, 0, 0)
            },
            LinearLayout.LayoutParams(dp(44), dp(40)).apply { marginStart = dp(4) },
        )
        return row
    }

    private fun calculationCard(index: Int, line: CalculationLine): View = vertical(12).apply {
        val active = index == state.activeCalculationLine
        // Ligne active : encadré 2 dp cyan, rayon 16. Lignes passées : compactes, atténuées.
        background = HydriaUi.rounded(
            this@AdvancedCalculatorActivity,
            if (active) HydriaColors.surfaceRaised else HydriaColors.surface,
            16f,
            if (active) HydriaColors.cyan else HydriaColors.outline,
            if (active) 2f else 1f,
        )
        elevation = 0f
        if (!active) alpha = 0.65f
        isClickable = true
        setOnClickListener { activateLine(index) }
        addView(horizontal().apply {
            addView(HydriaUi.badge(this@AdvancedCalculatorActivity, "L${index + 1}", if (active) Tone.INFO else Tone.NEUTRAL))
            addView(View(this@AdvancedCalculatorActivity), LinearLayout.LayoutParams(0, 1, 1f))
            addView(secondaryButton("×", getString(R.string.calculator_delete_line, index + 1)) { deleteLine(index) }, fixed(44, 40))
        })
        addView(input(getString(R.string.calculator_label_hint)).apply {
            setText(line.label)
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_CAP_SENTENCES
            doAfterTextChanged { value ->
                val rows = state.calculationLines.toMutableList()
                rows[index] = rows[index].copy(label = value?.toString().orEmpty().take(200))
                state = repository.save(state.copy(calculationLines = rows))
            }
        }, matchWrap(50, top = 8))
        val expressionField = input(getString(R.string.calculator_expression_hint)).apply {
            setText(line.expression)
            inputType = InputType.TYPE_CLASS_TEXT
            typeface = HydriaType.numeral(500)
            showSoftInputOnFocus = false
            isCursorVisible = true
            setOnClickListener { activateLine(index, selectionStart.coerceAtLeast(0)) }
            setOnFocusChangeListener { _, focused -> if (focused) hideKeyboard(this) }
        }
        addView(expressionField, matchWrap(52, top = 8))
        if (active) activeExpressionField = expressionField
        val err = line.error
        val res = line.result
        val resultText = when {
            err != null -> getString(err.messageResource())
            res != null -> formatDecimal(res)
            else -> "—"
        }
        addView(TextView(this@AdvancedCalculatorActivity).apply {
            text = resultText
            typeface = HydriaType.numeral(700)
            textSize = if (res != null && active) 26f else if (res != null) 18f else 13f
            letterSpacing = -0.03f
            setTextColor(when {
                err != null -> HydriaColors.error
                res != null -> HydriaColors.success
                else -> HydriaColors.textSecondary
            })
        }, matchWrap(top = 8))
    }

    private fun renderQuote() {
        val page = vertical(14)
        val totalView = label(getString(R.string.calculator_amount_ariary, formatMoney(QuoteCalculator.total(state.quoteLines))), 24f, true, HydriaColors.success)
        page.addView(vertical(12).apply {
            HydriaUi.card(this, true)
            addView(label(getString(R.string.calculator_general_total), 12f, false, HydriaColors.textSecondary))
            addView(totalView, matchWrap(top = 4))
        })
        page.addView(horizontal(8).apply {
            addView(primaryButton(getString(R.string.calculator_add_line)) {
                if (state.quoteLines.size >= QuoteCalculator.MAX_LINES) toast(getString(R.string.calculator_line_limit_500))
                else { state = repository.save(state.copy(quoteLines = state.quoteLines + QuoteLine())); renderContent() }
            }, weighted().apply { marginEnd = dp(4) })
            addView(secondaryButton(getString(R.string.calculator_clear)) { confirmClearQuote() }, weighted().apply { marginStart = dp(4) })
        }, matchWrap(52, top = 10))
        val cards = vertical(10)
        state.quoteLines.forEachIndexed { index, line -> cards.addView(quoteCard(index, line, totalView)) }
        page.addView(ScrollView(this).apply { addView(cards) }, LinearLayout.LayoutParams(-1, 0, 1f).apply { topMargin = dp(10) })
        content.addView(page, FrameLayout.LayoutParams(-1, -1))
    }

    private fun quoteCard(index: Int, line: QuoteLine, totalView: TextView): View = vertical(10).apply {
        HydriaUi.card(this)
        val amountView = label("", 18f, true, HydriaColors.success)
        fun refreshAmount() {
            val current = state.quoteLines[index]
            amountView.text = current.amount?.let { getString(R.string.calculator_amount_ariary, formatMoney(it)) }
                ?: getString(R.string.calculator_invalid_number)
            amountView.setTextColor(if (current.amount == null) HydriaColors.error else HydriaColors.success)
            totalView.text = getString(R.string.calculator_amount_ariary, formatMoney(QuoteCalculator.total(state.quoteLines)))
        }
        addView(horizontal().apply {
            addView(HydriaUi.badge(this@AdvancedCalculatorActivity, "#${index + 1}", Tone.INFO))
            addView(View(this@AdvancedCalculatorActivity), LinearLayout.LayoutParams(0, 1, 1f))
            addView(secondaryButton("×", getString(R.string.calculator_delete)) {
                val rows = state.quoteLines.toMutableList()
                if (rows.size == 1) rows[0] = QuoteLine() else rows.removeAt(index)
                state = repository.save(state.copy(quoteLines = rows)); renderContent()
            }, fixed(48, 44))
        })
        val designation = input(getString(R.string.calculator_designation)).apply { setText(line.designation) }
        designation.doAfterTextChanged { value -> updateQuote(index, designation = value?.toString().orEmpty()); refreshAmount() }
        addView(designation, matchWrap(50, top = 8))
        addView(horizontal(8).apply {
            val quantity = decimalInput(getString(R.string.calculator_quantity), line.quantity)
            val price = decimalInput(getString(R.string.calculator_unit_price), line.unitPrice)
            quantity.doAfterTextChanged { updateQuote(index, quantity = it?.toString().orEmpty()); refreshAmount() }
            price.doAfterTextChanged { updateQuote(index, unitPrice = it?.toString().orEmpty()); refreshAmount() }
            addView(quantity, weighted().apply { marginEnd = dp(4) })
            addView(price, weighted().apply { marginStart = dp(4) })
        }, matchWrap(52, top = 8))
        addView(amountView, matchWrap(top = 8)); refreshAmount()
    }

    private fun updateQuote(index: Int, designation: String? = null, quantity: String? = null, unitPrice: String? = null) {
        val rows = state.quoteLines.toMutableList(); val old = rows[index]
        rows[index] = old.copy(
            designation = designation ?: old.designation,
            quantity = quantity ?: old.quantity,
            unitPrice = unitPrice ?: old.unitPrice,
        )
        state = repository.save(state.copy(quoteLines = rows))
    }

    private fun renderTotal() {
        totalCriterionViews.clear()
        val page = vertical(14)
        val totalView = summaryCard(page, getString(R.string.calculator_general_total), TotalCalculator.total(state.totalLines))
        page.addView(horizontal(8).apply {
            addView(primaryButton(getString(R.string.calculator_add_line)) {
                if (state.totalLines.size >= TotalCalculator.MAX_LINES) toast(getString(R.string.calculator_line_limit_500))
                else { state = repository.save(state.copy(totalLines = state.totalLines + TotalLine())); renderContent() }
            }, weighted().apply { marginEnd = dp(4) })
            addView(secondaryButton(getString(R.string.calculator_clear)) { confirmClearTotal() }, weighted().apply { marginStart = dp(4) })
        }, matchWrap(52, top = 10))
        val body = vertical(10)
        state.totalLines.forEachIndexed { index, line -> body.addView(totalLineCard(index, line, totalView)) }
        body.addView(criteriaHeader(
            add = {
                if (state.totalCriteria.size >= TotalCalculator.MAX_CRITERIA) toast(getString(R.string.calculator_criterion_limit))
                else { state = repository.save(state.copy(totalCriteria = state.totalCriteria + FilterCriterion())); renderContent() }
            },
            clear = { state = repository.save(state.copy(totalCriteria = emptyList())); renderContent() },
        ), matchWrap(top = 12))
        state.totalCriteria.forEachIndexed { index, criterion -> body.addView(totalCriterionCard(index, criterion)) }
        page.addView(ScrollView(this).apply { addView(body) }, LinearLayout.LayoutParams(-1, 0, 1f).apply { topMargin = dp(10) })
        content.addView(page, FrameLayout.LayoutParams(-1, -1))
    }

    private fun totalLineCard(index: Int, line: TotalLine, totalView: TextView): View = vertical(10).apply {
        HydriaUi.card(this)
        val amountView = label("", 17f, true, HydriaColors.success)
        fun refresh() {
            val current = state.totalLines[index]
            amountView.text = current.amount?.let { getString(R.string.calculator_amount_ariary, formatMoney(it)) } ?: getString(R.string.calculator_invalid_number)
            amountView.setTextColor(if (current.amount == null) HydriaColors.error else HydriaColors.success)
            totalView.text = getString(R.string.calculator_amount_ariary, formatMoney(TotalCalculator.total(state.totalLines)))
            refreshCriterionViews()
        }
        addView(lineHeader(index) {
            val rows = state.totalLines.toMutableList(); if (rows.size == 1) rows[0] = TotalLine() else rows.removeAt(index)
            state = repository.save(state.copy(totalLines = rows)); renderContent()
        })
        val date = input(getString(R.string.calculator_date)).apply { setText(line.date) }
        val designation = input(getString(R.string.calculator_designation)).apply { setText(line.designation) }
        val amount = decimalInput(getString(R.string.calculator_amount), line.amountInput)
        date.doAfterTextChanged { updateTotalLine(index, date = it?.toString().orEmpty()); refresh() }
        designation.doAfterTextChanged { updateTotalLine(index, designation = it?.toString().orEmpty()); refresh() }
        amount.doAfterTextChanged { updateTotalLine(index, amount = it?.toString().orEmpty()); refresh() }
        addView(date, matchWrap(50, top = 8)); addView(designation, matchWrap(50, top = 8)); addView(amount, matchWrap(50, top = 8))
        addView(amountView, matchWrap(top = 8)); refresh()
    }

    private fun updateTotalLine(index: Int, date: String? = null, designation: String? = null, amount: String? = null) {
        val rows = state.totalLines.toMutableList(); val old = rows[index]
        rows[index] = old.copy(date = date ?: old.date, designation = designation ?: old.designation, amountInput = amount ?: old.amountInput)
        state = repository.save(state.copy(totalLines = rows))
    }

    private fun totalCriterionCard(index: Int, criterion: FilterCriterion): View = criterionCard(index, criterion,
        result = { getString(R.string.calculator_amount_ariary, formatMoney(TotalCalculator.result(state.totalLines, it).subtotal)) },
        update = { updated ->
            val rows = state.totalCriteria.toMutableList(); rows[index] = updated
            state = repository.save(state.copy(totalCriteria = rows))
        },
        delete = {
            val rows = state.totalCriteria.toMutableList().apply { removeAt(index) }
            state = repository.save(state.copy(totalCriteria = rows)); renderContent()
        },
    )

    private fun renderCash() {
        cashCriterionViews.clear()
        val page = vertical(14)
        val balanceView = summaryCard(page, getString(R.string.calculator_balance), state.cashLines.lastOrNull()?.balance ?: BigDecimal.ZERO)
        page.addView(horizontal(6).apply {
            addView(primaryButton(getString(R.string.calculator_add_line)) {
                if (state.cashLines.size >= CashCalculator.MAX_LINES) toast(getString(R.string.calculator_line_limit))
                else { state = repository.save(state.copy(cashLines = state.cashLines + CashLine())); renderContent() }
            }, weighted().apply { marginEnd = dp(3) })
            addView(secondaryButton(getString(R.string.calculator_save_book)) { promptSaveBook() }, weighted().apply { marginStart = dp(3); marginEnd = dp(3) })
            addView(secondaryButton(getString(R.string.calculator_clear)) { confirmClearCash() }, weighted().apply { marginStart = dp(3) })
        }, matchWrap(52, top = 10))
        page.addView(secondaryButton(getString(R.string.calculator_manage_books)) { showCashBooks() }, matchWrap(50, top = 8))
        val body = vertical(10)
        state.cashLines.forEachIndexed { index, line -> body.addView(cashLineCard(index, line, balanceView)) }
        body.addView(criteriaHeader(
            add = {
                if (state.cashCriteria.size >= CashCalculator.MAX_CRITERIA) toast(getString(R.string.calculator_criterion_limit))
                else { state = repository.save(state.copy(cashCriteria = state.cashCriteria + FilterCriterion())); renderContent() }
            },
            clear = { state = repository.save(state.copy(cashCriteria = emptyList())); renderContent() },
        ), matchWrap(top = 12))
        state.cashCriteria.forEachIndexed { index, criterion -> body.addView(cashCriterionCard(index, criterion)) }
        page.addView(ScrollView(this).apply { addView(body) }, LinearLayout.LayoutParams(-1, 0, 1f).apply { topMargin = dp(10) })
        content.addView(page, FrameLayout.LayoutParams(-1, -1))
    }

    private fun cashLineCard(index: Int, line: CashLine, balanceView: TextView): View = vertical(10).apply {
        HydriaUi.card(this)
        val rowBalance = label("", 17f, true)
        fun refresh() {
            rowBalance.text = getString(R.string.calculator_amount_ariary, formatMoney(state.cashLines[index].balance))
            rowBalance.setTextColor(if (state.cashLines[index].balance.signum() < 0) HydriaColors.error else HydriaColors.success)
            val finalBalance = state.cashLines.lastOrNull()?.balance ?: BigDecimal.ZERO
            balanceView.text = getString(R.string.calculator_amount_ariary, formatMoney(finalBalance))
            balanceView.setTextColor(if (finalBalance.signum() < 0) HydriaColors.error else HydriaColors.success)
            refreshCriterionViews()
        }
        addView(lineHeader(index) {
            val rows = state.cashLines.toMutableList(); if (rows.size == 1) rows[0] = CashLine() else rows.removeAt(index)
            state = repository.save(state.copy(cashLines = rows)); renderContent()
        })
        val date = input(getString(R.string.calculator_date)).apply { setText(line.date) }
        val designation = input(getString(R.string.calculator_designation)).apply { setText(line.designation) }
        val entry = decimalInput(getString(R.string.calculator_entry), line.entryInput)
        val exit = decimalInput(getString(R.string.calculator_exit), line.exitInput)
        val reference = input(getString(R.string.calculator_reference_invoice)).apply { setText(line.reference) }
        date.doAfterTextChanged { updateCashLine(index, date = it?.toString().orEmpty()); refresh() }
        designation.doAfterTextChanged { updateCashLine(index, designation = it?.toString().orEmpty()); refresh() }
        entry.doAfterTextChanged { updateCashLine(index, entry = it?.toString().orEmpty()); refresh() }
        exit.doAfterTextChanged { updateCashLine(index, exit = it?.toString().orEmpty()); refresh() }
        reference.doAfterTextChanged { updateCashLine(index, reference = it?.toString().orEmpty()); refresh() }
        addView(date, matchWrap(50, top = 8)); addView(designation, matchWrap(50, top = 8))
        addView(horizontal(8).apply { addView(entry, weighted().apply { marginEnd = dp(4) }); addView(exit, weighted().apply { marginStart = dp(4) }) }, matchWrap(52, top = 8))
        addView(reference, matchWrap(50, top = 8)); addView(rowBalance, matchWrap(top = 8)); refresh()
    }

    private fun updateCashLine(index: Int, date: String? = null, designation: String? = null, entry: String? = null, exit: String? = null, reference: String? = null) {
        val rows = state.cashLines.toMutableList(); val old = rows[index]
        rows[index] = old.copy(date = date ?: old.date, designation = designation ?: old.designation,
            entryInput = entry ?: old.entryInput, exitInput = exit ?: old.exitInput, reference = reference ?: old.reference)
        state = repository.save(state.copy(cashLines = rows))
    }

    private fun cashCriterionCard(index: Int, criterion: FilterCriterion): View = criterionCard(index, criterion,
        result = {
            val result = CashCalculator.result(state.cashLines, it)
            "${getString(R.string.calculator_total_entries, formatMoney(result.entries))}\n${getString(R.string.calculator_total_exits, formatMoney(result.exits))}\n${getString(R.string.calculator_net_balance, formatMoney(result.net))}"
        },
        update = { updated ->
            val rows = state.cashCriteria.toMutableList(); rows[index] = updated
            state = repository.save(state.copy(cashCriteria = rows))
        },
        delete = {
            val rows = state.cashCriteria.toMutableList().apply { removeAt(index) }
            state = repository.save(state.copy(cashCriteria = rows)); renderContent()
        },
    )

    private fun renderGps() {
        val page = vertical(14)
        val body = vertical(12)
        // Position actuelle du téléphone : un bouton, puis la meilleure position en 30 s maximum.
        body.addView(vertical(12).apply {
            HydriaUi.card(this)
            addView(label(getString(R.string.gps_phone_title), 20f, true))
            phoneGpsButton = primaryButton(getString(R.string.gps_phone_capture)) {
                if (phoneGps == null) requestPhoneGps() else finishPhoneGps()
            }
            addView(phoneGpsButton, matchWrap(52, top = 8))
            phoneGpsStatus = label(getString(R.string.gps_phone_hint), 12f, false, HydriaColors.textSecondary)
            addView(phoneGpsStatus, matchWrap(top = 6))
            if (phoneGps != null) updatePhoneGpsUi()
        })
        body.addView(vertical(12).apply {
            HydriaUi.card(this)
            addView(label(getString(R.string.gps_dms_title), 20f, true))
            val dms = input(getString(R.string.gps_dms_hint)).apply { setText(state.gpsDraft.dmsInput); maxLines = 3 }
            dms.doAfterTextChanged { state = repository.save(state.copy(gpsDraft = state.gpsDraft.copy(dmsInput = it?.toString().orEmpty()))) }
            addView(dms, matchWrap(58, top = 8))
            addView(primaryButton(getString(R.string.gps_convert)) {
                when (val result = GpsConverter.fromDms(dms.text.toString())) {
                    is GpsConversion.Success -> applyGpsCoordinate(result.coordinate)
                    is GpsConversion.Invalid -> toast(getString(result.error.messageResource()))
                }
            }, matchWrap(52, top = 8))
        })
        body.addView(vertical(12).apply {
            HydriaUi.card(this)
            addView(label(getString(R.string.gps_decimal_title), 20f, true))
            gpsLatitudeField = decimalInput(getString(R.string.gps_latitude), state.gpsDraft.latitudeInput)
            gpsLongitudeField = decimalInput(getString(R.string.gps_longitude), state.gpsDraft.longitudeInput)
            gpsLatitudeField?.doAfterTextChanged { state = repository.save(state.copy(gpsDraft = state.gpsDraft.copy(latitudeInput = it?.toString().orEmpty()))) }
            gpsLongitudeField?.doAfterTextChanged { state = repository.save(state.copy(gpsDraft = state.gpsDraft.copy(longitudeInput = it?.toString().orEmpty()))) }
            addView(gpsLatitudeField!!, matchWrap(52, top = 8)); addView(gpsLongitudeField!!, matchWrap(52, top = 8))
            addView(primaryButton(getString(R.string.gps_apply_decimal)) {
                when (val result = GpsConverter.fromDecimal(gpsLatitudeField?.text.toString(), gpsLongitudeField?.text.toString())) {
                    is GpsConversion.Success -> applyGpsCoordinate(result.coordinate)
                    is GpsConversion.Invalid -> toast(getString(result.error.messageResource()))
                }
            }, matchWrap(52, top = 8))
            gpsCombinedView = label(currentGpsCombined(), 18f, true, HydriaColors.success)
            addView(gpsCombinedView, matchWrap(top = 10))
            if (state.gpsDraft.updatedAt > 0) addView(label(getString(R.string.gps_updated,
                DateFormat.getDateTimeInstance(DateFormat.SHORT, DateFormat.SHORT).format(Date(state.gpsDraft.updatedAt))), 11f, false, HydriaColors.textSecondary), matchWrap(top = 4))
            addView(horizontal(5).apply {
                addView(secondaryButton(getString(R.string.gps_copy_latitude)) { copyGps(state.gpsDraft.latitude) }, weighted().apply { marginEnd = dp(3) })
                addView(secondaryButton(getString(R.string.gps_copy_longitude)) { copyGps(state.gpsDraft.longitude) }, weighted().apply { marginStart = dp(3); marginEnd = dp(3) })
                addView(secondaryButton(getString(R.string.gps_copy_pair)) { copyGps(currentGpsCombined()) }, weighted().apply { marginStart = dp(3) })
            }, matchWrap(52, top = 8))
        })
        body.addView(vertical(12).apply {
            HydriaUi.card(this)
            addView(label(getString(R.string.gps_map_title), 20f, true))
            addView(label(getString(R.string.gps_map_offline), 12f, false, HydriaColors.textSecondary), matchWrap(top = 4))
            val mapView = createGpsMap()
            addView(mapView, matchWrap(300, top = 8))
            addView(secondaryButton(getString(R.string.gps_open_external)) { openGpsExternal() }, matchWrap(52, top = 8))
        })
        body.addView(secondaryButton(getString(R.string.gps_clear)) { confirmClearGps() }, matchWrap(52))
        page.addView(ScrollView(this).apply { addView(body) }, LinearLayout.LayoutParams(-1, 0, 1f))
        content.addView(page, FrameLayout.LayoutParams(-1, -1))
    }

    private fun createGpsMap(): MapView {
        releaseGpsMap()
        val mapView = MapView(this)
        gpsMapView = mapView
        mapView.onCreate(null)
        if (activityStarted) mapView.onStart()
        if (activityResumed) mapView.onResume()
        mapView.getMapAsync { mapLibreMap ->
            gpsMap = mapLibreMap
            mapLibreMap.uiSettings.apply {
                isCompassEnabled = true; isZoomGesturesEnabled = true; isRotateGesturesEnabled = true
                isTiltGesturesEnabled = false; isLogoEnabled = false
            }
            mapView.addOnDidFailLoadingMapListener {
                if (!gpsUsingOfflineStyle) {
                    gpsUsingOfflineStyle = true
                    runOnUiThread { loadGpsStyle(mapLibreMap, true) }
                }
            }
            loadGpsStyle(mapLibreMap, !isOnline())
            mapLibreMap.addOnMapClickListener { point ->
                applyGpsCoordinate(GpsCoordinate(
                    BigDecimal.valueOf(point.latitude).setScale(8, java.math.RoundingMode.HALF_UP),
                    BigDecimal.valueOf(point.longitude).setScale(8, java.math.RoundingMode.HALF_UP),
                )); true
            }
            val current = currentGpsCoordinate()
            mapLibreMap.moveCamera(CameraUpdateFactory.newLatLngZoom(
                current?.let { LatLng(it.latitude.toDouble(), it.longitude.toDouble()) } ?: MADAGASCAR_CENTER,
                if (current == null) 5.0 else 14.0,
            ))
        }
        return mapView
    }

    private fun loadGpsStyle(mapLibreMap: MapLibreMap, offline: Boolean) {
        gpsUsingOfflineStyle = offline
        mapLibreMap.uiSettings.isAttributionEnabled = !offline
        mapLibreMap.setStyle(Style.Builder().fromUri(if (offline) "asset://navigation_neutral_style.json" else ONLINE_MAP_STYLE)) {
            updateGpsMarker(false)
        }
    }

    private fun applyGpsCoordinate(coordinate: GpsCoordinate) {
        val latitude = coordinate.latitude.setScale(8, java.math.RoundingMode.HALF_UP).toPlainString()
        val longitude = coordinate.longitude.setScale(8, java.math.RoundingMode.HALF_UP).toPlainString()
        state = repository.save(state.copy(gpsDraft = state.gpsDraft.copy(
            latitudeInput = latitude, longitudeInput = longitude, latitude = latitude, longitude = longitude, updatedAt = System.currentTimeMillis(),
        )))
        if (gpsLatitudeField?.text.toString() != latitude) gpsLatitudeField?.setText(latitude)
        if (gpsLongitudeField?.text.toString() != longitude) gpsLongitudeField?.setText(longitude)
        gpsCombinedView?.text = coordinate.combined
        updateGpsMarker(true)
    }

    private fun currentGpsCoordinate(): GpsCoordinate? {
        val latitude = state.gpsDraft.latitude.toBigDecimalOrNull() ?: return null
        val longitude = state.gpsDraft.longitude.toBigDecimalOrNull() ?: return null
        return GpsCoordinate(latitude, longitude)
    }

    private fun currentGpsCombined(): String = currentGpsCoordinate()?.combined ?: "—"

    private fun updateGpsMarker(center: Boolean) {
        val coordinate = currentGpsCoordinate() ?: return
        val mapLibreMap = gpsMap ?: return
        gpsMarker?.remove()
        val point = LatLng(coordinate.latitude.toDouble(), coordinate.longitude.toDouble())
        gpsMarker = mapLibreMap.addMarker(MarkerOptions().position(point).title(getString(R.string.calculator_title)))
        if (center) mapLibreMap.animateCamera(CameraUpdateFactory.newLatLngZoom(point, 14.0), 350)
    }

    private fun copyGps(value: String) {
        if (value.isBlank() || value == "—") { toast(getString(R.string.gps_no_coordinate)); return }
        val clipboard = getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
        clipboard.setPrimaryClip(ClipData.newPlainText(getString(R.string.calculator_tab_gps), value))
        toast(getString(R.string.gps_copied))
    }

    private fun openGpsExternal() {
        val coordinate = currentGpsCoordinate() ?: run { toast(getString(R.string.gps_no_coordinate)); return }
        val pair = "${coordinate.latitude.toPlainString()},${coordinate.longitude.toPlainString()}"
        runCatching { startActivity(Intent(Intent.ACTION_VIEW, Uri.parse("geo:$pair?q=$pair"))) }
            .onFailure { toast(getString(R.string.gps_no_coordinate)) }
    }

    private fun confirmClearGps() = confirmClear(R.string.gps_clear_confirmation) {
        state = repository.save(state.copy(gpsDraft = GpsDraft())); renderContent()
    }

    private fun requestPhoneGps() {
        val fine = android.Manifest.permission.ACCESS_FINE_LOCATION
        val coarse = android.Manifest.permission.ACCESS_COARSE_LOCATION
        val granted = listOf(fine, coarse).any {
            androidx.core.content.ContextCompat.checkSelfPermission(this, it) == android.content.pm.PackageManager.PERMISSION_GRANTED
        }
        if (granted) startPhoneGps() else locationPermission.launch(arrayOf(fine, coarse))
    }

    private fun startPhoneGps() {
        stopPhoneGps()
        phoneGpsBest = null
        phoneGpsStartedAt = System.currentTimeMillis()
        val controller = mg.hydria.app.navigation.location.TerrainLocationController(this,
            onLocation = { location -> runOnUiThread { onPhoneLocation(location) } },
            onUnavailable = { message -> runOnUiThread {
                if (phoneGpsBest == null) { stopPhoneGps(); toast(getString(R.string.gps_phone_unavailable, message)); updatePhoneGpsUi() }
            } })
        phoneGps = controller
        controller.start()
        if (phoneGps == null) return
        phoneGpsHandler.postDelayed(phoneGpsTimeout, CalculatorDeviceRules.GPS_MAX_WAIT_MS)
        updatePhoneGpsUi()
    }

    private fun onPhoneLocation(location: android.location.Location) {
        if (phoneGps == null) return
        // Une position mémorisée trop ancienne (dernière connue d'un autre lieu) est ignorée.
        val age = System.currentTimeMillis() - location.time
        if (!CalculatorDeviceRules.isFreshFix(age)) return
        val accuracy = if (location.hasAccuracy()) location.accuracy else null
        val bestAccuracy = phoneGpsBest?.let { if (it.hasAccuracy()) it.accuracy else Float.MAX_VALUE }
        if (CalculatorDeviceRules.isBetter(accuracy, bestAccuracy)) phoneGpsBest = location
        val best = phoneGpsBest ?: return
        val done = CalculatorDeviceRules.captureDone(
            if (best.hasAccuracy()) best.accuracy else Float.MAX_VALUE,
            System.currentTimeMillis() - phoneGpsStartedAt)
        if (done) finishPhoneGps() else updatePhoneGpsUi()
    }

    /** Retient la meilleure position obtenue (bouton « Utiliser », précision atteinte ou délai écoulé). */
    private fun finishPhoneGps() {
        val best = phoneGpsBest
        stopPhoneGps()
        if (best == null) {
            toast(getString(R.string.gps_phone_no_fix))
        } else {
            applyGpsCoordinate(GpsCoordinate(
                BigDecimal.valueOf(best.latitude).setScale(8, java.math.RoundingMode.HALF_UP),
                BigDecimal.valueOf(best.longitude).setScale(8, java.math.RoundingMode.HALF_UP),
            ))
            HydriaFeedback.success()
            toast(getString(R.string.gps_phone_done, if (best.hasAccuracy()) best.accuracy.toInt().toString() else "?"))
        }
        updatePhoneGpsUi()
    }

    private fun stopPhoneGps() {
        phoneGpsHandler.removeCallbacks(phoneGpsTimeout)
        phoneGps?.stop()
        phoneGps = null
    }

    private fun updatePhoneGpsUi() {
        val searching = phoneGps != null
        val best = phoneGpsBest
        phoneGpsButton?.text = getString(when {
            !searching -> R.string.gps_phone_capture
            best != null -> R.string.gps_phone_use_now
            else -> R.string.gps_phone_searching
        })
        phoneGpsStatus?.text = when {
            searching && best != null -> getString(R.string.gps_phone_progress,
                if (best.hasAccuracy()) best.accuracy.toInt().toString() else "?",
                CalculatorDeviceRules.GPS_TARGET_ACCURACY_M.toInt().toString())
            searching -> getString(R.string.gps_phone_waiting)
            else -> getString(R.string.gps_phone_hint)
        }
    }

    private fun releaseGpsMap() {
        val mapView = gpsMapView ?: return
        runCatching { if (activityResumed) mapView.onPause() }
        runCatching { if (activityStarted) mapView.onStop() }
        runCatching { mapView.onDestroy() }
        gpsMapView = null; gpsMap = null; gpsMarker = null; gpsUsingOfflineStyle = false
    }

    private fun summaryCard(parent: LinearLayout, title: String, amount: BigDecimal): TextView {
        val amountView = label(getString(R.string.calculator_amount_ariary, formatMoney(amount)), 24f, true,
            if (amount.signum() < 0) HydriaColors.error else HydriaColors.success)
        parent.addView(vertical(12).apply {
            HydriaUi.card(this, true)
            addView(label(title, 12f, false, HydriaColors.textSecondary))
            addView(amountView, matchWrap(top = 4))
        })
        return amountView
    }

    private fun lineHeader(index: Int, delete: () -> Unit): View = horizontal().apply {
        addView(HydriaUi.badge(this@AdvancedCalculatorActivity, "#${index + 1}", Tone.INFO))
        addView(View(this@AdvancedCalculatorActivity), LinearLayout.LayoutParams(0, 1, 1f))
        addView(secondaryButton("×", getString(R.string.calculator_delete)) { delete() }, fixed(48, 44))
    }

    private fun criteriaHeader(add: () -> Unit, clear: () -> Unit): View = vertical(8).apply {
        addView(label(getString(R.string.calculator_criteria), 20f, true))
        addView(horizontal(8).apply {
            addView(primaryButton(getString(R.string.calculator_add_criterion)) { add() }, weighted().apply { marginEnd = dp(4) })
            addView(secondaryButton(getString(R.string.calculator_clear_criteria)) { clear() }, weighted().apply { marginStart = dp(4) })
        }, matchWrap(52, top = 6))
    }

    private fun criterionCard(
        index: Int,
        criterion: FilterCriterion,
        result: (FilterCriterion) -> String,
        update: (FilterCriterion) -> Unit,
        delete: () -> Unit,
    ): View = vertical(10).apply {
        HydriaUi.card(this)
        var current = criterion
        val resultView = label(result(current), 16f, true, HydriaColors.success)
        if (state.selectedTab == CalculatorTab.TOTAL) totalCriterionViews[criterion.localId] = resultView
        if (state.selectedTab == CalculatorTab.CASH) cashCriterionViews[criterion.localId] = resultView
        fun refresh(updated: FilterCriterion) {
            current = updated
            update(updated)
            resultView.text = result(updated)
            if (state.selectedTab == CalculatorTab.CASH) {
                resultView.setTextColor(if (CashCalculator.result(state.cashLines, updated).net.signum() < 0) HydriaColors.error else HydriaColors.success)
            }
        }
        addView(horizontal().apply {
            addView(HydriaUi.badge(this@AdvancedCalculatorActivity, "#${index + 1}", Tone.NEUTRAL))
            addView(secondaryButton(getString(if (criterion.mode == ComparisonMode.CONTAINS) R.string.calculator_contains else R.string.calculator_equals_mode)) {
                refresh(current.copy(mode = if (current.mode == ComparisonMode.CONTAINS) ComparisonMode.EQUALS else ComparisonMode.CONTAINS))
                renderContent()
            }, LinearLayout.LayoutParams(dp(112), dp(44)).apply { marginStart = dp(8) })
            addView(View(this@AdvancedCalculatorActivity), LinearLayout.LayoutParams(0, 1, 1f))
            addView(secondaryButton("×", getString(R.string.calculator_delete)) { delete() }, fixed(48, 44))
        })
        val designation = input(getString(R.string.calculator_designation)).apply { setText(criterion.designation) }
        val date = input(getString(R.string.calculator_date)).apply { setText(criterion.date) }
        designation.doAfterTextChanged { refresh(current.copy(designation = it?.toString().orEmpty())) }
        date.doAfterTextChanged { refresh(current.copy(date = it?.toString().orEmpty())) }
        addView(designation, matchWrap(50, top = 8)); addView(date, matchWrap(50, top = 8)); addView(resultView, matchWrap(top = 8))
        if (state.selectedTab == CalculatorTab.CASH) refresh(current)
    }

    private fun refreshCriterionViews() {
        state.totalCriteria.forEach { criterion ->
            totalCriterionViews[criterion.localId]?.text = getString(R.string.calculator_amount_ariary,
                formatMoney(TotalCalculator.result(state.totalLines, criterion).subtotal))
        }
        state.cashCriteria.forEach { criterion ->
            cashCriterionViews[criterion.localId]?.let { view ->
                val result = CashCalculator.result(state.cashLines, criterion)
                view.text = "${getString(R.string.calculator_total_entries, formatMoney(result.entries))}\n${getString(R.string.calculator_total_exits, formatMoney(result.exits))}\n${getString(R.string.calculator_net_balance, formatMoney(result.net))}"
                view.setTextColor(if (result.net.signum() < 0) HydriaColors.error else HydriaColors.success)
            }
        }
    }

    private fun promptSaveBook() {
        val name = input(getString(R.string.calculator_book_name))
        AlertDialog.Builder(this).setTitle(R.string.calculator_save_book).setView(name)
            .setNegativeButton(R.string.calculator_cancel, null)
            .setPositiveButton(R.string.calculator_save_book) { _, _ -> saveBook(CashCalculator.normalizeBookName(name.text.toString())) }
            .show()
    }

    private fun saveBook(name: String, overwriteConfirmed: Boolean = false) {
        if (name.isBlank()) { toast(getString(R.string.calculator_book_name_required)); return }
        val existingIndex = state.namedCashBooks.indexOfFirst { it.name.equals(name, ignoreCase = true) }
        if (existingIndex >= 0 && !overwriteConfirmed) {
            AlertDialog.Builder(this).setTitle(R.string.calculator_save_book).setMessage(R.string.calculator_overwrite_book)
                .setNegativeButton(R.string.calculator_cancel, null)
                .setPositiveButton(R.string.calculator_save_book) { _, _ -> saveBook(name, true) }.show()
            return
        }
        if (existingIndex < 0 && state.namedCashBooks.size >= CashCalculator.MAX_BOOKS) { toast(getString(R.string.calculator_book_limit)); return }
        val snapshot = NamedCashBook(
            localId = if (existingIndex >= 0) state.namedCashBooks[existingIndex].localId else java.util.UUID.randomUUID().toString(),
            name = name,
            updatedAt = System.currentTimeMillis(),
            lines = state.cashLines.map { it.copy() },
            criteria = state.cashCriteria.map { it.copy() },
        )
        val books = state.namedCashBooks.toMutableList()
        if (existingIndex >= 0) books[existingIndex] = snapshot else books += snapshot
        state = repository.save(state.copy(namedCashBooks = books)); toast(getString(R.string.calculator_saved))
    }

    private fun showCashBooks() {
        if (state.namedCashBooks.isEmpty()) { toast(getString(R.string.calculator_manage_books)); return }
        val labels = state.namedCashBooks.map { book ->
            "${book.name}\n${getString(R.string.calculator_book_updated, DateFormat.getDateTimeInstance(DateFormat.SHORT, DateFormat.SHORT).format(Date(book.updatedAt)))}"
        }.toTypedArray()
        AlertDialog.Builder(this).setTitle(R.string.calculator_manage_books).setItems(labels) { _, index -> showCashBookActions(state.namedCashBooks[index]) }
            .setNegativeButton(R.string.calculator_cancel, null).show()
    }

    private fun showCashBookActions(book: NamedCashBook) {
        AlertDialog.Builder(this).setTitle(book.name)
            .setMessage(getString(R.string.calculator_book_updated, DateFormat.getDateTimeInstance(DateFormat.SHORT, DateFormat.SHORT).format(Date(book.updatedAt))))
            .setNeutralButton(R.string.calculator_cancel, null)
            .setNegativeButton(R.string.calculator_delete) { _, _ -> confirmDeleteBook(book) }
            .setPositiveButton(R.string.calculator_load) { _, _ ->
                state = repository.save(state.copy(cashLines = book.lines.map { it.copy() }, cashCriteria = book.criteria.map { it.copy() })); renderContent()
                toast(getString(R.string.calculator_loaded))
            }.show()
    }

    private fun confirmDeleteBook(book: NamedCashBook) {
        AlertDialog.Builder(this).setTitle(R.string.calculator_delete).setMessage(getString(R.string.calculator_delete_book_confirmation, book.name))
            .setNegativeButton(R.string.calculator_cancel, null)
            .setPositiveButton(R.string.calculator_delete) { _, _ ->
                state = repository.save(state.copy(namedCashBooks = state.namedCashBooks.filterNot { it.localId == book.localId })); renderContent()
            }.show()
    }

    private fun confirmClearQuote() = confirmClear(R.string.calculator_clear_quote_confirmation) {
        state = repository.save(state.copy(quoteLines = listOf(QuoteLine()))); renderContent()
    }

    private fun confirmClearTotal() = confirmClear(R.string.calculator_clear_total_confirmation) {
        state = repository.save(state.copy(totalLines = listOf(TotalLine()), totalCriteria = emptyList())); renderContent()
    }

    private fun confirmClearCash() = confirmClear(R.string.calculator_clear_cash_confirmation) {
        state = repository.save(state.copy(cashLines = listOf(CashLine()), cashCriteria = emptyList())); renderContent()
    }

    private fun confirmClear(message: Int, action: () -> Unit) = AlertDialog.Builder(this)
        .setTitle(R.string.calculator_clear).setMessage(message).setNegativeButton(R.string.calculator_cancel, null)
        .setPositiveButton(R.string.calculator_clear) { _, _ -> action() }.show()

    private fun referenceStrip(): View = HorizontalScrollView(this).apply {
        isHorizontalScrollBarEnabled = false
        // Pas de marge verticale : la bande mesure 48 dp et les puces (WRAP_CONTENT) sont bornées à
        // la hauteur de la rangée ; avec 6 dp de marge elles tombaient à 32-36 dp (TRANSVERSE-05).
        val row = horizontal(6).apply { setPadding(dp(6), 0, dp(6), 0) }
        state.calculationLines.forEachIndexed { index, line ->
            val res = line.result
            if (index < state.activeCalculationLine && res != null && line.error == null) {
                row.addView(
                    HydriaUi.chip(this@AdvancedCalculatorActivity, "L${index + 1} · ${formatDecimal(res)}", false).apply {
                        contentDescription = getString(R.string.calculator_insert_reference, index + 1)
                        setOnClickListener { insertText("L${index + 1}") }
                    },
                    LinearLayout.LayoutParams(LinearLayout.LayoutParams.WRAP_CONTENT, LinearLayout.LayoutParams.WRAP_CONTENT).apply { marginEnd = dp(6) },
                )
            }
        }
        if (row.childCount == 0) row.addView(label(getString(R.string.calculator_no_reference), 12f, false, HydriaColors.textSecondary))
        // Hauteur de la rangée = celle de la bande (puces et libellé centrés verticalement).
        addView(row, FrameLayout.LayoutParams(FrameLayout.LayoutParams.WRAP_CONTENT, FrameLayout.LayoutParams.MATCH_PARENT))
    }

    /** Hauteur des touches adaptée à l'écran : le pavé ne cache plus les lignes sur un petit téléphone. */
    private val keyHeight: Int get() = CalculatorDeviceRules.keyHeightDp(resources.configuration.screenHeightDp)

    private fun keypad(): View = vertical(6).apply {
        listOf(
            listOf("(", ")", "%", "⌫"), listOf("7", "8", "9", "÷"),
            listOf("4", "5", "6", "×"), listOf("1", "2", "3", "−"),
            listOf("C", "0", ",", "+"),
        ).forEach { keys ->
            addView(horizontal(5).apply { keys.forEach { addView(keyButton(it), weighted().apply { marginEnd = dp(5) }) } }, matchWrap(keyHeight, top = 3))
        }
        addView(primaryButton("= Ligne suivante") { nextLine() }.apply {
            contentDescription = getString(R.string.calculator_equals)
        }, matchWrap(keyHeight, top = 5))
    }

    private fun keyButton(key: String): Button {
        val isOperator = key in setOf("÷", "×", "−", "+", "%", "(", ")")
        return secondaryButton(key, getString(when (key) {
            "⌫" -> R.string.calculator_backspace; "C" -> R.string.calculator_clear_expression
            "×" -> R.string.calculator_multiply; "÷" -> R.string.calculator_divide
            "−" -> R.string.calculator_subtract; else -> R.string.calculator_key
        }, key)) {
            it.performHapticFeedback(HapticFeedbackConstants.KEYBOARD_TAP)
            HydriaFeedback.tap()
            when (key) { "⌫" -> backspace(); "C" -> replaceActiveExpression(""); else -> insertText(key) }
        }.apply {
            textSize = CalculatorDeviceRules.keyTextSizeSp(keyHeight)
            typeface = HydriaType.numeral(600)
            if (isOperator) {
                background = HydriaUi.rounded(this@AdvancedCalculatorActivity, HydriaColors.surfaceRaised, 14f, HydriaColors.outline)
                setTextColor(HydriaColors.cyan)
            } else if (key == "C" || key == "⌫") {
                setTextColor(HydriaColors.textSecondary)
            } else {
                setTextColor(HydriaColors.text)
            }
        }
    }

    private fun activateLine(index: Int, cursor: Int? = null) {
        if (index !in state.calculationLines.indices) return
        if (state.activeCalculationLine != index) {
            state = repository.save(state.copy(activeCalculationLine = index)); renderContent()
        }
        activeExpressionField?.post {
            activeExpressionField?.requestFocus()
            val length = activeExpressionField?.text?.length ?: 0
            activeExpressionField?.setSelection((cursor ?: length).coerceIn(0, length))
        }
    }

    private fun insertText(value: String) {
        val field = activeExpressionField ?: return
        val start = field.selectionStart.coerceAtLeast(0)
        val end = field.selectionEnd.coerceAtLeast(start)
        replaceActiveExpression(field.text.toString().replaceRange(start, end, value), start + value.length)
    }

    private fun backspace() {
        val field = activeExpressionField ?: return
        val start = field.selectionStart.coerceAtLeast(0)
        val end = field.selectionEnd.coerceAtLeast(start)
        if (start == 0 && end == 0) return
        val deleteStart = if (start == end) start - 1 else start
        replaceActiveExpression(field.text.toString().removeRange(deleteStart, end), deleteStart)
    }

    private fun replaceActiveExpression(value: String, cursor: Int = value.length) {
        val rows = state.calculationLines.toMutableList()
        rows[state.activeCalculationLine] = rows[state.activeCalculationLine].copy(expression = value.take(CalculatorState.MAX_EXPRESSION_LENGTH))
        state = repository.save(state.copy(calculationLines = rows)); renderContent()
        activeExpressionField?.post {
            activeExpressionField?.requestFocus()
            activeExpressionField?.setSelection(cursor.coerceIn(0, activeExpressionField?.text?.length ?: 0))
        }
    }

    private fun addLine(): Boolean {
        if (state.calculationLines.size >= CalculatorState.MAX_CALCULATION_LINES) { toast(getString(R.string.calculator_line_limit)); return false }
        val rows = state.calculationLines + CalculationLine()
        state = repository.save(state.copy(calculationLines = rows, activeCalculationLine = rows.lastIndex)); renderContent(); return true
    }

    private fun nextLine() {
        recalculate(false)
        val next = state.activeCalculationLine + 1
        if (next < state.calculationLines.size) { state = repository.save(state.copy(activeCalculationLine = next)); renderContent() } else addLine()
    }

    private fun deleteLine(index: Int) {
        if (state.calculationLines.size == 1) { replaceActiveExpression(""); return }
        val rows = state.calculationLines.toMutableList().apply { removeAt(index) }
        state = repository.save(state.copy(calculationLines = rows, activeCalculationLine = minOf(state.activeCalculationLine, rows.lastIndex))); renderContent()
    }

    private fun recalculate(render: Boolean = true) { state = repository.save(state); if (render) renderContent() }
    private fun confirmClearCalculations() = AlertDialog.Builder(this).setTitle(R.string.calculator_clear_calculations).setMessage(R.string.calculator_clear_calculations_confirmation).setNegativeButton(R.string.calculator_cancel, null).setPositiveButton(R.string.calculator_clear) { _, _ -> state = repository.save(state.copy(activeCalculationLine = 0, calculationLines = listOf(CalculationLine()))); renderContent() }.show()
    private fun confirmClearMemory() = AlertDialog.Builder(this).setTitle(R.string.calculator_clear_memory).setMessage(R.string.calculator_clear_memory_confirmation).setNegativeButton(R.string.calculator_cancel, null).setPositiveButton(R.string.calculator_clear) { _, _ -> state = repository.clearMemory(state.namedCashBooks); renderTabs(); renderContent() }.show()
    private fun hideKeyboard(view: View) = (getSystemService(Context.INPUT_METHOD_SERVICE) as InputMethodManager).hideSoftInputFromWindow(view.windowToken, 0)
    private fun formatDecimal(value: BigDecimal): String = RESULT_FORMAT.format(value)
    private fun formatMoney(value: BigDecimal): String = MONEY_FORMAT.format(value)
    private fun toast(value: String) = Toast.makeText(this, value, Toast.LENGTH_SHORT).show()
    private fun dp(value: Int) = (value * resources.displayMetrics.density).toInt()
    private fun vertical(padding: Int = 0) = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(dp(padding), dp(padding), dp(padding), dp(padding)) }
    private fun horizontal(padding: Int = 0) = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL; setPadding(dp(padding), dp(padding), dp(padding), dp(padding)) }
    private fun label(value: String, size: Float, bold: Boolean, color: Int = HydriaColors.text) = TextView(this).apply { text = value; textSize = size; setTextColor(color); if (bold) setTypeface(typeface, android.graphics.Typeface.BOLD) }
    private fun input(hintValue: String) = EditText(this).apply { hint = hintValue; HydriaUi.styleInput(this); maxLines = 1 }
    private fun decimalInput(hintValue: String, value: String) = input(hintValue).apply {
        inputType = InputType.TYPE_CLASS_NUMBER or InputType.TYPE_NUMBER_FLAG_DECIMAL or InputType.TYPE_NUMBER_FLAG_SIGNED
        setText(value)
    }
    private fun primaryButton(value: String, action: (View) -> Unit) = Button(this).apply { text = value; HydriaUi.stylePrimary(this); setOnClickListener(action) }
    private fun secondaryButton(value: String, description: String = value, action: (View) -> Unit) = Button(this).apply { text = value; contentDescription = description; HydriaUi.styleSecondary(this); setOnClickListener(action) }
    private fun fixed(width: Int, height: Int) = LinearLayout.LayoutParams(dp(width), dp(height))
    private fun weighted() = LinearLayout.LayoutParams(0, -1, 1f)
    private fun matchWrap(height: Int? = null, top: Int = 0) = LinearLayout.LayoutParams(-1, height?.let(::dp) ?: -2).apply { topMargin = dp(top) }

    private fun CalculatorTab.labelResource() = when (this) { CalculatorTab.CALCULATIONS -> R.string.calculator_tab_calculations; CalculatorTab.SALARY -> R.string.calculator_tab_salary; CalculatorTab.QUOTE -> R.string.calculator_tab_quote; CalculatorTab.TOTAL -> R.string.calculator_tab_total; CalculatorTab.CASH -> R.string.calculator_tab_cash; CalculatorTab.GPS -> R.string.calculator_tab_gps }
    private fun SalaryMode.labelResource() = when (this) { SalaryMode.STANDARD -> R.string.salary_mode_standard; SalaryMode.PRORATA -> R.string.salary_mode_prorata; SalaryMode.DAILY -> R.string.salary_mode_daily; SalaryMode.GUARDIAN -> R.string.salary_mode_guardian }
    private fun SalaryInputError.messageResource() = when (this) { SalaryInputError.TARGET -> R.string.salary_invalid_target; SalaryInputError.DEPENDENTS -> R.string.salary_invalid_dependents; SalaryInputError.DAYS -> R.string.salary_invalid_days; SalaryInputError.HOURS -> R.string.salary_invalid_hours; SalaryInputError.ORDINARY_REPLACEMENT -> R.string.salary_invalid_replacement }
    private fun ExpressionError.messageResource() = when (this) { ExpressionError.INVALID_REFERENCE -> R.string.calculator_error_invalid_reference; ExpressionError.MISSING_LINE -> R.string.calculator_error_missing_line; ExpressionError.CURRENT_OR_FUTURE_REFERENCE -> R.string.calculator_error_future_reference; ExpressionError.LINE_HAS_ERROR -> R.string.calculator_error_referenced_line; ExpressionError.LINE_NO_RESULT -> R.string.calculator_error_line_no_result; ExpressionError.DIVISION_BY_ZERO -> R.string.calculator_error_division_zero; ExpressionError.NON_NUMERIC -> R.string.calculator_error_non_numeric; ExpressionError.INCOMPLETE_EXPRESSION -> R.string.calculator_error_incomplete; ExpressionError.MISSING_CLOSING_PARENTHESIS -> R.string.calculator_error_parenthesis; ExpressionError.INVALID_NUMBER -> R.string.calculator_error_invalid_number; ExpressionError.FORBIDDEN_CHARACTER -> R.string.calculator_error_forbidden_character; ExpressionError.RESULT_TOO_LARGE -> R.string.calculator_error_result_too_large }

    private fun GpsError.messageResource() = when (this) { GpsError.INVALID_FORMAT -> R.string.gps_error_format; GpsError.ORIENTATION_MISSING -> R.string.gps_error_orientation; GpsError.DUPLICATE_COORDINATE -> R.string.gps_error_duplicate; GpsError.INVALID_MINUTES -> R.string.gps_error_minutes; GpsError.INVALID_SECONDS -> R.string.gps_error_seconds; GpsError.LATITUDE_RANGE -> R.string.gps_error_latitude; GpsError.LONGITUDE_RANGE -> R.string.gps_error_longitude }

    override fun onStart() {
        super.onStart(); activityStarted = true; gpsMapView?.onStart()
    }

    override fun onResume() {
        super.onResume(); activityResumed = true; gpsMapView?.onResume()
    }

    override fun onPause() {
        if (phoneGps != null) { stopPhoneGps(); updatePhoneGpsUi() }
        gpsMapView?.onPause(); activityResumed = false; super.onPause()
    }

    override fun onStop() {
        gpsMapView?.onStop(); activityStarted = false; super.onStop()
    }

    override fun onLowMemory() {
        super.onLowMemory(); gpsMapView?.onLowMemory()
    }

    override fun onDestroy() {
        stopPhoneGps(); releaseGpsMap(); super.onDestroy()
    }

    override fun onSaveInstanceState(outState: Bundle) {
        super.onSaveInstanceState(outState); gpsMapView?.onSaveInstanceState(outState)
    }

    companion object {
        private val RESULT_FORMAT = DecimalFormat("#,##0.######", DecimalFormatSymbols(Locale.FRANCE))
        private val MONEY_FORMAT = DecimalFormat("#,##0.00", DecimalFormatSymbols(Locale.FRANCE))
        private val MADAGASCAR_CENTER = LatLng(-18.7669, 46.8691)
        private const val ONLINE_MAP_STYLE = "https://tiles.openfreemap.org/styles/liberty"
    }
}
