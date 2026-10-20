package mg.hydria.app.planning

import androidx.lifecycle.ViewModel
import mg.hydria.shared.rules.planning.PlanningViewModelGateway

/** Seul le cycle de vie est Android ; filtres, agenda et validation sont communs. */
class PlanningScreenModel : ViewModel() {
    val planning = PlanningViewModelGateway()
}
