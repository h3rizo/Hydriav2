package mg.hydria.app.navigation.model

import org.json.JSONObject

typealias GeoCategory = mg.hydria.shared.navigation.model.GeoCategory
typealias GeoEntity = mg.hydria.shared.navigation.model.GeoEntity
typealias CapturedPosition = mg.hydria.shared.navigation.model.CapturedPosition
typealias PlacementCandidate = mg.hydria.shared.navigation.model.PlacementCandidate
typealias NavigationMode = mg.hydria.shared.navigation.model.NavigationMode
typealias NavigationTarget = mg.hydria.shared.navigation.model.NavigationTarget

data class NavigationConfig(
    val arrivalRadiusMeters: Double = 25.0,
    val accuracyWarningMeters: Double = 30.0,
    val maxEdgeIndicators: Int = 6,
    val canModifyPositions: Boolean = true,
    val canCreateLandmarks: Boolean = true,
) {
    companion object {
        fun fromJson(body: JSONObject): NavigationConfig {
            val value = body.optJSONObject("config") ?: body
            val permissions = value.optJSONObject("permissions") ?: JSONObject()
            return fromServerValues(
                value.optDouble("arrival_radius_m", 25.0), value.optDouble("accuracy_warning_m", 30.0),
                value.optInt("max_edge_indicators", 6), permissions.optBoolean("modify_positions", true),
                permissions.optBoolean("create_landmarks", true),
            )
        }

        fun fromServerValues(
            arrivalRadiusMeters: Double = 25.0,
            accuracyWarningMeters: Double = 30.0,
            maxEdgeIndicators: Int = 6,
            canModifyPositions: Boolean = true,
            canCreateLandmarks: Boolean = true,
        ): NavigationConfig = mg.hydria.shared.navigation.model.NavigationConfig.fromServerValues(
            arrivalRadiusMeters, accuracyWarningMeters, maxEdgeIndicators, canModifyPositions, canCreateLandmarks,
        ).let {
            NavigationConfig(it.arrivalRadiusMeters, it.accuracyWarningMeters, it.maxEdgeIndicators,
                it.canModifyPositions, it.canCreateLandmarks)
        }
    }
}
