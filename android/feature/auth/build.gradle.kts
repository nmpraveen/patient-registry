plugins {
    alias(libs.plugins.compose.compiler)
    alias(libs.plugins.android.library)
}

android {
    namespace = "com.naveenhospital.medtrack.feature.auth"
    compileSdk = 37

    defaultConfig {
        minSdk = 24
    }

    buildFeatures {
        compose = true
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
}

dependencies {
    implementation(project(":core:designsystem"))
    implementation(project(":core:domain"))
    testImplementation(libs.junit)
}
