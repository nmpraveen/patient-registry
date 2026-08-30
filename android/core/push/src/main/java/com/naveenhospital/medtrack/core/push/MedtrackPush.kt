package com.naveenhospital.medtrack.core.push

import android.app.NotificationChannel
import android.app.NotificationManager
import android.content.Context
import android.content.pm.PackageManager
import android.os.Build
import com.google.firebase.FirebaseApp
import com.google.firebase.messaging.FirebaseMessaging
import com.naveenhospital.medtrack.core.data.auth.TokenStore
import com.naveenhospital.medtrack.core.data.auth.AccountSessionIdentity
import com.naveenhospital.medtrack.core.data.auth.AccountSessionInvalidator
import com.naveenhospital.medtrack.core.data.auth.AccountSessionRefreshResult
import com.naveenhospital.medtrack.core.data.auth.refreshAndVerifyAccountSession
import com.naveenhospital.medtrack.core.data.auth.isDefinitiveAccountAuthFailure
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
        val expectedSession = tokenStore.sessionIdentity() ?: return@withContext false
        val ownerAccountId = expectedSession.accountId
        val database = MedtrackDatabase.build(appContext)
        val accountGeneration = database.activeAccountGeneration(ownerAccountId)
            ?: return@withContext false
        val invalidator = AccountSessionInvalidator(appContext)
        val api = MedtrackNetwork.create(
            baseUrl = baseUrl,
            accessTokenProvider = { tokenStore.accessTokenFor(expectedSession) },
            refreshTokenProvider = { tokenStore.refreshTokenFor(expectedSession) },
            expectedAccountIdProvider = {
                ownerAccountId.takeIf { tokenStore.accountId() == ownerAccountId }
            },
            expectedMobileDeviceIdProvider = { expectedSession.mobileDeviceId },
            sessionIncarnationProvider = {
                tokenStore.sessionIdentityFor(ownerAccountId)?.incarnation
            },
            sessionUpdater = { access, refresh ->
                tokenStore.updateSessionForIdentity(expectedSession, access, refresh)
            },
        )
        registerPushTokenForAccountSession(
            expectedSession = expectedSession,
            accountGeneration = accountGeneration,
            token = token,
            deviceLabel = deviceLabel,
            tokenStore = tokenStore,
            database = database,
            invalidateIfCurrent = invalidator::invalidateIfCurrent,
            refreshSession = { refreshToken ->
                MedtrackNetwork.create(baseUrl).refresh(RefreshTokenRequestDto(refresh = refreshToken))
            },
            verifyProfile = { accessToken ->
                MedtrackNetwork.create(
                    baseUrl = baseUrl,
                    accessTokenProvider = { accessToken },
                ).me()
            },
            registerRemote = {
                api.registerPushToken(
                    RegisterPushTokenRequestDto(
                        token = token,
                        deviceLabel = deviceLabel,
                    ),
                )
            },
        )
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

internal suspend fun registerPushTokenForAccountSession(
    expectedSession: AccountSessionIdentity,
    accountGeneration: Long,
    token: String,
    deviceLabel: String,
    tokenStore: TokenStore,
    database: MedtrackDatabase,
    invalidateIfCurrent: suspend (AccountSessionIdentity, Long) -> Boolean,
    refreshSession: suspend (String) -> com.naveenhospital.medtrack.core.network.model.AuthSessionDto,
    verifyProfile: suspend (String) -> com.naveenhospital.medtrack.core.network.model.UserProfileDto,
    registerRemote: suspend () -> Unit,
): Boolean {
    if (!tokenStore.isCurrent(expectedSession)) return false
    val ownerAccountId = expectedSession.accountId
    return try {
        database.commitForAccount(
            ownerAccountId,
            accountGeneration,
            { tokenStore.isCurrent(expectedSession) },
        ) {
            database.pushTokenDao().upsertToken(
                PushTokenEntity(
                    ownerAccountId = ownerAccountId,
                    token = token,
                    deviceLabel = deviceLabel,
                    syncedAtMillis = 0L,
                ),
            )
        }
        if (tokenStore.accessTokenFor(expectedSession).isNullOrBlank()) {
            when (
                refreshAndVerifyAccountSession(
                    expectedSession = expectedSession,
                    tokenStore = tokenStore,
                    refreshSession = refreshSession,
                    verifyProfile = verifyProfile,
                )
            ) {
                AccountSessionRefreshResult.Verified -> Unit
                AccountSessionRefreshResult.StaleAccount -> return false
                is AccountSessionRefreshResult.Retryable -> return false
                is AccountSessionRefreshResult.DefinitiveFailure -> {
                    invalidateIfCurrent(expectedSession, accountGeneration)
                    return false
                }
            }
        }
        if (!tokenStore.isCurrent(expectedSession)) return false
        registerRemote()
        database.commitForAccount(
            ownerAccountId,
            accountGeneration,
            { tokenStore.isCurrent(expectedSession) },
        ) {
            database.pushTokenDao().markTokenSynced(ownerAccountId, token, System.currentTimeMillis())
        }
        true
    } catch (failure: Throwable) {
        if (failure.isDefinitiveAccountAuthFailure()) {
            invalidateIfCurrent(expectedSession, accountGeneration)
        }
        false
    }
}
