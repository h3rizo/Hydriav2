package mg.hydria.app.navigation.model

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Test

class NavigationConfigTest {
    @Test fun defaultsAreSafe() {
        val config = NavigationConfig.fromServerValues()
        assertEquals(25.0, config.arrivalRadiusMeters, 0.0)
        assertEquals(6, config.maxEdgeIndicators)
    }

    @Test fun serverValuesAreClamped() {
        val config = NavigationConfig.fromServerValues(1000.0, 1.0, 99)
        assertEquals(200.0, config.arrivalRadiusMeters, 0.0)
        assertEquals(5.0, config.accuracyWarningMeters, 0.0)
        assertEquals(12, config.maxEdgeIndicators)
    }

    @Test fun permissionsAreReadFromNestedObject() {
        val config = NavigationConfig.fromServerValues(canModifyPositions = false, canCreateLandmarks = false)
        assertFalse(config.canModifyPositions)
        assertFalse(config.canCreateLandmarks)
    }
}
