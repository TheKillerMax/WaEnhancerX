import java.util.Properties
import java.io.FileInputStream
import java.security.KeyStore
import java.security.MessageDigest

plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.android)
    alias(libs.plugins.compose.compiler)
    alias(libs.plugins.kotlin.serialization)
    alias(libs.plugins.kotlin.kapt)
    alias(libs.plugins.dagger.hilt.android)
}

android {
    val lastV1VersionCode = 17113
    val expectedSigningCertificateSha256 =
        "284325b6f0ca18da5e4c237a6c0618c2a22b08ff8d4a5d11fd12478dad690a84"

    namespace = "com.waenhancer.app"
    compileSdk = 36
    
    defaultConfig {
        val configuredVersionCode =
            project.findProperty("VERSION_CODE")?.toString()?.toInt() ?: 20100

        applicationId = "com.waenhancer"
        minSdk = 24
        targetSdk = 36
        versionCode = configuredVersionCode
        versionName = project.findProperty("VERSION_NAME")?.toString() ?: "1.0.0"

        require(configuredVersionCode > lastV1VersionCode) {
            "VERSION_CODE must be greater than the latest v1 version code ($lastV1VersionCode) to support upgrades."
        }
    }

    signingConfigs {
        create("releaseConfig") {
            val keystorePropertiesFile = rootProject.file("local.properties")
            val keystoreProperties = Properties()
            if (keystorePropertiesFile.exists()) {
                keystoreProperties.load(FileInputStream(keystorePropertiesFile))
            }
            val androidStoreFile = (project.findProperty("androidStoreFile") as? String)
                ?: keystoreProperties.getProperty("androidStoreFile") ?: "key.jks"
            val keyFile = rootProject.file(androidStoreFile)
            require(keyFile.isFile) {
                "Signing keystore not found at ${keyFile.absolutePath}. All builds must use the v1 signing key."
            }

            val signingStorePassword = (project.findProperty("androidStorePassword") as? String)
                ?: keystoreProperties.getProperty("androidStorePassword") ?: "123456"
            val signingKeyAlias = (project.findProperty("androidKeyAlias") as? String)
                ?: keystoreProperties.getProperty("androidKeyAlias") ?: "my-alias"
            val signingKeyPassword = (project.findProperty("androidKeyPassword") as? String)
                ?: keystoreProperties.getProperty("androidKeyPassword") ?: "123456"

            val keyStore = KeyStore.getInstance(KeyStore.getDefaultType())
            keyFile.inputStream().use { keyStore.load(it, signingStorePassword.toCharArray()) }
            val certificate = requireNotNull(keyStore.getCertificate(signingKeyAlias)) {
                "Signing alias '$signingKeyAlias' was not found in ${keyFile.absolutePath}."
            }
            val certificateSha256 = MessageDigest.getInstance("SHA-256")
                .digest(certificate.encoded)
                .joinToString("") { "%02x".format(it) }
            require(certificateSha256 == expectedSigningCertificateSha256) {
                "Signing certificate does not match v1. Expected $expectedSigningCertificateSha256, got $certificateSha256."
            }

            storeFile = keyFile
            storePassword = signingStorePassword
            keyAlias = signingKeyAlias
            keyPassword = signingKeyPassword
            enableV1Signing = true
            enableV2Signing = true
            enableV3Signing = true
        }
    }

    buildTypes {
        debug {
            signingConfig = signingConfigs.getByName("releaseConfig")
        }
        release {
            isMinifyEnabled = true
            isShrinkResources = true
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
            signingConfig = signingConfigs.getByName("releaseConfig")
        }
    }
    
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    
    buildFeatures {
        compose = true
    }

    packaging {
        resources {
            excludes += "/META-INF/{AL2.0,LGPL2.1}"
        }
        jniLibs {
            useLegacyPackaging = false
        }
    }

    applicationVariants.all {
        val variant = this
        variant.outputs.forEach {
            val output = it as? com.android.build.gradle.api.ApkVariantOutput
            if (output != null) {
                val suffix = if (variant.buildType.name == "debug") "_debug" else "_release"
                output.outputFileName = "WaEnhancerX-v${variant.versionName}${suffix}.apk"
            }
        }
    }
}

kotlin {
    jvmToolchain(17)
}

dependencies {
    // Android/Compose standard dependencies
    val composeBom = platform(libs.androidx.compose.bom)
    implementation(composeBom)
    androidTestImplementation(composeBom)

    implementation(libs.androidx.core.ktx)
    implementation(libs.androidx.core.splashscreen)
    implementation(libs.androidx.lifecycle.runtime.ktx)
    implementation(libs.androidx.activity.compose)
    implementation(libs.androidx.lifecycle.runtime.compose)
    implementation(libs.androidx.lifecycle.viewmodel.compose)

    implementation(libs.androidx.compose.ui)
    implementation(libs.androidx.compose.ui.tooling.preview)
    implementation(libs.androidx.compose.material3)
    implementation(libs.androidx.compose.icons.core)
    implementation("androidx.compose.material:material-icons-extended")
    debugImplementation(libs.androidx.compose.ui.tooling)
    androidTestImplementation(libs.androidx.compose.ui.test.junit4)
    debugImplementation(libs.androidx.compose.ui.test.manifest)

    // Navigation
    implementation(libs.androidx.navigation3.ui)
    implementation(libs.androidx.navigation3.runtime)
    implementation(libs.androidx.hilt.navigation.compose)
    implementation(libs.androidx.lifecycle.viewmodel.navigation3)

    // Hilt
    implementation(libs.hilt.android)
    kapt(libs.hilt.compiler)
    
    // Serialization
    implementation(libs.kotlinx.serialization.json)

    // DataStore Preferences
    implementation(libs.androidx.datastore.preferences)

    // External dependencies needed on app classpath for Hilt annotation processing
    implementation(libs.retrofit.core)
    implementation(libs.okhttp.core)
    implementation(libs.markwon.core)
    implementation(libs.markwon.html)
    implementation(libs.room.runtime)

    // Xposed Framework & DexKit Hooking Engine
    compileOnly(libs.libxposed.legacy)
    implementation(libs.dexkit)

    // Submodule Licensing Library (Private Submodule)
    implementation(project(":licensing"))


    // Testing
    testImplementation(libs.junit)
    testImplementation(libs.kotlinx.coroutines.test)
    androidTestImplementation(libs.androidx.test.core)
    androidTestImplementation(libs.androidx.test.ext.junit)
    androidTestImplementation(libs.androidx.test.runner)
    androidTestImplementation(libs.androidx.test.espresso.core)
}

kapt {
    correctErrorTypes = true
    arguments {
        arg("dagger.hilt.android.internal.disableAndroidSuperclassValidation", "true")
    }
}
