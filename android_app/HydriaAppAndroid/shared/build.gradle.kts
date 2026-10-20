// -Phydria.desktopOnly=true : cible Android et plugin Android désactivés (aucun Android SDK requis),
// pour construire l'app Desktop sur une machine Linux. Build normal : inchangé (Android + Desktop).
val desktopOnly = providers.gradleProperty("hydria.desktopOnly").orNull == "true"

plugins {
    id("org.jetbrains.kotlin.multiplatform")
    id("org.jetbrains.kotlin.plugin.serialization")
    id("app.cash.sqldelight")
    id("org.jetbrains.compose")
    id("org.jetbrains.kotlin.plugin.compose")
}

if (!desktopOnly) apply(plugin = "com.android.library")

// Module KMP "fondations" (Phase 0 du plan de migration) : reseau (Ktor),
// serialisation (kotlinx.serialization) et base locale (SQLDelight),
// plus les regles metier deja pures (rules/) portees telles quelles.
// Cibles Android + JVM Desktop uniquement pour l'instant (pas iOS).
kotlin {
    jvmToolchain(17)

    if (!desktopOnly) androidTarget()
    jvm("desktop")

    sourceSets {
        val commonMain by getting {
            dependencies {
                implementation("org.jetbrains.kotlinx:kotlinx-serialization-json:1.8.0")
                implementation("org.jetbrains.kotlinx:kotlinx-datetime:0.7.1")
                implementation("org.jetbrains.kotlinx:kotlinx-coroutines-core:1.10.2")
                implementation("io.ktor:ktor-client-core:3.4.0")
                implementation("io.ktor:ktor-client-content-negotiation:3.4.0")
                implementation("io.ktor:ktor-serialization-kotlinx-json:3.4.0")
                implementation("io.ktor:ktor-client-logging:3.4.0")
                implementation("app.cash.sqldelight:runtime:2.2.1")
                implementation("app.cash.sqldelight:coroutines-extensions:2.2.1")
                // Ecran d'intro anime (ui/intro/HydriaIntro.kt), partage Android + Desktop.
                implementation(compose.foundation)
                implementation(compose.components.resources)
            }
        }
        val commonTest by getting {
            dependencies {
                implementation(kotlin("test"))
                implementation("io.ktor:ktor-client-mock:3.4.0")
            }
        }
        // Regroupe le code qui utilise des API JVM "ordinaires" (java.time,
        // org.json), partagees par les deux cibles actuelles (Android + JVM
        // Desktop sont toutes les deux des JVM) sans etre du Kotlin commun
        // pur (java.* n'existe pas en commonMain). Ce n'est pas une
        // limitation KMP definitive : le jour ou ces fonctions seraient
        // recrites avec kotlinx-datetime et kotlinx.serialization a la
        // place de java.time/org.json, elles pourraient redescendre en
        // commonMain pur (utile si iOS/JS rejoint un jour les cibles).
        val jvmCommonMain by creating {
            dependsOn(commonMain)
            dependencies {
                implementation("org.json:json:20240303")
            }
        }
        if (!desktopOnly) {
            getByName("androidMain") {
                dependsOn(jvmCommonMain)
                dependencies {
                    implementation("io.ktor:ktor-client-okhttp:3.4.0")
                    implementation("app.cash.sqldelight:android-driver:2.2.1")
                }
            }
        }
        val desktopMain by getting {
            dependsOn(jvmCommonMain)
            dependencies {
                implementation("io.ktor:ktor-client-cio:3.4.0")
                implementation("app.cash.sqldelight:sqlite-driver:2.2.1")
            }
        }
        // Les edges dependsOn explicites ci-dessus desactivent le template de
        // hierarchie par defaut : desktopTest ne recupere donc pas commonTest
        // automatiquement, on le rebranche ici (kotlin.test + acces au driver
        // JDBC de desktopMain pour tester les facades DB de jvmCommonMain).
        val desktopTest by getting {
            dependsOn(commonTest)
        }
    }
}

if (!desktopOnly) {
    extensions.configure<com.android.build.gradle.LibraryExtension>("android") {
        namespace = "mg.hydria.shared"
        compileSdk = 35

        defaultConfig {
            minSdk = 26
        }

        compileOptions {
            sourceCompatibility = JavaVersion.VERSION_17
            targetCompatibility = JavaVersion.VERSION_17
        }
    }
}

sqldelight {
    databases {
        create("HydriaSharedDatabase") {
            packageName.set("mg.hydria.shared.database")
        }
    }
}

// Package du "Res" genere pour les composeResources (font/drawable de
// l'intro animee) : fixe explicitement pour que les imports dans
// HydriaIntro.kt (mg.hydria.shared.generated.resources.*) soient corrects,
// plutot que de dependre du nom derive par defaut par le plugin.
compose.resources {
    packageOfResClass = "mg.hydria.shared.generated.resources"
}
