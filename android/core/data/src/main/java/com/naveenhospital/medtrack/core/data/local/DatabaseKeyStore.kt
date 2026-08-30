package com.naveenhospital.medtrack.core.data.local

import android.content.Context
import android.content.SharedPreferences
import android.util.Base64
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey
import java.security.SecureRandom

/** Keeps the SQLCipher passphrase behind an Android Keystore-backed master key. */
internal class DatabaseKeyStore(
    private val prefs: SharedPreferences,
) {
    constructor(context: Context) : this(encryptedPrefs(context.applicationContext))

    fun getOrCreatePassphrase(): ByteArray {
        prefs.getString(KEY_PASSPHRASE, null)?.let { encoded ->
            return encoded.toByteArray(Charsets.UTF_8)
        }
        val encoded = ByteArray(PASSPHRASE_BYTES)
            .also(secureRandom::nextBytes)
            .let { Base64.encodeToString(it, Base64.NO_WRAP) }
        check(prefs.edit().putString(KEY_PASSPHRASE, encoded).commit()) {
            "Unable to persist the encrypted MEDTRACK database key."
        }
        return encoded.toByteArray(Charsets.UTF_8)
    }

    private companion object {
        const val PREFS_NAME = "medtrack_database_key"
        const val KEY_PASSPHRASE = "sqlcipher_passphrase"
        const val PASSPHRASE_BYTES = 32
        val secureRandom = SecureRandom()

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
