// Client de synchronisation de fichiers Hydria (PC <-> serveur), type Dropbox.
// Module volontairement INDEPENDANT de :shared et :desktopApp (aucune de leurs classes), mais aligne
// sur les memes versions (Kotlin, Ktor, coroutines, serialization) pour partager le cache Gradle.
// Phase 1 : moteur + ligne de commande (installDist -> build/install/syncclient/bin/syncclient.bat).
plugins {
    id("org.jetbrains.kotlin.jvm")
    id("org.jetbrains.kotlin.plugin.serialization")
    application
}

kotlin {
    jvmToolchain(17)
}

dependencies {
    implementation("org.jetbrains.kotlinx:kotlinx-serialization-json:1.8.0")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-core:1.10.2")
    implementation("io.ktor:ktor-client-core:3.4.0")
    implementation("io.ktor:ktor-client-cio:3.4.0")
    implementation("io.ktor:ktor-client-content-negotiation:3.4.0")
    implementation("io.ktor:ktor-serialization-kotlinx-json:3.4.0")

    testImplementation(kotlin("test"))
    testImplementation("io.ktor:ktor-client-mock:3.4.0")
}

application {
    mainClass = "mg.hydria.sync.MainKt"
    applicationName = "syncclient"
}

// Permet de saisir le mot de passe avec `gradlew :syncclient:run --args="login ..."`.
tasks.named<JavaExec>("run") {
    standardInput = System.`in`
}
