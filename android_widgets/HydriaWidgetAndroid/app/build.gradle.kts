plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "mg.hydria.widget"
    compileSdk = 34

    defaultConfig {
        applicationId = "mg.hydria.widget"
        minSdk = 26
        targetSdk = 34
        versionCode = 31
        versionName = "1.30"
    }

    buildTypes {
        release {
            isMinifyEnabled = false
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
}

// CAUSE REELLE des erreurs "Unresolved reference" precedentes : le
// gradle daemon a ete configure sur un JDK 25 (tache updateDaemonJvm),
// que Kotlin ne supporte pas encore comme cible et sur lequel il retombe
// silencieusement en JVM_24 â€” en conflit avec compileOptions ci-dessus
// (Java 17), ce que Gradle refuse ("Inconsistent JVM Target Compatibility").
// La tache compileDebugKotlin echouait donc AVANT meme de lire le code
// source, d'ou l'illusion d'un bug dans HydriaApi.kt qui n'a jamais existe.
// Fixer explicitement le toolchain Kotlin sur 17 force la meme cible que
// Java, quel que soit le JDK utilise par le daemon Gradle lui-meme.
kotlin {
    jvmToolchain(17)
}

dependencies {
    implementation("androidx.core:core-ktx:1.13.1")
    implementation("androidx.appcompat:appcompat:1.7.0")
    implementation("com.google.android.material:material:1.12.0")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.8.1")
    // Explicite plutÃ´t que comptÃ© transitivement via appcompat â€” nÃ©cessaire
    // pour lifecycleScope utilisÃ© dans ConfigActivity.kt.
    implementation("androidx.lifecycle:lifecycle-runtime-ktx:2.8.4")
}
