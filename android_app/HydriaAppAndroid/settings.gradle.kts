pluginManagement {
    repositories {
        google()
        mavenCentral()
        gradlePluginPortal()
    }
}
dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        google()
        mavenCentral()
    }
}

rootProject.name = "HydriaApp"
// -Phydria.desktopOnly=true : build Desktop seul (Linux/WSL sans Android SDK), sans le module Android.
if (providers.gradleProperty("hydria.desktopOnly").orNull != "true") {
    include(":app")
}
include(":shared")
include(":desktopApp")
