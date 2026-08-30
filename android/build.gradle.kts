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

val securityDependencyOverrides = mapOf(
    "org.bouncycastle:bcprov-jdk18on" to "1.84",
    "com.google.protobuf:protobuf-java" to "3.25.5",
    "com.google.protobuf:protobuf-java-util" to "3.25.5",
    "com.google.protobuf:protobuf-kotlin" to "3.25.5",
    "io.netty:netty-buffer" to "4.1.136.Final",
    "io.netty:netty-codec" to "4.1.136.Final",
    "io.netty:netty-codec-http" to "4.1.136.Final",
    "io.netty:netty-codec-http2" to "4.1.136.Final",
    "io.netty:netty-codec-socks" to "4.1.136.Final",
    "io.netty:netty-common" to "4.1.136.Final",
    "io.netty:netty-handler" to "4.1.136.Final",
    "io.netty:netty-handler-proxy" to "4.1.136.Final",
    "io.netty:netty-resolver" to "4.1.136.Final",
    "io.netty:netty-transport" to "4.1.136.Final",
    "io.netty:netty-transport-native-unix-common" to "4.1.136.Final",
)

allprojects {
    val projectBuildName = if (path == ":") "root" else path.removePrefix(":").replace(':', '_')
    layout.buildDirectory.set(file("${medtrackBuildRoot.get()}/$projectBuildName"))
    dependencyLocking {
        lockAllConfigurations()
        lockMode.set(LockMode.STRICT)
    }
    configurations.configureEach {
        resolutionStrategy.eachDependency {
            securityDependencyOverrides["${requested.group}:${requested.name}"]?.let { secureVersion ->
                useVersion(secureVersion)
                because("Resolve repository-scanner HIGH/CRITICAL advisories in transitive build and test dependencies")
            }
        }
    }
}
