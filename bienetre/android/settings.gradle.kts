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

rootProject.name = "BienetreHydria"

include(":app")
include(":core:model")
include(":core:network")
include(":core:designsystem")
include(":core:preferences")
include(":feature:auth")
include(":feature:dashboard")
include(":feature:profile")
include(":feature:meals")
include(":feature:shopping")
include(":feature:fitness")
include(":feature:progress")
include(":feature:household")
