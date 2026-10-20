plugins {
    id("com.android.application") version "8.13.2" apply false
    id("com.android.library") version "8.13.2" apply false
    id("org.jetbrains.kotlin.android") version "2.4.20" apply false
    id("org.jetbrains.kotlin.multiplatform") version "2.4.20" apply false
    id("org.jetbrains.kotlin.jvm") version "2.4.20" apply false
    id("org.jetbrains.kotlin.plugin.serialization") version "2.4.20" apply false
    id("org.jetbrains.kotlin.plugin.compose") version "2.4.20" apply false
    // 1.12.0+ embarque des artefacts androidx.compose.*-android qui exigent
    // compileSdk 37 / AGP 9.1+ (constaté au build : echec checkDebugAarMetadata).
    // Ce projet est sur compileSdk 35 / AGP 8.13.2 (max recommande 36) : on
    // reste donc sur 1.11.1, dernier correctif avant ce palier.
    id("org.jetbrains.compose") version "1.11.1" apply false
    id("app.cash.sqldelight") version "2.3.2" apply false
}
