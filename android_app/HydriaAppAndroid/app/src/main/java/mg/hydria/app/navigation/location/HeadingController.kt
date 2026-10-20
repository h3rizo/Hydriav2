package mg.hydria.app.navigation.location

import android.content.Context
import android.hardware.Sensor
import android.hardware.SensorEvent
import android.hardware.SensorEventListener
import android.hardware.SensorManager
import mg.hydria.shared.navigation.HeadingSmoother

class HeadingController(context: Context, private val onHeading: (Double) -> Unit) : SensorEventListener {
    private val manager = context.getSystemService(Context.SENSOR_SERVICE) as SensorManager
    private val sensor = manager.getDefaultSensor(Sensor.TYPE_ROTATION_VECTOR)
    private val rotation = FloatArray(9)
    private val orientation = FloatArray(3)
    private val smoother = HeadingSmoother()

    fun start() { sensor?.let { manager.registerListener(this, it, SensorManager.SENSOR_DELAY_UI) } }
    fun stop() = manager.unregisterListener(this)

    override fun onSensorChanged(event: SensorEvent) {
        SensorManager.getRotationMatrixFromVector(rotation, event.values)
        SensorManager.getOrientation(rotation, orientation)
        onHeading(smoother.update(Math.toDegrees(orientation[0].toDouble())))
    }

    override fun onAccuracyChanged(sensor: Sensor?, accuracy: Int) = Unit
}

