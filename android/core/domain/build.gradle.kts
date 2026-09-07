plugins {
    alias(libs.plugins.android.library)
}

android {
    namespace = "com.naveenhospital.medtrack.core.domain"
    compileSdk = 37

    defaultConfig {
        minSdk = 24
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
}
