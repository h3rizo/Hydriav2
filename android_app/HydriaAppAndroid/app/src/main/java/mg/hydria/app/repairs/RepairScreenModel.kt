package mg.hydria.app.repairs

import androidx.lifecycle.ViewModel
import mg.hydria.shared.rules.planning.PlanningViewModelGateway

/** Instance indépendante : réutilise les filtres communs validés du Planning. */
class RepairScreenModel : ViewModel() {
    val filters = PlanningViewModelGateway()
}
