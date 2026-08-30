import java.io.File
import org.gradle.api.artifacts.dsl.LockMode

plugins {
    alias(libs.plugins.android.application) apply false
    alias(libs.plugins.android.library) apply false
    alias(libs.plugins.kotlin.android) apply false
    alias(libs.plugins.ksp) apply false
    alias(libs.plugins.google.services) apply false
    alias(libs.plugins.firebase.crashlytics) apply false
    alias(libs.plugins.hilt.android) apply false
}

val medtrackBuildRoot = providers.environmentVariable("MEDTRACK_ANDROID_BUILD_DIR")
    .orElse(
        providers.provider {
            File(rootDir, ".build").absolutePath
        },
    )

allprojects {
    val projectBuildName = if (path == ":") "root" else path.removePrefix(":").replace(':', '_')
    layout.buildDirectory.set(file("${medtrackBuildRoot.get()}/$projectBuildName"))
    dependencyLocking {
        lockAllConfigurations()
        lockMode.set(LockMode.STRICT)
    }
}
