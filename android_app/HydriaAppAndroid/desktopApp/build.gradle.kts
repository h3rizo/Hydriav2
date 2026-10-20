import org.jetbrains.compose.desktop.application.dsl.TargetFormat

// Module Desktop (Phase 4 du plan de migration KMP).
// Compose Multiplatform (JVM Desktop uniquement) + le module :shared.
// Windows : .msi / .exe  ·  Linux : .deb  ·  JRE embarque par jpackage.
plugins {
    id("org.jetbrains.kotlin.jvm")
    id("org.jetbrains.compose")
    id("org.jetbrains.kotlin.plugin.compose")
}

kotlin {
    jvmToolchain(17)
}

dependencies {
    implementation(project(":shared"))
    implementation(compose.desktop.currentOs)
    implementation(compose.material3)
    implementation(compose.materialIconsExtended)
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-core:1.10.2")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-swing:1.10.2")
    // Les facades de :shared exposent leurs resultats en org.json.JSONObject
    // (invisible en transitif car `implementation` dans :shared) ; sur Desktop
    // il n'y a pas d'Android SDK pour le fournir, donc dependance explicite.
    implementation("org.json:json:20240303")
    // QR des factures volumetriques imprimees (meme contenu que l'APK, zxing pur Java).
    implementation("com.google.zxing:core:3.4.1")

    testImplementation(kotlin("test"))
}

// Gabarit de facture de la page web Facturation (hydria.mg), embarque TEL QUEL :
// copie a chaque build depuis backend/static, jamais modifie cote Desktop.
val webInvoiceTemplate by tasks.registering(Copy::class) {
    val staticDir = rootProject.file("../../backend/static")
    from(File(staticDir, "js/print_factures_a4.js"), File(staticDir, "images/mvola-logo.svg"))
    into(layout.buildDirectory.dir("generated/webInvoice/web-invoice"))
    doFirst {
        require(File(staticDir, "js/print_factures_a4.js").isFile) { "Gabarit web introuvable : $staticDir" }
    }
}
sourceSets.main {
    resources.srcDir(layout.buildDirectory.dir("generated/webInvoice"))
}
tasks.named("processResources") { dependsOn(webInvoiceTemplate) }

// JRE embarqué dans les installateurs : Eclipse Adoptium 17. Sans ce choix, Gradle peut prendre
// le JetBrains Runtime, qui contient Chromium (JCEF) : installateurs x2 (≈ 286 Mo au lieu de 143).
// Sous Linux, l'OpenJDK 17 de la distribution convient (pas de JCEF).
val packagingJdk = javaToolchains.launcherFor {
    languageVersion.set(JavaLanguageVersion.of(17))
    if (System.getProperty("os.name").startsWith("Windows")) vendor.set(JvmVendorSpec.ADOPTIUM)
}

compose.desktop {
    application {
        mainClass = "mg.hydria.desktop.MainKt"
        javaHome = packagingJdk.get().metadata.installationPath.asFile.absolutePath

        nativeDistributions {
            targetFormats(TargetFormat.Msi, TargetFormat.Exe, TargetFormat.Deb)
            packageName = "HydriaOperations"
            packageVersion = "2.12.0"
            vendor = "Hydria"
            description = "Hydria Operations - poste de travail"

            // Modules du JRE embarque : jlink/jdeps ne detecte pas les usages
            // par reflexion (sqlite-jdbc -> java.sql, Ktor TLS -> java.naming, ...).
            // includeAllModules garantit qu'aucun module ne manque a l'execution
            // (surcout ~30 Mo, negligeable pour un poste de travail). Symptome si
            // on l'enleve : "Failed to launch JVM" + NoClassDefFoundError java.sql.*.
            includeAllModules = true

            windows {
                menuGroup = "Hydria"
                shortcut = true
                dirChooser = true
                // UUID fige : NE PAS changer entre versions (upgrade MSI in-place).
                upgradeUuid = "5c7b1e42-2e2b-4c1e-9a4a-1b7d9f0a3e11"
                iconFile.set(project.file("icons/hydria.ico"))
            }
            linux {
                packageName = "hydria-operations"
                debMaintainer = "contact@hydria.mg"
                menuGroup = "Hydria"
                shortcut = true
                iconFile.set(project.file("icons/hydria.png"))
            }
        }
    }
}
