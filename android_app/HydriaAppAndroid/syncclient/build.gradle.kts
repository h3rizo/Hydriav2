import org.jetbrains.compose.desktop.application.dsl.TargetFormat

// Client de synchronisation de fichiers Hydria (PC <-> serveur), type Dropbox.
// Module volontairement INDEPENDANT de :shared et :desktopApp (aucune de leurs classes), mais aligne
// sur les memes versions (Kotlin, Ktor, Compose, coroutines, serialization) pour partager le cache Gradle.
//
//   Fenetre :           gradlew :syncclient:run
//   Executable Windows: gradlew :syncclient:createDistributable  -> build/compose/binaries/main/app/HydriaSync/
//   Ligne de commande : gradlew :syncclient:cli --args="sync"
plugins {
    id("org.jetbrains.kotlin.jvm")
    id("org.jetbrains.kotlin.plugin.serialization")
    id("org.jetbrains.kotlin.plugin.compose")
    id("org.jetbrains.compose")
}

kotlin {
    jvmToolchain(17)
}

dependencies {
    implementation("org.jetbrains.kotlinx:kotlinx-serialization-json:1.8.0")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-core:1.10.2")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-swing:1.10.2")
    implementation("io.ktor:ktor-client-core:3.4.0")
    implementation("io.ktor:ktor-client-cio:3.4.0")
    implementation("io.ktor:ktor-client-content-negotiation:3.4.0")
    implementation("io.ktor:ktor-serialization-kotlinx-json:3.4.0")
    implementation(compose.desktop.currentOs)
    implementation(compose.material3)
    implementation(compose.materialIconsExtended)

    testImplementation(kotlin("test"))
    testImplementation("io.ktor:ktor-client-mock:3.4.0")
}

// JRE embarque : Eclipse Adoptium 17 (et non le JetBrains Runtime qui contient Chromium : installateurs x2).
val packagingJdk = javaToolchains.launcherFor {
    languageVersion.set(JavaLanguageVersion.of(17))
    if (System.getProperty("os.name").startsWith("Windows")) vendor.set(JvmVendorSpec.ADOPTIUM)
}

compose.desktop {
    application {
        mainClass = "mg.hydria.sync.app.FenetreKt"
        javaHome = packagingJdk.get().metadata.installationPath.asFile.absolutePath

        nativeDistributions {
            targetFormats(TargetFormat.Msi, TargetFormat.Exe)
            packageName = "HydriaSync"
            packageVersion = "1.0.0"
            vendor = "Hydria"
            description = "Hydria Sync - synchronisation de fichiers"
            includeAllModules = true
            windows {
                menuGroup = "Hydria"
                shortcut = true
                dirChooser = true
                // UUID fige : NE PAS changer entre versions (mise a jour MSI sur place).
                upgradeUuid = "a3f1c7e2-6b84-4d0e-9c15-2e7f5b8d4a61"
            }
        }
    }
}

// Ligne de commande (sans fenetre) : gradlew :syncclient:cli --args="login --root C:\Hydria --user moi"
tasks.register<JavaExec>("cli") {
    group = "application"
    description = "Client de synchronisation en ligne de commande."
    classpath = sourceSets["main"].runtimeClasspath
    mainClass = "mg.hydria.sync.MainKt"
    standardInput = System.`in`
}
