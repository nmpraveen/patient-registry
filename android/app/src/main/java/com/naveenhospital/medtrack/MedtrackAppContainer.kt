package com.naveenhospital.medtrack

import android.content.Context
import com.naveenhospital.medtrack.core.data.auth.AuthRepository
import com.naveenhospital.medtrack.core.data.auth.AccountSessionInvalidator
import com.naveenhospital.medtrack.core.data.auth.AccountVisibilityInvalidations
import com.naveenhospital.medtrack.core.data.auth.LockStore
import com.naveenhospital.medtrack.core.data.auth.MobileDeviceCredentialStore
import com.naveenhospital.medtrack.core.data.auth.TokenStore
import com.naveenhospital.medtrack.core.data.local.MedtrackDatabase
import com.naveenhospital.medtrack.core.data.repository.MedtrackRepository
import com.naveenhospital.medtrack.core.data.sync.MedtrackSyncWorker
import com.naveenhospital.medtrack.core.network.api.MedtrackApi
import com.naveenhospital.medtrack.core.network.api.MedtrackNetwork
import dagger.hilt.android.qualifiers.ApplicationContext
import java.util.concurrent.ConcurrentHashMap
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class MedtrackAppContainer @Inject constructor(@ApplicationContext context: Context) {
    private val appContext = context.applicationContext
    private val tokenStore = TokenStore(appContext)
    private val mobileDeviceCredentials = MobileDeviceCredentialStore(appContext)
    private val apiBaseUrl = BuildConfig.MEDTRACK_API_BASE_URL
    private val database = MedtrackDatabase.build(appContext)
    private val accountApis = ConcurrentHashMap<String, MedtrackApi>()

    val lockStore = LockStore(appContext).also { store ->
        store.activateAccount(tokenStore.accountId())
    }

    val medtrackRepository = MedtrackRepository(
        apiForAccount = ::apiForAccount,
        database = database,
        onPendingWriteQueued = { accountId ->
            MedtrackSyncWorker.enqueueOneTime(appContext, apiBaseUrl, accountId)
        },
    )

    private val accountInvalidator = AccountSessionInvalidator(
        context = appContext,
        database = database,
        tokenStore = tokenStore,
        lockStore = lockStore,
    )

    private val visibilityInvalidationListener: (String) -> Unit = { accountId ->
        if (medtrackRepository.activeAccountId() == accountId) {
            medtrackRepository.deactivateAccount()
        }
        if (lockStore.activeAccountId() == accountId) {
            lockStore.deactivate()
        }
        accountApis.remove(accountId)
    }

    init {
        AccountVisibilityInvalidations.register(visibilityInvalidationListener)
    }

    val authRepository = AuthRepository(
        anonymousApi = MedtrackNetwork.create(apiBaseUrl),
        verificationApiForAccessToken = { candidateAccessToken ->
            MedtrackNetwork.create(
                baseUrl = apiBaseUrl,
                accessTokenProvider = { candidateAccessToken },
            )
        },
        apiForAccount = ::apiForAccount,
        tokenStore = tokenStore,
        mobileDeviceCredentials = mobileDeviceCredentials,
        onBeforeAccountCommit = { previousSession, newAccountId ->
            medtrackRepository.deactivateAccount()
            previousSession?.let { accountApis.remove(it.accountId) }
            if (previousSession != null && previousSession.accountId != newAccountId) {
                accountInvalidator.invalidate(previousSession)
            }
        },
        onAccountCommitted = { accountId ->
            lockStore.activateAccount(accountId)
            medtrackRepository.activateAccount(accountId)
        },
        onSessionCleared = { sessionIdentity ->
            accountInvalidator.invalidate(sessionIdentity)
        },
    )

    fun startBackgroundSync() {
        val accountId = tokenStore.accountId() ?: return
        if (medtrackRepository.activeAccountId() != accountId) return
        MedtrackSyncWorker.enqueue(appContext, apiBaseUrl, accountId)
    }

    suspend fun abandonLockedSession() {
        authRepository.abandonSession()
    }

    private fun apiForAccount(accountId: String): MedtrackApi =
        accountApis.getOrPut(accountId) {
            val sessionIdentity = tokenStore.sessionIdentityFor(accountId)
                ?: error("No verified MEDTRACK session is bound to account $accountId.")
            MedtrackNetwork.create(
                baseUrl = apiBaseUrl,
                accessTokenProvider = { tokenStore.accessTokenFor(sessionIdentity) },
                refreshTokenProvider = { tokenStore.refreshTokenFor(sessionIdentity) },
                expectedAccountIdProvider = {
                    accountId.takeIf { tokenStore.accountId() == accountId }
                },
                expectedMobileDeviceIdProvider = { sessionIdentity.mobileDeviceId },
                sessionIncarnationProvider = {
                    tokenStore.sessionIdentityFor(accountId)?.incarnation
                },
                sessionUpdater = { access, refresh ->
                    tokenStore.updateSessionForIdentity(sessionIdentity, access, refresh)
                },
            )
        }
}
