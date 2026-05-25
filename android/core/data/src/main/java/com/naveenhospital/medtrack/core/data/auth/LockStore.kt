package com.naveenhospital.medtrack.core.data.auth

import android.content.Context
import android.content.SharedPreferences
import android.util.Base64
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey
import java.security.MessageDigest
import java.security.SecureRandom

class LockStore internal constructor(
    private val prefs: SharedPreferences,
) {
    constructor(context: Context) : this(encryptedPrefs(context.applicationContext))

    fun hasPattern(): Boolean =
        !prefs.getString(KEY_PATTERN_HASH, null).isNullOrBlank() &&
            !prefs.getString(KEY_PATTERN_SALT, null).isNullOrBlank()

    fun isBiometricEnabled(): Boolean = prefs.getBoolean(KEY_BIOMETRIC_ENABLED, false)

    fun hasAnyLock(): Boolean = hasPattern() || isBiometricEnabled()

    fun savePattern(pattern: List<Int>) {
        require(pattern.size >= MIN_PATTERN_LENGTH) { "Use at least $MIN_PATTERN_LENGTH dots." }
        val salt = ByteArray(16).also { secureRandom.nextBytes(it) }
        prefs.edit()
            .putString(KEY_PATTERN_SALT, salt.encode())
            .putString(KEY_PATTERN_HASH, hashPattern(pattern, salt).encode())
            .apply()
    }

    fun verifyPattern(pattern: List<Int>): Boolean {
        val salt = prefs.getString(KEY_PATTERN_SALT, null)?.decode() ?: return false
        val expected = prefs.getString(KEY_PATTERN_HASH, null)?.decode() ?: return false
        return MessageDigest.isEqual(hashPattern(pattern, salt), expected)
    }

    fun setBiometricEnabled(enabled: Boolean) {
        prefs.edit().putBoolean(KEY_BIOMETRIC_ENABLED, enabled).apply()
    }

    fun clear() {
        prefs.edit().clear().apply()
    }

    private fun hashPattern(pattern: List<Int>, salt: ByteArray): ByteArray {
        val digest = MessageDigest.getInstance("SHA-256")
        digest.update(salt)
        digest.update(pattern.joinToString(separator = "-").toByteArray(Charsets.UTF_8))
        return digest.digest()
    }

    private fun ByteArray.encode(): String =
        Base64.encodeToString(this, Base64.NO_WRAP)

    private fun String.decode(): ByteArray =
        Base64.decode(this, Base64.NO_WRAP)

    companion object {
        const val MIN_PATTERN_LENGTH = 4
        private const val PREFS_NAME = "medtrack_lock"
        private const val KEY_PATTERN_SALT = "pattern_salt"
        private const val KEY_PATTERN_HASH = "pattern_hash"
        private const val KEY_BIOMETRIC_ENABLED = "biometric_enabled"
        private val secureRandom = SecureRandom()

        private fun encryptedPrefs(context: Context): SharedPreferences {
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
    }
}
