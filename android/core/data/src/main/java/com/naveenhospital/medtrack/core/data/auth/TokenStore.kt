package com.naveenhospital.medtrack.core.data.auth

import android.content.Context
import android.content.SharedPreferences
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey

class TokenStore internal constructor(
    private val prefs: SharedPreferences,
) {
    constructor(context: Context) : this(encryptedPrefs(context.applicationContext))

    @Volatile
    private var activeAccessToken: String? = null

    val accessToken: String?
        get() = activeAccessToken

    fun accountId(): String? = prefs.getString(KEY_ACCOUNT_ID, null)?.takeIf { it.isNotBlank() }

    fun refreshToken(): String? = prefs.getString(KEY_REFRESH_TOKEN, null)

    fun hasRefreshToken(): Boolean = accountId() != null && !refreshToken().isNullOrBlank()

    fun accessTokenFor(accountId: String): String? =
        activeAccessToken?.takeIf { this.accountId() == accountId }

    fun refreshTokenFor(accountId: String): String? =
        refreshToken()?.takeIf { this.accountId() == accountId }

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
                .commit()
            activeAccessToken = if (committed) access else null
            committed
        }

    fun updateSessionForAccount(accountId: String, access: String, refresh: String?): Boolean =
        synchronized(MUTATION_LOCK) {
            if (this.accountId() != accountId || access.isBlank()) return@synchronized false
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
                    .commit(),
            ) { "Unable to clear MEDTRACK credentials." }
        }
    }

    fun clearForAccount(accountId: String): Boolean = synchronized(MUTATION_LOCK) {
        if (this.accountId() != accountId) return@synchronized false
        activeAccessToken = null
        check(
            prefs.edit()
                .remove(KEY_ACCOUNT_ID)
                .remove(KEY_REFRESH_TOKEN)
                .commit(),
        ) { "Unable to clear MEDTRACK credentials." }
        true
    }

    private companion object {
        const val PREFS_NAME = "medtrack_auth"
        const val KEY_ACCOUNT_ID = "account_id"
        const val KEY_REFRESH_TOKEN = "refresh_token"
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
