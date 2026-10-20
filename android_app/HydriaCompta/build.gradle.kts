// Versions alignées sur l'app terrain existante (HydriaAppAndroid) pour partager
// le même toolchain JDK 17 / Gradle 9.5 sur ce poste.
plugins {
    id("com.android.application") version "9.3.2" apply false
    id("org.jetbrains.kotlin.android") version "2.2.10" apply false
    id("org.jetbrains.kotlin.plugin.compose") version "2.2.10" apply false
    // Si Android Studio signale une incompatibilité KSP <-> Kotlin lors de la
    // première synchro, aligner cette version sur celle proposée par l'IDE.
    id("com.google.devtools.ksp") version "2.2.10-2.0.2" apply false
}
