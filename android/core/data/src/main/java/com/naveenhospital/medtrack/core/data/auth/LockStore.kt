package com.naveenhospital.medtrack.core.data.auth

import android.content.Context
import android.content.SharedPreferences
import android.util.Base64
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey
import java.security.MessageDigest
import java.security.SecureRandom
import javax.crypto.SecretKeyFactory
import javax.crypto.spec.PBEKeySpec
import kotlin.math.min

sealed interface LockVerificationResult {
    data object Success : LockVerificationResult
    data object Invalid : LockVerificationResult
    data class Throttled(val retryAfterMillis: Long) : LockVerificationResult
    data object ReauthenticationRequired : LockVerificationResult
}

/** Account-owned local lock state protected by Android Keystore encrypted preferences. */
class LockStore internal constructor(
    private val prefs: SharedPreferences,
    private val nowMillis: () -> Long = System::currentTimeMillis,
) {
    constructor(context: Context) : this(encryptedPrefs(context.applicationContext))

    @Volatile
    private var activeAccountId: String? = null

    init {
        discardLegacyUnownedLock()
    }

    fun activateAccount(accountId: String?) {
        activeAccountId = accountId?.trim()?.takeIf { it.isNotEmpty() }
    }

    fun activeAccountId(): String? = activeAccountId

    fun hasPattern(): Boolean = activePrefix()?.let { prefix ->
        !prefs.getString(prefix + KEY_PATTERN_HASH, null).isNullOrBlank() &&
            !prefs.getString(prefix + KEY_PATTERN_SALT, null).isNullOrBlank()
    } ?: false

    fun isBiometricEnabled(): Boolean =
        activePrefix()?.let { prefs.getBoolean(it + KEY_BIOMETRIC_ENABLED, false) } ?: false

    fun hasAnyLock(): Boolean = hasPattern() || isBiometricEnabled()

    fun savePattern(pattern: List<Int>) {
        require(pattern.size >= MIN_PATTERN_LENGTH) { "Use at least $MIN_PATTERN_LENGTH dots." }
        val prefix = requireActivePrefix()
        val salt = ByteArray(SALT_BYTES).also { secureRandom.nextBytes(it) }
        requireCommitted(
            prefs.edit()
                .putString(prefix + KEY_PATTERN_SALT, salt.encode())
                .putString(prefix + KEY_PATTERN_HASH, derivePattern(pattern, salt).encode())
                .putInt(prefix + KEY_FAILED_ATTEMPTS, 0)
                .putLong(prefix + KEY_LOCKOUT_UNTIL, 0L)
                .commit(),
            "Unable to persist the MEDTRACK lock.",
        )
    }

    fun verifyPattern(pattern: List<Int>): LockVerificationResult {
        val prefix = activePrefix() ?: return LockVerificationResult.ReauthenticationRequired
        val now = nowMillis()
        val lockoutUntil = prefs.getLong(prefix + KEY_LOCKOUT_UNTIL, 0L)
        if (lockoutUntil > now) {
            return LockVerificationResult.Throttled(lockoutUntil - now)
        }
        val salt = prefs.getString(prefix + KEY_PATTERN_SALT, null)?.decode()
            ?: return LockVerificationResult.ReauthenticationRequired
        val expected = prefs.getString(prefix + KEY_PATTERN_HASH, null)?.decode()
            ?: return LockVerificationResult.ReauthenticationRequired
        if (MessageDigest.isEqual(derivePattern(pattern, salt), expected)) {
            if (!prefs.edit()
                    .putInt(prefix + KEY_FAILED_ATTEMPTS, 0)
                    .putLong(prefix + KEY_LOCKOUT_UNTIL, 0L)
                    .commit()
            ) {
                activeAccountId = null
                return LockVerificationResult.ReauthenticationRequired
            }
            return LockVerificationResult.Success
        }

        val failedAttempts = prefs.getInt(prefix + KEY_FAILED_ATTEMPTS, 0) + 1
        if (failedAttempts >= MAX_FAILED_ATTEMPTS) {
            clearAccount(activeAccountId ?: return LockVerificationResult.ReauthenticationRequired)
            return LockVerificationResult.ReauthenticationRequired
        }
        val delayMillis = throttleDelayMillis(failedAttempts)
        if (!prefs.edit()
                .putInt(prefix + KEY_FAILED_ATTEMPTS, failedAttempts)
                .putLong(prefix + KEY_LOCKOUT_UNTIL, if (delayMillis > 0) now + delayMillis else 0L)
                .commit()
        ) {
            activeAccountId = null
            return LockVerificationResult.ReauthenticationRequired
        }
        return if (delayMillis > 0) {
            LockVerificationResult.Throttled(delayMillis)
        } else {
            LockVerificationResult.Invalid
        }
    }

    fun setBiometricEnabled(enabled: Boolean) {
        val prefix = requireActivePrefix()
        requireCommitted(
            prefs.edit().putBoolean(prefix + KEY_BIOMETRIC_ENABLED, enabled).commit(),
            "Unable to persist biometric lock state.",
        )
    }

    fun clearActiveAccount() {
        activeAccountId?.let(::clearAccount)
        activeAccountId = null
    }

    fun clearAccount(accountId: String) {
        val prefix = accountPrefix(accountId)
        val editor = prefs.edit()
        prefs.all.keys.filter { it.startsWith(prefix) }.forEach(editor::remove)
        if (activeAccountId == accountId) activeAccountId = null
        check(editor.commit()) { "Unable to clear MEDTRACK lock state." }
    }

    fun deactivate() {
        activeAccountId = null
    }

    private fun requireCommitted(committed: Boolean, message: String) {
        if (!committed) {
            activeAccountId = null
            throw IllegalStateException(message)
        }
    }

    private fun derivePattern(pattern: List<Int>, salt: ByteArray): ByteArray {
        val password = pattern.joinToString(separator = "-").toCharArray()
        return try {
            val spec = PBEKeySpec(password, salt, PBKDF2_ITERATIONS, DERIVED_KEY_BITS)
            try {
                SecretKeyFactory.getInstance("PBKDF2WithHmacSHA256").generateSecret(spec).encoded
            } finally {
                spec.clearPassword()
            }
        } finally {
            password.fill('\u0000')
        }
    }

    private fun activePrefix(): String? = activeAccountId?.let(::accountPrefix)

    private fun requireActivePrefix(): String =
        activePrefix() ?: error("A verified account must be active before configuring a local lock.")

    private fun discardLegacyUnownedLock() {
        if (prefs.getBoolean(KEY_OWNERSHIP_MIGRATED, false)) return
        check(
            prefs.edit()
                .remove(KEY_PATTERN_SALT)
                .remove(KEY_PATTERN_HASH)
                .remove(KEY_BIOMETRIC_ENABLED)
                .putBoolean(KEY_OWNERSHIP_MIGRATED, true)
                .commit(),
        ) { "Unable to migrate MEDTRACK lock ownership." }
    }

    private fun throttleDelayMillis(failedAttempts: Int): Long {
        if (failedAttempts < THROTTLE_AFTER_ATTEMPTS) return 0L
        val exponent = min(failedAttempts - THROTTLE_AFTER_ATTEMPTS, 4)
        return min(BASE_THROTTLE_MILLIS shl exponent, MAX_THROTTLE_MILLIS)
    }

    private fun ByteArray.encode(): String = Base64.encodeToString(this, Base64.NO_WRAP)

    private fun String.decode(): ByteArray = Base64.decode(this, Base64.NO_WRAP)

    companion object {
        const val MIN_PATTERN_LENGTH = 4
        const val MAX_FAILED_ATTEMPTS = 10
        private const val THROTTLE_AFTER_ATTEMPTS = 5
        private const val BASE_THROTTLE_MILLIS = 30_000L
        private const val MAX_THROTTLE_MILLIS = 5 * 60_000L
        private const val PBKDF2_ITERATIONS = 210_000
        private const val DERIVED_KEY_BITS = 256
        private const val SALT_BYTES = 16
        private const val PREFS_NAME = "medtrack_lock"
        private const val KEY_PATTERN_SALT = "pattern_salt"
        private const val KEY_PATTERN_HASH = "pattern_hash"
        private const val KEY_BIOMETRIC_ENABLED = "biometric_enabled"
        private const val KEY_FAILED_ATTEMPTS = "failed_attempts"
        private const val KEY_LOCKOUT_UNTIL = "lockout_until"
        private const val KEY_OWNERSHIP_MIGRATED = "owner_lock_migration_complete"
        private val secureRandom = SecureRandom()

        private fun accountPrefix(accountId: String): String {
            val digest = MessageDigest.getInstance("SHA-256")
                .digest(accountId.toByteArray(Charsets.UTF_8))
            return "account_${Base64.encodeToString(digest, Base64.NO_WRAP or Base64.URL_SAFE)}_"
        }

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
