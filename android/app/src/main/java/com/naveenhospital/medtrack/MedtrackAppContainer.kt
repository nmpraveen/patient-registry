package com.naveenhospital.medtrack

import android.content.Context
import com.naveenhospital.medtrack.core.data.auth.AuthRepository
import com.naveenhospital.medtrack.core.data.auth.LockStore
import com.naveenhospital.medtrack.core.data.auth.TokenStore
import com.naveenhospital.medtrack.core.data.local.MedtrackDatabase
import com.naveenhospital.medtrack.core.data.repository.MedtrackRepository
import com.naveenhospital.medtrack.core.data.sync.MedtrackSyncWorker
import com.naveenhospital.medtrack.core.network.api.MedtrackNetwork
import dagger.hilt.android.qualifiers.ApplicationContext
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class MedtrackAppContainer @Inject constructor(@ApplicationContext context: Context) {
    private val appContext = context.applicationContext
    private val tokenStore = TokenStore(context)
    private val apiBaseUrl = BuildConfig.MEDTRACK_API_BASE_URL
    private val api = MedtrackNetwork.create(
        baseUrl = apiBaseUrl,
        accessTokenProvider = { tokenStore.accessToken },
        refreshTokenProvider = { tokenStore.refreshToken() },
        sessionUpdater = { access, refresh -> tokenStore.saveSession(access = access, refresh = refresh) },
    )
    private val database = MedtrackDatabase.build(context)

    val authRepository = AuthRepository(api = api, tokenStore = tokenStore)
    val lockStore = LockStore(context)
    val medtrackRepository = MedtrackRepository(
        api = api,
        database = database,
        onPendingWriteQueued = { MedtrackSyncWorker.enqueueOneTime(appContext, apiBaseUrl) },
    )

    fun startBackgroundSync() {
        MedtrackSyncWorker.enqueue(appContext, apiBaseUrl)
    }
}
