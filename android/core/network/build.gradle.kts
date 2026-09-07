plugins {
    alias(libs.plugins.android.library)
}

android {
    namespace = "com.naveenhospital.medtrack.core.network"
    compileSdk = 37

    defaultConfig {
        minSdk = 24
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
}

dependencies {
    implementation(project(":core:domain"))
    implementation(libs.coroutines.android)
    implementation(libs.moshi.kotlin)
    implementation(libs.okhttp.core)
    implementation(libs.retrofit.core)
    implementation(libs.retrofit.moshi)

    testImplementation(libs.junit)
    testImplementation(libs.okhttp.mockwebserver)
}
