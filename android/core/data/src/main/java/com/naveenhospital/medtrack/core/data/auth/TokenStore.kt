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
    var accessToken: String? = null

    fun refreshToken(): String? = prefs.getString(KEY_REFRESH_TOKEN, null)

    fun hasRefreshToken(): Boolean = !refreshToken().isNullOrBlank()

    fun saveSession(access: String, refresh: String?) {
        accessToken = access
        if (!refresh.isNullOrBlank()) {
            prefs.edit().putString(KEY_REFRESH_TOKEN, refresh).apply()
        }
    }

    fun clear() {
        accessToken = null
        prefs.edit().remove(KEY_REFRESH_TOKEN).apply()
    }

    private companion object {
        const val PREFS_NAME = "medtrack_auth"
        const val KEY_REFRESH_TOKEN = "refresh_token"

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
