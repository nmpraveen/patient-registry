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

rootProject.name = "MedtrackAndroid"

include(":app")
include(":core:designsystem")
include(":core:domain")
include(":core:network")
include(":core:data")
include(":core:push")
include(":feature:auth")
include(":feature:home")
include(":feature:case")
include(":feature:calls")
include(":feature:notifications")
