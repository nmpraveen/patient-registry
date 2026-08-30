import java.util.Properties
import org.gradle.api.GradleException

plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.android)
    alias(libs.plugins.ksp)
    alias(libs.plugins.hilt.android)
}

val hasFirebaseConfig = file("google-services.json").exists()
val versionProperties = Properties().apply {
    rootProject.file("version.properties").inputStream().use(::load)
}
val medtrackVersionCode = versionProperties.getProperty("VERSION_CODE")?.toIntOrNull()
    ?: throw GradleException("android/version.properties must contain an integer VERSION_CODE.")
val medtrackVersionName = versionProperties.getProperty("VERSION_NAME")?.takeIf { it.isNotBlank() }
    ?: throw GradleException("android/version.properties must contain VERSION_NAME.")

fun externalValue(name: String) = providers.gradleProperty(name)
    .orElse(providers.environmentVariable(name))
    .orNull
    ?.takeIf { it.isNotBlank() }

val signingStoreFile = externalValue("MEDTRACK_SIGNING_STORE_FILE")
val signingStorePassword = externalValue("MEDTRACK_SIGNING_STORE_PASSWORD")
val signingKeyAlias = externalValue("MEDTRACK_SIGNING_KEY_ALIAS")
val signingKeyPassword = externalValue("MEDTRACK_SIGNING_KEY_PASSWORD")
val signingValues = listOf(signingStoreFile, signingStorePassword, signingKeyAlias, signingKeyPassword)
val hasExternalSigning = signingValues.all { it != null }
if (signingValues.any { it != null } && !hasExternalSigning) {
    throw GradleException("Release signing is partially configured. Supply all four MEDTRACK_SIGNING_* values or none.")
}

val legacyDevApiBaseUrl = providers.gradleProperty("MEDTRACK_API_BASE_URL")
val devApiBaseUrl = providers.gradleProperty("MEDTRACK_DEV_API_BASE_URL")
    .orElse(providers.environmentVariable("MEDTRACK_DEV_API_BASE_URL"))
    .orElse(legacyDevApiBaseUrl)
    .getOrElse("http://10.0.2.2:8000/")
val stageApiBaseUrl = providers.gradleProperty("MEDTRACK_STAGE_API_BASE_URL")
    .orElse(providers.environmentVariable("MEDTRACK_STAGE_API_BASE_URL"))
    .getOrElse("https://medtrack-stage.invalid/")
val prodApiBaseUrl = providers.gradleProperty("MEDTRACK_PROD_API_BASE_URL")
    .orElse(providers.environmentVariable("MEDTRACK_PROD_API_BASE_URL"))
    .getOrElse("https://book.naveenhospital.net/")

if (hasFirebaseConfig) {
    apply(plugin = "com.google.gms.google-services")
    apply(plugin = "com.google.firebase.crashlytics")
}

android {
    namespace = "com.naveenhospital.medtrack"
    compileSdk = 36

    defaultConfig {
        applicationId = "com.naveenhospital.medtrack"
        minSdk = 24
        targetSdk = 36
        versionCode = medtrackVersionCode
        versionName = medtrackVersionName
    }

    flavorDimensions += "environment"
    productFlavors {
        create("dev") {
            dimension = "environment"
            applicationIdSuffix = ".dev"
            versionNameSuffix = "-dev"
            buildConfigField("String", "MEDTRACK_API_BASE_URL", "\"$devApiBaseUrl\"")
            manifestPlaceholders["medtrackApiBaseUrl"] = devApiBaseUrl
        }
        create("stage") {
            dimension = "environment"
            applicationIdSuffix = ".stage"
            versionNameSuffix = "-stage"
            buildConfigField("String", "MEDTRACK_API_BASE_URL", "\"$stageApiBaseUrl\"")
            manifestPlaceholders["medtrackApiBaseUrl"] = stageApiBaseUrl
        }
        create("prod") {
            dimension = "environment"
            buildConfigField("String", "MEDTRACK_API_BASE_URL", "\"$prodApiBaseUrl\"")
            manifestPlaceholders["medtrackApiBaseUrl"] = prodApiBaseUrl
        }
    }

    signingConfigs {
        if (hasExternalSigning) {
            create("externalRelease") {
                storeFile = file(signingStoreFile!!)
                storePassword = signingStorePassword
                keyAlias = signingKeyAlias
                keyPassword = signingKeyPassword
            }
        }
    }

    buildTypes {
        getByName("debug") {
            isDebuggable = true
        }
        getByName("release") {
            isDebuggable = false
            isMinifyEnabled = false
            if (hasExternalSigning) {
                signingConfig = signingConfigs.getByName("externalRelease")
            }
        }
    }

    buildFeatures {
        buildConfig = true
        compose = true
    }

    composeOptions {
        kotlinCompilerExtensionVersion = libs.versions.composeCompiler.get()
    }

    kotlinOptions {
        jvmTarget = "17"
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    packaging {
        resources {
            excludes += "/META-INF/{AL2.0,LGPL2.1}"
        }
    }

    lint {
        abortOnError = true
        checkDependencies = true
        checkReleaseBuilds = true
        disable += setOf(
            "AndroidGradlePluginVersion",
            "GradleDependency",
            "VectorPath",
        )
        htmlReport = true
        textReport = true
        xmlReport = true
    }
}

androidComponents {
    beforeVariants(selector().withBuildType("debug")) { variantBuilder ->
        if (variantBuilder.productFlavors.any { (_, flavor) -> flavor == "prod" }) {
            variantBuilder.enable = false
        }
    }
}

tasks.register("verifyReleaseMetadata") {
    group = "verification"
    description = "Verifies monotonic Play-compatible Android release metadata."
    doLast {
        check(medtrackVersionCode in 1..2_100_000_000) { "VERSION_CODE is outside the Play-supported range." }
        check(Regex("\\d{4}\\.\\d{1,2}\\.\\d{1,2}\\.\\d+").matches(medtrackVersionName)) {
            "VERSION_NAME must use YYYY.M.D.REVISION."
        }
    }
}

tasks.register("verifyProdSigning") {
    group = "verification"
    description = "Fails unless the external production signing identity is fully configured."
    doLast {
        check(hasExternalSigning) {
            "Production signing is not configured. Use unsignedReleaseArtifacts for review builds."
        }
    }
}

tasks.register("unsignedReleaseArtifacts") {
    group = "build"
    description = "Builds unsigned production release APK and AAB artifacts for review."
    dependsOn("verifyReleaseMetadata", "assembleProdRelease", "bundleProdRelease")
}

tasks.register("bundleProdForPlay") {
    group = "build"
    description = "Builds a production AAB only after external signing is verified."
    dependsOn("verifyProdSigning", "bundleProdRelease")
}

tasks.matching { it.name == "bundleProdRelease" }.configureEach {
    mustRunAfter("verifyProdSigning", "verifyReleaseMetadata")
}

dependencies {
    implementation(project(":core:designsystem"))
    implementation(project(":core:domain"))
    implementation(project(":core:data"))
    implementation(project(":core:network"))
    implementation(project(":core:push"))
    implementation(project(":feature:auth"))
    implementation(project(":feature:home"))
    implementation(project(":feature:case"))
    implementation(project(":feature:calls"))
    implementation(project(":feature:notifications"))

    implementation(libs.androidx.activity.compose)
    implementation(libs.androidx.biometric)
    implementation(libs.androidx.core.ktx)
    implementation(libs.androidx.lifecycle.runtime.compose)
    implementation(libs.androidx.lifecycle.runtime.ktx)
    implementation(libs.androidx.navigation.compose)
    implementation(platform(libs.compose.bom))
    implementation(libs.compose.material3)
    implementation(libs.compose.ui)
    implementation(libs.compose.ui.tooling.preview)
    implementation(libs.paging.compose)
    implementation(platform(libs.firebase.bom))
    implementation(libs.firebase.crashlytics)
    implementation(libs.hilt.android)
    ksp(libs.hilt.compiler)

    debugImplementation(libs.compose.ui.tooling)
}
