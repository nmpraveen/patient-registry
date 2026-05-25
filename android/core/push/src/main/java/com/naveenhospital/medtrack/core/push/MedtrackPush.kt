package com.naveenhospital.medtrack.core.push

import android.app.NotificationChannel
import android.app.NotificationManager
import android.content.Context
import android.content.pm.PackageManager
import android.os.Build
import com.google.firebase.FirebaseApp
import com.google.firebase.messaging.FirebaseMessaging
import com.naveenhospital.medtrack.core.data.auth.TokenStore
import com.naveenhospital.medtrack.core.data.local.MedtrackDatabase
import com.naveenhospital.medtrack.core.data.local.PushTokenEntity
import com.naveenhospital.medtrack.core.network.api.MedtrackNetwork
import com.naveenhospital.medtrack.core.network.model.RefreshTokenRequestDto
import com.naveenhospital.medtrack.core.network.model.RegisterPushTokenRequestDto
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

object MedtrackPush {
    const val CHANNEL_ASSIGNMENTS = "assignments"
    const val CHANNEL_RED_FLAGS = "red_flags"
    const val CHANNEL_OVERDUE = "overdue"
    private const val META_API_BASE_URL = "com.naveenhospital.medtrack.API_BASE_URL"

    fun createChannels(context: Context) {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return
        val manager = context.getSystemService(NotificationManager::class.java)
        manager.createNotificationChannels(
            listOf(
                NotificationChannel(
                    CHANNEL_ASSIGNMENTS,
                    "Assignments",
                    NotificationManager.IMPORTANCE_HIGH,
                ),
                NotificationChannel(
                    CHANNEL_RED_FLAGS,
                    "Red flags",
                    NotificationManager.IMPORTANCE_HIGH,
                ),
                NotificationChannel(
                    CHANNEL_OVERDUE,
                    "Overdue",
                    NotificationManager.IMPORTANCE_DEFAULT,
                ),
            ),
        )
    }

    fun fetchTokenIfConfigured(
        context: Context,
        onToken: (String) -> Unit,
    ) {
        if (FirebaseApp.getApps(context).isEmpty()) return
        FirebaseMessaging.getInstance().token
            .addOnSuccessListener { token ->
                if (!token.isNullOrBlank()) {
                    onToken(token)
                }
            }
    }

    suspend fun registerTokenForCurrentSession(
        context: Context,
        token: String,
        deviceLabel: String = Build.MODEL.orEmpty(),
    ): Boolean = withContext(Dispatchers.IO) {
        if (token.isBlank()) return@withContext false
        val appContext = context.applicationContext
        val baseUrl = apiBaseUrl(appContext) ?: return@withContext false
        val tokenStore = TokenStore(appContext)
        val refreshToken = tokenStore.refreshToken() ?: return@withContext false
        val database = MedtrackDatabase.build(appContext)
        database.pushTokenDao().upsertToken(
            PushTokenEntity(
                token = token,
                deviceLabel = deviceLabel,
                syncedAtMillis = 0L,
            ),
        )
        val api = MedtrackNetwork.create(
            baseUrl = baseUrl,
            accessTokenProvider = { tokenStore.accessToken },
            refreshTokenProvider = { tokenStore.refreshToken() },
            sessionUpdater = { access, refresh -> tokenStore.saveSession(access = access, refresh = refresh) },
        )
        if (tokenStore.accessToken.isNullOrBlank()) {
            val session = runCatching { api.refresh(RefreshTokenRequestDto(refresh = refreshToken)) }
                .getOrElse { return@withContext false }
            tokenStore.saveSession(access = session.access, refresh = session.refresh)
        }
        runCatching {
            api.registerPushToken(
                RegisterPushTokenRequestDto(
                    token = token,
                    deviceLabel = deviceLabel,
                ),
            )
            database.pushTokenDao().markTokenSynced(token, System.currentTimeMillis())
        }.isSuccess
    }

    fun channelForType(type: String?): String =
        when (type) {
            "assignment", "assignments" -> CHANNEL_ASSIGNMENTS
            "red_flag", "red_flags" -> CHANNEL_RED_FLAGS
            else -> CHANNEL_OVERDUE
        }

    @Suppress("DEPRECATION")
    private fun apiBaseUrl(context: Context): String? =
        context.packageManager
            .getApplicationInfo(context.packageName, PackageManager.GET_META_DATA)
            .metaData
            ?.getString(META_API_BASE_URL)
            ?.takeIf { it.isNotBlank() }
}
