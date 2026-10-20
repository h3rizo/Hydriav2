plugins {
    alias(libs.plugins.android.library)
}

android {
    namespace = "mg.hydria.bienetre.core.model"
    compileSdk = 37

    defaultConfig { minSdk = 26 }
}

