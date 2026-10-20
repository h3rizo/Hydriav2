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

rootProject.name = "LogistiqueAndroid"
include(":app")
include(":core:model")
include(":core:database")
include(":core:network")
include(":core:sync")
include(":feature:main")
