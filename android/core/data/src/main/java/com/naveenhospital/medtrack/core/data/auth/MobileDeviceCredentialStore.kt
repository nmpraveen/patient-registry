package com.naveenhospital.medtrack.core.data.auth

import android.content.Context
import android.content.SharedPreferences
import android.os.Build
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey
import java.security.MessageDigest
import java.util.Locale
import java.util.UUID

data class MobileDeviceCredential(
    val deviceId: String,
    val deviceSecret: String,
)

interface MobileDeviceCredentialStorage {
    val deviceLabel: String
    fun credentialFor(username: String): MobileDeviceCredential?
    fun save(username: String, credential: MobileDeviceCredential): Boolean
    fun clear(username: String): Boolean
}

class MobileDeviceCredentialStore internal constructor(
    private val prefs: SharedPreferences,
    override val deviceLabel: String,
) : MobileDeviceCredentialStorage {
    constructor(context: Context) : this(
        prefs = encryptedPrefs(context.applicationContext),
        deviceLabel = buildDeviceLabel(),
    )

    override fun credentialFor(username: String): MobileDeviceCredential? = synchronized(MUTATION_LOCK) {
        val prefix = keyPrefix(username)
        val deviceId = prefs.getString(prefix + KEY_DEVICE_ID, null)?.takeIf { it.isNotBlank() }
            ?: return@synchronized null
        val deviceSecret = prefs.getString(prefix + KEY_DEVICE_SECRET, null)?.takeIf { it.isNotBlank() }
            ?: return@synchronized null
        val canonicalId = runCatching { UUID.fromString(deviceId).toString() }.getOrNull()
            ?: return@synchronized null
        MobileDeviceCredential(canonicalId, deviceSecret)
    }

    override fun save(username: String, credential: MobileDeviceCredential): Boolean = synchronized(MUTATION_LOCK) {
        val canonicalId = runCatching { UUID.fromString(credential.deviceId).toString() }.getOrNull()
            ?: return@synchronized false
        if (credential.deviceSecret.isBlank() || credential.deviceSecret.length > MAX_SECRET_LENGTH) {
            return@synchronized false
        }
        val prefix = keyPrefix(username)
        prefs.edit()
            .putString(prefix + KEY_DEVICE_ID, canonicalId)
            .putString(prefix + KEY_DEVICE_SECRET, credential.deviceSecret)
            .commit()
    }

    override fun clear(username: String): Boolean = synchronized(MUTATION_LOCK) {
        val prefix = keyPrefix(username)
        prefs.edit()
            .remove(prefix + KEY_DEVICE_ID)
            .remove(prefix + KEY_DEVICE_SECRET)
            .commit()
    }

    private fun keyPrefix(username: String): String {
        val normalized = username.trim().lowercase(Locale.ROOT)
        require(normalized.isNotBlank()) { "Username is required for mobile-device authentication." }
        val digest = MessageDigest.getInstance("SHA-256")
            .digest(normalized.toByteArray(Charsets.UTF_8))
            .joinToString(separator = "") { byte ->
                (byte.toInt() and 0xff).toString(16).padStart(2, '0')
            }
        return "credential_${digest}_"
    }

    private companion object {
        const val PREFS_NAME = "medtrack_mobile_auth"
        const val KEY_DEVICE_ID = "device_id"
        const val KEY_DEVICE_SECRET = "device_secret"
        const val MAX_SECRET_LENGTH = 128
        val MUTATION_LOCK = Any()

        fun encryptedPrefs(context: Context): SharedPreferences {
            val masterKey = MasterKey.Builder(context)
                .setKeyScheme(MasterKey.KeyScheme.AES256_GCM)
                .build()
            return EncryptedSharedPreferences.create(
                context,
                PREFS_NAME,
                masterKey,
                EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
                EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM,
            )
        }

        fun buildDeviceLabel(): String {
            val manufacturer = Build.MANUFACTURER.orEmpty().trim()
            val model = Build.MODEL.orEmpty().trim()
            return listOf(manufacturer, model)
                .filter { it.isNotBlank() }
                .joinToString(separator = " ")
                .ifBlank { "Android device" }
                .take(120)
        }
    }
}

internal object UnavailableMobileDeviceCredentialStorage : MobileDeviceCredentialStorage {
    override val deviceLabel: String = "Android device"
    override fun credentialFor(username: String): MobileDeviceCredential? = null
    override fun save(username: String, credential: MobileDeviceCredential): Boolean = false
    override fun clear(username: String): Boolean = true
}
