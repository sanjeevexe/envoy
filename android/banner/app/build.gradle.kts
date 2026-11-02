plugins {
    id("com.android.application")
}

android {
    namespace = "ai.envoy.banner"
    compileSdk {
        version = release(37) { minorApiLevel = 2 }
    }

    defaultConfig {
        applicationId = "ai.envoy.banner"
        minSdk = 29
        targetSdk = 36
        versionCode = 2  // Envoy reinstalls the banner when the built one is newer than the phone's (devices/phone.py)
        versionName = "1.1"
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
}
