plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("org.jetbrains.compose")
    id("org.jetbrains.kotlin.plugin.compose")
}

android {
    namespace = "mg.hydria.app"
    compileSdk = 35

    defaultConfig {
        applicationId = "mg.hydria.app"
        minSdk = 26
        targetSdk = 34
        versionCode = 57
        versionName = "2.12.0"
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            signingConfig = signingConfigs.getByName("debug")
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    // Ecran d'intro anime (IntroActivity, avant l'app a base d'Activities existante).
    buildFeatures {
        compose = true
    }
}

// Le daemon Gradle du poste est configure sur JDK 25, non pris en charge
// par le compilateur Kotlin 1.9. Forcer le toolchain 17 evite le crash du
// cache incremental et garde les cibles Java/Kotlin coherentes.
kotlin {
    jvmToolchain(17)
}

dependencies {
    implementation(project(":shared"))
    implementation("com.journeyapps:zxing-android-embedded:4.3.0")
    implementation("androidx.core:core-ktx:1.13.1")
    implementation("androidx.appcompat:appcompat:1.7.0")
    implementation("androidx.activity:activity-ktx:1.9.0")
    implementation("com.google.android.material:material:1.12.0")
    implementation("androidx.swiperefreshlayout:swiperefreshlayout:1.1.0")
    implementation("org.maplibre.gl:android-sdk:13.6.0")
    // Ecran d'intro anime (IntroActivity -> HydriaIntro de :shared)
    implementation("androidx.activity:activity-compose:1.9.0")
    implementation(compose.foundation)
    testImplementation("junit:junit:4.13.2")
    testImplementation("org.json:json:20240303")
}
