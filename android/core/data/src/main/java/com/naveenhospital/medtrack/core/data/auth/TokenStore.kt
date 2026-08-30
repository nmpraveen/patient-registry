package com.naveenhospital.medtrack.core.data.auth

import android.content.Context
import android.content.SharedPreferences
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey
import java.util.UUID

data class AccountSessionIdentity(
    val accountId: String,
    val incarnation: String,
)

class TokenStore internal constructor(
    private val prefs: SharedPreferences,
) {
    constructor(context: Context) : this(encryptedPrefs(context.applicationContext))

    @Volatile
    private var activeAccessToken: String? = null

    init {
        synchronized(MUTATION_LOCK) {
            val accountId = prefs.getString(KEY_ACCOUNT_ID, null)?.takeIf { it.isNotBlank() }
            val refreshToken = prefs.getString(KEY_REFRESH_TOKEN, null)?.takeIf { it.isNotBlank() }
            val incarnation = prefs.getString(KEY_SESSION_INCARNATION, null)?.takeIf { it.isNotBlank() }
            if (accountId != null && refreshToken != null && incarnation == null) {
                check(
                    prefs.edit()
                        .putString(KEY_SESSION_INCARNATION, UUID.randomUUID().toString())
                        .commit(),
                ) { "Unable to migrate the MEDTRACK session identity." }
            }
        }
    }

    val accessToken: String?
        get() = activeAccessToken

    fun accountId(): String? = prefs.getString(KEY_ACCOUNT_ID, null)?.takeIf { it.isNotBlank() }

    fun refreshToken(): String? = prefs.getString(KEY_REFRESH_TOKEN, null)

    fun hasRefreshToken(): Boolean = sessionIdentity() != null && !refreshToken().isNullOrBlank()

    fun sessionIdentity(): AccountSessionIdentity? = synchronized(MUTATION_LOCK) {
        val accountId = accountId() ?: return@synchronized null
        val incarnation = prefs.getString(KEY_SESSION_INCARNATION, null)
            ?.takeIf { it.isNotBlank() }
            ?: return@synchronized null
        AccountSessionIdentity(accountId, incarnation)
    }

    fun sessionIdentityFor(accountId: String): AccountSessionIdentity? =
        sessionIdentity()?.takeIf { it.accountId == accountId }

    fun isCurrent(identity: AccountSessionIdentity): Boolean =
        sessionIdentity() == identity

    fun accessTokenFor(accountId: String): String? =
        activeAccessToken?.takeIf { this.accountId() == accountId }

    fun accessTokenFor(identity: AccountSessionIdentity): String? =
        activeAccessToken?.takeIf { isCurrent(identity) }

    fun refreshTokenFor(accountId: String): String? =
        refreshToken()?.takeIf { this.accountId() == accountId }

    fun refreshTokenFor(identity: AccountSessionIdentity): String? =
        refreshToken()?.takeIf { isCurrent(identity) }

    fun commitVerifiedSession(accountId: String, access: String, refresh: String?): Boolean =
        synchronized(MUTATION_LOCK) {
            require(accountId.isNotBlank()) { "Verified account ID is required." }
            require(access.isNotBlank()) { "Access token is required." }
            val existingAccountId = this.accountId()
            val resolvedRefresh = refresh?.takeIf { it.isNotBlank() }
                ?: refreshToken()?.takeIf { existingAccountId == accountId }
            if (resolvedRefresh.isNullOrBlank()) return@synchronized false
            val committed = prefs.edit()
                .putString(KEY_ACCOUNT_ID, accountId)
                .putString(KEY_REFRESH_TOKEN, resolvedRefresh)
                .putString(KEY_SESSION_INCARNATION, UUID.randomUUID().toString())
                .commit()
            activeAccessToken = if (committed) access else null
            committed
        }

    fun updateSessionForIdentity(
        identity: AccountSessionIdentity,
        access: String,
        refresh: String?,
    ): Boolean = synchronized(MUTATION_LOCK) {
        if (!isCurrentLocked(identity) || access.isBlank()) return@synchronized false
        val editor = prefs.edit()
        if (!refresh.isNullOrBlank()) {
            editor.putString(KEY_REFRESH_TOKEN, refresh)
        }
        val committed = editor.commit()
        activeAccessToken = if (committed) access else null
        committed
    }

    fun clear() {
        synchronized(MUTATION_LOCK) {
            activeAccessToken = null
            check(
                prefs.edit()
                    .remove(KEY_ACCOUNT_ID)
                    .remove(KEY_REFRESH_TOKEN)
                    .remove(KEY_SESSION_INCARNATION)
                    .commit(),
            ) { "Unable to clear MEDTRACK credentials." }
        }
    }

    fun clearForIdentity(identity: AccountSessionIdentity): Boolean = synchronized(MUTATION_LOCK) {
        if (!isCurrentLocked(identity)) return@synchronized false
        activeAccessToken = null
        check(
            prefs.edit()
                .remove(KEY_ACCOUNT_ID)
                .remove(KEY_REFRESH_TOKEN)
                .remove(KEY_SESSION_INCARNATION)
                .commit(),
        ) { "Unable to clear MEDTRACK credentials." }
        true
    }

    private fun isCurrentLocked(identity: AccountSessionIdentity): Boolean =
        prefs.getString(KEY_ACCOUNT_ID, null) == identity.accountId &&
            prefs.getString(KEY_SESSION_INCARNATION, null) == identity.incarnation

    private companion object {
        const val PREFS_NAME = "medtrack_auth"
        const val KEY_ACCOUNT_ID = "account_id"
        const val KEY_REFRESH_TOKEN = "refresh_token"
        const val KEY_SESSION_INCARNATION = "session_incarnation"
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
    }
}
