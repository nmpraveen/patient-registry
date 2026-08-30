package com.naveenhospital.medtrack

import android.content.Context
import com.naveenhospital.medtrack.core.data.auth.AuthRepository
import com.naveenhospital.medtrack.core.data.auth.LockStore
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
        onBeforeAccountCommit = { previousAccountId, newAccountId ->
            medtrackRepository.deactivateAccount()
            if (previousAccountId != null && previousAccountId != newAccountId) {
                MedtrackSyncWorker.cancelForAccount(appContext, previousAccountId)
                medtrackRepository.wipeAccountData(previousAccountId)
                lockStore.clearAccount(previousAccountId)
                accountApis.remove(previousAccountId)
            }
        },
        onAccountCommitted = { accountId ->
            lockStore.activateAccount(accountId)
            medtrackRepository.activateAccount(accountId)
        },
        onSessionCleared = { accountId ->
            medtrackRepository.deactivateAccount()
            if (accountId != null) {
                MedtrackSyncWorker.cancelForAccount(appContext, accountId)
                medtrackRepository.wipeAccountData(accountId)
                lockStore.clearAccount(accountId)
                accountApis.remove(accountId)
            } else {
                lockStore.deactivate()
            }
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
            MedtrackNetwork.create(
                baseUrl = apiBaseUrl,
                accessTokenProvider = { tokenStore.accessTokenFor(accountId) },
                refreshTokenProvider = { tokenStore.refreshTokenFor(accountId) },
                sessionUpdater = { access, refresh ->
                    tokenStore.updateSessionForAccount(accountId, access, refresh)
                },
            )
        }
}
