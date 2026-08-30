plugins {
    alias(libs.plugins.android.library)
    alias(libs.plugins.kotlin.android)
}

android {
    namespace = "com.naveenhospital.medtrack.core.push"
    compileSdk = 36

    defaultConfig {
        minSdk = 24
    }

    kotlinOptions {
        jvmTarget = "17"
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
}

dependencies {
    implementation(project(":core:data"))
    implementation(project(":core:network"))
    implementation(libs.androidx.core.ktx)
    implementation(libs.androidx.room.runtime)
    implementation(platform(libs.firebase.bom))
    implementation(libs.firebase.messaging)
    testImplementation(libs.androidx.room.testing)
    testImplementation(libs.androidx.test.core)
    testImplementation(libs.coroutines.test)
    testImplementation(libs.junit)
    testImplementation(libs.retrofit.core)
    testImplementation(libs.robolectric)
}
