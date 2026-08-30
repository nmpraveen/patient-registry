package com.naveenhospital.medtrack.core.data.sync

import android.content.Context
import androidx.work.Constraints
import androidx.work.CoroutineWorker
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.ExistingWorkPolicy
import androidx.work.NetworkType
import androidx.work.OneTimeWorkRequest
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.Operation
import androidx.work.PeriodicWorkRequest
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import androidx.work.workDataOf
import androidx.room.withTransaction
import com.naveenhospital.medtrack.core.data.auth.TokenStore
import com.naveenhospital.medtrack.core.data.auth.AccountSessionIdentity
import com.naveenhospital.medtrack.core.data.auth.AccountSessionInvalidator
import com.naveenhospital.medtrack.core.data.auth.AccountSessionRefreshResult
import com.naveenhospital.medtrack.core.data.auth.refreshAndVerifyAccountSession
import com.naveenhospital.medtrack.core.data.local.CacheMetadataEntity
import com.naveenhospital.medtrack.core.data.local.AccountGenerationRevokedException
import com.naveenhospital.medtrack.core.data.local.CaseEntity
import com.naveenhospital.medtrack.core.data.local.CaseStatsEntity
import com.naveenhospital.medtrack.core.data.local.CategoryOptionsEntity
import com.naveenhospital.medtrack.core.data.local.MedtrackDatabase
import com.naveenhospital.medtrack.core.data.local.NotificationEntity
import com.naveenhospital.medtrack.core.data.local.SyncConflictEntity
import com.naveenhospital.medtrack.core.data.local.TaskEntity
import com.naveenhospital.medtrack.core.data.local.VitalEntity
import com.naveenhospital.medtrack.core.data.local.VitalsThresholdEntity
import com.naveenhospital.medtrack.core.data.notification.notificationPayloadToJson
import com.naveenhospital.medtrack.core.data.repository.CACHE_KEY_CATEGORY_OPTIONS
import com.naveenhospital.medtrack.core.data.repository.CACHE_KEY_NOTIFICATIONS
import com.naveenhospital.medtrack.core.data.repository.CACHE_KEY_NOTIFICATION_DATASET_EPOCH_PREFIX
import com.naveenhospital.medtrack.core.data.repository.CACHE_KEY_VITALS_THRESHOLDS
import com.naveenhospital.medtrack.core.data.repository.caseDetailCacheKey
import com.naveenhospital.medtrack.core.data.repository.caseListCacheKey
import com.naveenhospital.medtrack.core.data.repository.isCacheFresh
import com.naveenhospital.medtrack.core.data.repository.pendingVitalId
import com.naveenhospital.medtrack.core.network.api.MedtrackApi
import com.naveenhospital.medtrack.core.network.api.MedtrackNetwork
import com.naveenhospital.medtrack.core.network.model.CategoriesResponseDto
import com.naveenhospital.medtrack.core.network.model.CaseSummaryDto
import com.naveenhospital.medtrack.core.network.model.CaseStatsDto
import com.naveenhospital.medtrack.core.network.model.NotificationDto
import com.naveenhospital.medtrack.core.network.model.RefreshTokenRequestDto
import com.naveenhospital.medtrack.core.network.model.RegisterPushTokenRequestDto
import com.naveenhospital.medtrack.core.network.model.TaskDto
import com.naveenhospital.medtrack.core.network.model.VitalDto
import com.naveenhospital.medtrack.core.network.model.VitalsThresholdsDto
import com.squareup.moshi.Moshi
import com.squareup.moshi.kotlin.reflect.KotlinJsonAdapterFactory
import java.util.concurrent.TimeUnit
import java.util.concurrent.Executor
import java.security.MessageDigest
import android.util.Base64
import java.io.IOException
import java.util.UUID
import retrofit2.HttpException
import kotlinx.coroutines.suspendCancellableCoroutine

internal enum class SyncRunOutcome {
    COMPLETED,
    RETRY,
    AUTH_REQUIRED,
    TERMINAL_FAILURE,
}

class MedtrackSyncWorker(
    appContext: Context,
    params: WorkerParameters,
) : CoroutineWorker(appContext, params) {
    override suspend fun doWork(): Result {
        val baseUrl = inputData.getString(KEY_BASE_URL) ?: return Result.failure()
        val ownerAccountId = inputData.getString(KEY_ACCOUNT_ID)?.takeIf { it.isNotBlank() }
            ?: return Result.failure()
        val tokenStore = TokenStore(applicationContext)
        val expectedSession = tokenStore.sessionIdentityFor(ownerAccountId) ?: return Result.success()
        val database = MedtrackDatabase.build(applicationContext)
        val accountGeneration = database.activeAccountGeneration(ownerAccountId)
            ?: return Result.success()
        val invalidator = AccountSessionInvalidator(applicationContext)
        when (
            authenticateWorkerAccount(
                expectedSession = expectedSession,
                expectedGeneration = accountGeneration,
                tokenStore = tokenStore,
                invalidator = invalidator,
                refreshSession = { refreshToken ->
                    MedtrackNetwork.create(baseUrl).refresh(RefreshTokenRequestDto(refresh = refreshToken))
                },
                verifyProfile = { accessToken ->
                    MedtrackNetwork.create(
                        baseUrl = baseUrl,
                        accessTokenProvider = { accessToken },
                    ).me()
                },
            )
        ) {
            WorkerAuthenticationResult.Verified -> Unit
            WorkerAuthenticationResult.StaleAccount -> return Result.success()
            WorkerAuthenticationResult.Retry -> return Result.retry()
            WorkerAuthenticationResult.Invalidated -> return Result.failure()
        }
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
        if (!tokenStore.isCurrent(expectedSession)) return Result.success()

        return try {
            val activeAccount = {
                ownerAccountId.takeIf { tokenStore.isCurrent(expectedSession) }
            }
            when (
                drainPendingWritesForSync(
                    api = api,
                    database = database,
                    ownerAccountId = ownerAccountId,
                    accountGeneration = accountGeneration,
                    activeAccountId = activeAccount,
                )
            ) {
                SyncRunOutcome.AUTH_REQUIRED -> {
                    invalidator.invalidateIfCurrent(expectedSession, accountGeneration)
                    return Result.failure(workDataOf(KEY_FAILURE_KIND to SyncFailureKinds.AUTHENTICATION))
                }
                SyncRunOutcome.RETRY -> return Result.retry()
                SyncRunOutcome.TERMINAL_FAILURE -> return Result.failure()
                SyncRunOutcome.COMPLETED -> Unit
            }
            when (
                syncPendingPushTokens(
                    api = api,
                    database = database,
                    ownerAccountId = ownerAccountId,
                    accountGeneration = accountGeneration,
                    activeAccountId = activeAccount,
                )
            ) {
                SyncRunOutcome.AUTH_REQUIRED -> {
                    invalidator.invalidateIfCurrent(expectedSession, accountGeneration)
                    return Result.failure(workDataOf(KEY_FAILURE_KIND to SyncFailureKinds.AUTHENTICATION))
                }
                SyncRunOutcome.RETRY -> return Result.retry()
                SyncRunOutcome.TERMINAL_FAILURE -> return Result.failure()
                SyncRunOutcome.COMPLETED -> Unit
            }
            if (!tokenStore.isCurrent(expectedSession)) return Result.success()
            refreshStaleReadCaches(
                api = api,
                database = database,
                ownerAccountId = ownerAccountId,
                accountGeneration = accountGeneration,
                activeAccountId = {
                    ownerAccountId.takeIf { tokenStore.isCurrent(expectedSession) }
                },
            )
            Result.success()
        } catch (failure: Throwable) {
            if (failure is HttpException && failure.code() in setOf(401, 403)) {
                invalidator.invalidateIfCurrent(expectedSession, accountGeneration)
                Result.failure()
            } else if (failure is AccountChangedException || failure is AccountGenerationRevokedException) {
                Result.success()
            } else {
                Result.retry()
            }
        }
    }

    private suspend fun refreshStaleReadCaches(
        api: com.naveenhospital.medtrack.core.network.api.MedtrackApi,
        database: MedtrackDatabase,
        ownerAccountId: String,
        accountGeneration: Long,
        activeAccountId: () -> String?,
    ) {
        // Revalidate the current JWT actor before any clinical/notification read. PR #103/lane 4
        // must additionally bind this identity to the account-scoped database generation.
        require(api.me().id > 0L) { "Authenticated mobile identity is invalid." }
        val now = System.currentTimeMillis()
        val defaultCaseListKey = caseListCacheKey(
            bucket = "today",
            query = null,
            assignedTo = null,
            scopeContext = null,
            categories = emptyList(),
            subcategories = emptyList(),
        )
        if (database.shouldRefresh(ownerAccountId, defaultCaseListKey, now)) {
            val response = api.listCases(bucket = "today", page = 1)
            database.commitForAccount(
                ownerAccountId = ownerAccountId,
                generation = accountGeneration,
                isLocallyActive = { activeAccountId() == ownerAccountId },
            ) {
                database.caseDao().clearCases(ownerAccountId)
                database.caseDao().upsertCases(response.results.map { it.toEntityForSync(ownerAccountId) })
                database.caseStatsDao().upsertStats(response.stats.toEntityForSync(ownerAccountId, defaultCaseListKey, now))
                database.markCacheFresh(ownerAccountId, defaultCaseListKey, now)
            }
        }

        if (database.shouldRefresh(ownerAccountId, CACHE_KEY_VITALS_THRESHOLDS, now)) {
            val response = api.vitalsThresholds()
            database.commitForAccount(
                ownerAccountId,
                accountGeneration,
                { activeAccountId() == ownerAccountId },
            ) {
                database.vitalsThresholdDao().upsertThresholds(response.toEntityForSync(ownerAccountId, now))
                database.markCacheFresh(ownerAccountId, CACHE_KEY_VITALS_THRESHOLDS, now)
            }
        }

        if (database.shouldRefresh(ownerAccountId, CACHE_KEY_CATEGORY_OPTIONS, now)) {
            val response = api.categories()
            database.commitForAccount(
                ownerAccountId,
                accountGeneration,
                { activeAccountId() == ownerAccountId },
            ) {
                database.categoryOptionsDao().upsertOptions(response.toEntityForSync(ownerAccountId, now))
                database.markCacheFresh(ownerAccountId, CACHE_KEY_CATEGORY_OPTIONS, now)
            }
        }

        if (database.shouldRefresh(ownerAccountId, CACHE_KEY_NOTIFICATIONS, now)) {
            val snapshot = fetchAllNotifications(api = api)
            database.commitForAccount(
                ownerAccountId,
                accountGeneration,
                { activeAccountId() == ownerAccountId },
            ) {
                replaceNotificationSnapshot(
                    database = database,
                    ownerAccountId = ownerAccountId,
                    type = null,
                    snapshot = NotificationSnapshot(
                        datasetEpoch = snapshot.datasetEpoch,
                        notifications = snapshot.notifications.map { it.toEntityForSync(ownerAccountId) },
                    ),
                )
                database.markCacheFresh(ownerAccountId, CACHE_KEY_NOTIFICATIONS, now)
            }
        }

        database.cacheMetadataDao().cacheKeysStartingWith(ownerAccountId, CASE_DETAIL_CACHE_PREFIX).forEach { cacheKey ->
            if (!database.shouldRefresh(ownerAccountId, cacheKey, now)) {
                return@forEach
            }
            val caseId = cacheKey.removePrefix(CASE_DETAIL_CACHE_PREFIX).takeIf { it.isNotBlank() }
                ?: return@forEach
            runCatching {
                refreshServerCase(
                    api = api,
                    database = database,
                    ownerAccountId = ownerAccountId,
                    accountGeneration = accountGeneration,
                    activeAccountId = activeAccountId,
                    caseId = caseId,
                    cacheUpdatedAtMillis = now,
                )
            }.onFailure(Throwable::rethrowAccountBoundaryFailure)
        }
    }

    companion object {
        private const val WORK_NAME_PREFIX = "medtrack_periodic_sync"
        private const val ONE_TIME_WORK_NAME_PREFIX = "medtrack_pending_write_sync"
        private const val CASE_DETAIL_CACHE_PREFIX = "case_detail:"
        private const val KEY_BASE_URL = "base_url"
        private const val KEY_ACCOUNT_ID = "account_id"
        private const val KEY_FAILURE_KIND = "failure_kind"

        fun enqueue(context: Context, baseUrl: String, accountId: String) {
            WorkManager.getInstance(context).enqueueUniquePeriodicWork(
                periodicWorkName(accountId),
                ExistingPeriodicWorkPolicy.UPDATE,
                periodicRequest(baseUrl, accountId),
            )
        }

        fun enqueueOneTime(context: Context, baseUrl: String, accountId: String) {
            WorkManager.getInstance(context).enqueueUniqueWork(
                oneTimeWorkName(accountId),
                ExistingWorkPolicy.APPEND_OR_REPLACE,
                oneTimeRequest(baseUrl, accountId),
            )
        }

        suspend fun cancelForAccount(context: Context, accountId: String) {
            val workManager = WorkManager.getInstance(context)
            workManager.cancelUniqueWork(periodicWorkName(accountId)).awaitCompletion()
            workManager.cancelUniqueWork(oneTimeWorkName(accountId)).awaitCompletion()
        }

        internal fun periodicWorkName(accountId: String): String =
            "$WORK_NAME_PREFIX:${accountWorkKey(accountId)}"

        internal fun oneTimeWorkName(accountId: String): String =
            "$ONE_TIME_WORK_NAME_PREFIX:${accountWorkKey(accountId)}"

        fun periodicRequest(baseUrl: String, accountId: String): PeriodicWorkRequest =
            PeriodicWorkRequestBuilder<MedtrackSyncWorker>(15, TimeUnit.MINUTES)
                .setConstraints(
                    Constraints.Builder()
                        .setRequiredNetworkType(NetworkType.CONNECTED)
                        .build(),
                )
                .setInputData(workDataOf(KEY_BASE_URL to baseUrl, KEY_ACCOUNT_ID to accountId))
                .build()

        fun oneTimeRequest(baseUrl: String, accountId: String): OneTimeWorkRequest =
            OneTimeWorkRequestBuilder<MedtrackSyncWorker>()
                .setConstraints(
                    Constraints.Builder()
                        .setRequiredNetworkType(NetworkType.CONNECTED)
                        .build(),
                )
                .setInputData(workDataOf(KEY_BASE_URL to baseUrl, KEY_ACCOUNT_ID to accountId))
                .build()

        private fun accountWorkKey(accountId: String): String {
            require(accountId.isNotBlank()) { "A verified account ID is required." }
            val digest = MessageDigest.getInstance("SHA-256")
                .digest(accountId.toByteArray(Charsets.UTF_8))
            return Base64.encodeToString(digest.copyOf(12), Base64.NO_WRAP or Base64.URL_SAFE)
        }
    }
}

internal enum class WorkerAuthenticationResult {
    Verified,
    StaleAccount,
    Retry,
    Invalidated,
}

internal suspend fun authenticateWorkerAccount(
    expectedSession: AccountSessionIdentity,
    expectedGeneration: Long,
    tokenStore: TokenStore,
    invalidator: AccountSessionInvalidator,
    refreshSession: suspend (String) -> com.naveenhospital.medtrack.core.network.model.AuthSessionDto,
    verifyProfile: suspend (String) -> com.naveenhospital.medtrack.core.network.model.UserProfileDto,
): WorkerAuthenticationResult =
    when (
        refreshAndVerifyAccountSession(
            expectedSession = expectedSession,
            tokenStore = tokenStore,
            refreshSession = refreshSession,
            verifyProfile = verifyProfile,
        )
    ) {
        AccountSessionRefreshResult.Verified -> WorkerAuthenticationResult.Verified
        AccountSessionRefreshResult.StaleAccount -> WorkerAuthenticationResult.StaleAccount
        is AccountSessionRefreshResult.Retryable -> WorkerAuthenticationResult.Retry
        is AccountSessionRefreshResult.DefinitiveFailure -> {
            if (invalidator.invalidateIfCurrent(expectedSession, expectedGeneration)) {
                WorkerAuthenticationResult.Invalidated
            } else {
                WorkerAuthenticationResult.StaleAccount
            }
        }
    }

private suspend fun Operation.awaitCompletion() {
    val future = result
    suspendCancellableCoroutine<Unit> { continuation ->
        future.addListener(
            {
                runCatching { future.get() }
                    .onSuccess { continuation.resumeWith(Result.success(Unit)) }
                    .onFailure { continuation.resumeWith(Result.failure(it)) }
            },
            Executor(Runnable::run),
        )
        continuation.invokeOnCancellation { future.cancel(true) }
    }
}

internal suspend fun drainPendingWritesForSync(
    api: MedtrackApi,
    database: MedtrackDatabase,
    ownerAccountId: String,
    accountGeneration: Long,
    activeAccountId: () -> String? = { ownerAccountId },
): SyncRunOutcome {
    val pendingWriteDao = database.pendingWriteDao()
    pendingWriteDao.pendingWrites(ownerAccountId).forEach { write ->
        if (activeAccountId() != ownerAccountId) return SyncRunOutcome.COMPLETED
        val now = System.currentTimeMillis()
        val result = runCatching {
            ensureAccountActive(ownerAccountId, activeAccountId)
            when (val pendingWrite = PendingWriteJson.decodeForSync(write)) {
                is DecodedPendingWrite.TaskComplete -> {
                    val response = api.completeTask(pendingWrite.taskId, pendingWrite.payload)
                    database.commitForAccount(
                        ownerAccountId,
                        accountGeneration,
                        { activeAccountId() == ownerAccountId },
                    ) {
                        database.caseDao().upsertCase(response.case.toEntityForSync(ownerAccountId))
                        database.taskDao().upsertTask(response.task.toEntityForSync(ownerAccountId, pendingWrite.caseId))
                        pendingWriteDao.deletePendingWrite(ownerAccountId, write.clientWriteId)
                    }
                }
                is DecodedPendingWrite.CallOutcome -> {
                    val response = api.logCall(pendingWrite.caseId, pendingWrite.payload)
                    database.commitForAccount(
                        ownerAccountId,
                        accountGeneration,
                        { activeAccountId() == ownerAccountId },
                    ) {
                        database.caseDao().upsertCase(response.case.toEntityForSync(ownerAccountId))
                        pendingWriteDao.deletePendingWrite(ownerAccountId, write.clientWriteId)
                    }
                }
                is DecodedPendingWrite.VitalsCreate -> {
                    val response = api.addVitals(pendingWrite.caseId, pendingWrite.payload)
                    database.commitForAccount(
                        ownerAccountId,
                        accountGeneration,
                        { activeAccountId() == ownerAccountId },
                    ) {
                        database.caseDao().upsertCase(response.case.toEntityForSync(ownerAccountId))
                        database.vitalDao().deleteVital(ownerAccountId, pendingVitalId(write.clientWriteId))
                        database.vitalDao().upsertVital(response.vital.toEntityForSync(ownerAccountId, pendingWrite.caseId))
                        pendingWriteDao.deletePendingWrite(ownerAccountId, write.clientWriteId)
                    }
                }
                is DecodedPendingWrite.NotificationRead -> {
                    api.markNotificationRead(pendingWrite.notificationId)
                    database.commitForAccount(
                        ownerAccountId,
                        accountGeneration,
                        { activeAccountId() == ownerAccountId },
                    ) {
                        database.notificationDao().markRead(ownerAccountId, pendingWrite.notificationId)
                        pendingWriteDao.deletePendingWrite(ownerAccountId, write.clientWriteId)
                    }
                }
            }
        }
        if (result.isSuccess) {
            database.commitForAccount(
                ownerAccountId,
                accountGeneration,
                { activeAccountId() == ownerAccountId },
            ) {
                database.markRecoveryResolved(
                    ownerAccountId,
                    write.clientWriteId,
                    SyncResolutionStates.SYNCED_AFTER_RETRY,
                )
            }
        } else {
            val error = result.exceptionOrNull()
            if (error is AccountChangedException || error is AccountGenerationRevokedException) {
                return SyncRunOutcome.COMPLETED
            }
            if (error is MalformedPendingWriteException) {
                database.commitForAccount(
                    ownerAccountId,
                    accountGeneration,
                    { activeAccountId() == ownerAccountId },
                ) {
                    database.recordSyncIssue(
                        ownerAccountId = ownerAccountId,
                        write = write,
                        failureKind = SyncFailureKinds.MALFORMED,
                        message = error.message ?: "Malformed pending write.",
                        serverPayloadJson = null,
                        httpStatus = null,
                        createdAtMillis = now,
                    )
                    pendingWriteDao.deletePendingWrite(ownerAccountId, write.clientWriteId)
                }
                return@forEach
            }
            val failureKind = classifySyncFailure(error)
            if (failureKind == SyncFailureKinds.AUTHENTICATION) {
                database.commitForAccount(
                    ownerAccountId,
                    accountGeneration,
                    { activeAccountId() == ownerAccountId },
                ) {
                    pendingWriteDao.markAttempt(
                        ownerAccountId = ownerAccountId,
                        clientWriteId = write.clientWriteId,
                        lastError = "Authentication expired. Sign in to retry.",
                        updatedAtMillis = now,
                    )
                    database.recordSyncIssue(
                        ownerAccountId = ownerAccountId,
                        write = write,
                        failureKind = failureKind,
                        message = "Authentication expired. Sign in to retry the retained change.",
                        serverPayloadJson = error.httpErrorBody(),
                        httpStatus = (error as? HttpException)?.code(),
                        createdAtMillis = now,
                    )
                }
                return SyncRunOutcome.AUTH_REQUIRED
            }
            if (failureKind in setOf(SyncFailureKinds.CONFLICT, SyncFailureKinds.VALIDATION)) {
                val serverPayload = error.httpErrorBody()
                val statusCode = (error as? HttpException)?.code()
                val serverMessage = serverPayload
                    ?.trim()
                    ?.removeSurrounding("\"")
                    ?.takeIf { it.length <= 240 && !it.startsWith("{") && !it.startsWith("[") }
                val message = serverMessage ?: when (failureKind) {
                    SyncFailureKinds.CONFLICT -> "The server version was kept. Review or retry the retained change."
                    else -> "The server rejected this saved change${statusCode?.let { " ($it)" }.orEmpty()}. Review or discard it."
                }
                database.commitForAccount(
                    ownerAccountId,
                    accountGeneration,
                    { activeAccountId() == ownerAccountId },
                ) {
                    database.recordSyncIssue(
                        ownerAccountId = ownerAccountId,
                        write = write,
                        failureKind = failureKind,
                        message = message,
                        serverPayloadJson = serverPayload,
                        httpStatus = statusCode,
                        createdAtMillis = now,
                    )
                    pendingWriteDao.deletePendingWrite(ownerAccountId, write.clientWriteId)
                }
                write.caseId?.let { caseId ->
                    runCatching {
                        refreshServerCase(
                            api,
                            database,
                            ownerAccountId,
                            accountGeneration,
                            activeAccountId,
                            caseId,
                        )
                    }.onFailure(Throwable::rethrowAccountBoundaryFailure)
                }
                return@forEach
            }
            database.commitForAccount(
                ownerAccountId,
                accountGeneration,
                { activeAccountId() == ownerAccountId },
            ) {
                pendingWriteDao.markAttempt(
                    ownerAccountId = ownerAccountId,
                    clientWriteId = write.clientWriteId,
                    lastError = error?.message,
                    updatedAtMillis = now,
                )
            }
            return SyncRunOutcome.RETRY
        }
    }
    return SyncRunOutcome.COMPLETED
}

private suspend fun syncPendingPushTokens(
    api: MedtrackApi,
    database: MedtrackDatabase,
    ownerAccountId: String,
    accountGeneration: Long,
    activeAccountId: () -> String?,
): SyncRunOutcome {
    database.pushTokenDao().pendingTokens(ownerAccountId).forEach { token ->
        val result = runCatching {
            api.registerPushToken(
                RegisterPushTokenRequestDto(
                    token = token.token,
                    deviceLabel = token.deviceLabel,
                ),
            )
            database.commitForAccount(
                ownerAccountId,
                accountGeneration,
                { activeAccountId() == ownerAccountId },
            ) {
                database.pushTokenDao().markTokenSynced(ownerAccountId, token.token, System.currentTimeMillis())
            }
        }
        if (result.isFailure) {
            val error = result.exceptionOrNull()
            when (classifySyncFailure(error)) {
                SyncFailureKinds.AUTHENTICATION -> return SyncRunOutcome.AUTH_REQUIRED
                SyncFailureKinds.TRANSIENT -> return SyncRunOutcome.RETRY
                else -> {
                    database.commitForAccount(
                        ownerAccountId,
                        accountGeneration,
                        { activeAccountId() == ownerAccountId },
                    ) {
                        database.pushTokenDao().deleteToken(ownerAccountId, token.token)
                    }
                    return@forEach
                }
            }
        }
    }
    return SyncRunOutcome.COMPLETED
}

private suspend fun refreshServerCase(
    api: MedtrackApi,
    database: MedtrackDatabase,
    ownerAccountId: String,
    accountGeneration: Long,
    activeAccountId: () -> String?,
    caseId: String,
    cacheUpdatedAtMillis: Long? = null,
) {
    val response = api.caseDetail(caseId)
    database.commitForAccount(
        ownerAccountId,
        accountGeneration,
        { activeAccountId() == ownerAccountId },
    ) {
        database.caseDao().upsertCase(response.case.toEntityForSync(ownerAccountId))
        database.taskDao().clearTasksForCase(ownerAccountId, caseId)
        database.taskDao().upsertTasks(response.tasks.map { it.toEntityForSync(ownerAccountId, caseId) })
        database.vitalDao().clearVitalsForCase(ownerAccountId, caseId)
        database.vitalDao().upsertVitals(response.vitals.map { it.toEntityForSync(ownerAccountId, caseId) })
        cacheUpdatedAtMillis?.let { updatedAt ->
            database.markCacheFresh(ownerAccountId, caseDetailCacheKey(caseId), updatedAt)
        }
    }
}

private suspend fun MedtrackDatabase.recordSyncIssue(
    ownerAccountId: String,
    write: com.naveenhospital.medtrack.core.data.local.PendingWriteEntity,
    failureKind: String,
    message: String,
    serverPayloadJson: String?,
    httpStatus: Int?,
    createdAtMillis: Long,
) {
    syncConflictDao().upsertConflict(
        SyncConflictEntity(
            ownerAccountId = ownerAccountId,
            clientWriteId = write.clientWriteId,
            writeType = write.writeType,
            caseId = write.caseId,
            taskId = write.taskId,
            message = message,
            serverPayloadJson = SyncRecoveryJson.encode(
                SyncRecoveryPayload(
                    failureKind = failureKind,
                    localPayloadJson = write.payloadJson,
                    serverPayloadJson = serverPayloadJson,
                    httpStatus = httpStatus,
                ),
            ),
            createdAtMillis = createdAtMillis,
        ),
    )
}

private suspend fun MedtrackDatabase.shouldRefresh(ownerAccountId: String, cacheKey: String, now: Long): Boolean =
    !isCacheFresh(cacheMetadataDao().updatedAtMillis(ownerAccountId, cacheKey), now)

private suspend fun MedtrackDatabase.markRecoveryResolved(
    ownerAccountId: String,
    clientWriteId: String,
    resolutionState: String,
) {
    val conflict = syncConflictDao().conflictById(ownerAccountId, clientWriteId) ?: return
    val recovery = SyncRecoveryJson.decode(conflict.serverPayloadJson) ?: return
    syncConflictDao().upsertConflict(
        conflict.copy(
            serverPayloadJson = SyncRecoveryJson.encode(
                recovery.copy(
                    resolutionState = resolutionState,
                    resolutionAtMillis = System.currentTimeMillis(),
                ),
            ),
        ),
    )
}

internal fun classifySyncFailure(error: Throwable?): String =
    when (error) {
        is IOException -> SyncFailureKinds.TRANSIENT
        is HttpException -> when (error.code()) {
            401, 403 -> SyncFailureKinds.AUTHENTICATION
            409 -> SyncFailureKinds.CONFLICT
            408, 425, 429 -> SyncFailureKinds.TRANSIENT
            in 500..599 -> SyncFailureKinds.TRANSIENT
            in 400..499 -> SyncFailureKinds.VALIDATION
            else -> SyncFailureKinds.TRANSIENT
        }
        else -> SyncFailureKinds.TRANSIENT
    }

private fun Throwable?.httpErrorBody(): String? =
    (this as? HttpException)
        ?.response()
        ?.errorBody()
        ?.string()
        ?.takeIf { it.isNotBlank() }

internal data class NotificationSnapshot<T>(
    val datasetEpoch: String,
    val notifications: List<T>,
)

internal suspend fun fetchAllNotifications(
    api: MedtrackApi,
    type: String? = null,
): NotificationSnapshot<NotificationDto> {
    val notificationsByEventId = linkedMapOf<String, NotificationDto>()
    val seenCursors = mutableSetOf<String>()
    var datasetEpoch: String? = null
    var cursor: String? = null
    var requestCount = 0
    while (true) {
        requestCount += 1
        check(requestCount <= MAX_NOTIFICATION_PAGES) { "Notification pagination exceeded the safety limit." }
        val response = api.notifications(type = type, cursor = cursor, pageSize = NOTIFICATION_PAGE_SIZE)
        UUID.fromString(response.datasetEpoch)
        if (datasetEpoch == null) {
            datasetEpoch = response.datasetEpoch
        } else {
            check(datasetEpoch == response.datasetEpoch) { "Notification dataset epoch changed during snapshot traversal." }
        }
        response.results.forEach { notification ->
            require(notification.eventId.isNotBlank()) { "Notification event_id must be present." }
            notificationsByEventId[notification.eventId] = notification
        }
        val nextCursor = response.nextCursor?.takeIf { it.isNotBlank() } ?: break
        check(nextCursor != cursor && seenCursors.add(nextCursor)) { "Notification pagination cursor repeated." }
        cursor = nextCursor
    }
    return NotificationSnapshot(
        datasetEpoch = requireNotNull(datasetEpoch),
        notifications = notificationsByEventId.values.toList(),
    )
}

internal suspend fun replaceNotificationSnapshot(
    database: MedtrackDatabase,
    ownerAccountId: String,
    type: String?,
    snapshot: NotificationSnapshot<NotificationEntity>,
) {
    database.withTransaction {
        val epochKeys = database.cacheMetadataDao()
            .cacheKeysStartingWith(ownerAccountId, CACHE_KEY_NOTIFICATION_DATASET_EPOCH_PREFIX)
        check(epochKeys.size <= 1) { "Multiple notification dataset epochs are present." }
        val previousEpoch = epochKeys.singleOrNull()?.removePrefix(CACHE_KEY_NOTIFICATION_DATASET_EPOCH_PREFIX)
        if (previousEpoch != null && previousEpoch != snapshot.datasetEpoch) {
            database.notificationDao().clearNotifications(ownerAccountId)
            database.pendingWriteDao().deletePendingWritesByType(
                ownerAccountId,
                PendingWriteTypes.NOTIFICATION_READ,
            )
        }
        if (type == null) {
            database.notificationDao().clearNotifications(ownerAccountId)
        } else {
            database.notificationDao().clearNotificationsByType(ownerAccountId, type)
        }
        database.notificationDao().upsertNotifications(snapshot.notifications)
        database.cacheMetadataDao().deleteKeysStartingWith(
            ownerAccountId,
            CACHE_KEY_NOTIFICATION_DATASET_EPOCH_PREFIX,
        )
        database.cacheMetadataDao().upsertMetadata(
            CacheMetadataEntity(
                ownerAccountId = ownerAccountId,
                cacheKey = CACHE_KEY_NOTIFICATION_DATASET_EPOCH_PREFIX + snapshot.datasetEpoch,
                updatedAtMillis = System.currentTimeMillis(),
            ),
        )
    }
}

private const val MAX_NOTIFICATION_PAGES = 5_000
private const val NOTIFICATION_PAGE_SIZE = 100


private suspend fun MedtrackDatabase.markCacheFresh(ownerAccountId: String, cacheKey: String, now: Long) {
    cacheMetadataDao().upsertMetadata(
        CacheMetadataEntity(ownerAccountId = ownerAccountId, cacheKey = cacheKey, updatedAtMillis = now),
    )
}

private class AccountChangedException : IllegalStateException("Authenticated account changed during sync.")

private fun ensureAccountActive(ownerAccountId: String, activeAccountId: () -> String?) {
    if (activeAccountId() != ownerAccountId) throw AccountChangedException()
}

private fun Throwable.rethrowAccountBoundaryFailure() {
    if (
        this is AccountChangedException ||
        this is AccountGenerationRevokedException ||
        (this is HttpException && code() in setOf(401, 403))
    ) {
        throw this
    }
}

private fun CaseSummaryDto.toEntityForSync(ownerAccountId: String): CaseEntity =
    CaseEntity(
        ownerAccountId = ownerAccountId,
        id = id.toString(),
        uhid = uhid,
        patientName = name,
        age = age,
        sexLabel = sexLabel,
        place = place,
        phoneNumber = phoneNumber,
        category = category.name,
        subcategoryValue = subcategory?.value,
        subcategoryLabel = subcategory?.label,
        status = status,
        diagnosis = diagnosis,
        nextTaskId = nextTask?.id?.toString(),
        nextTaskTitle = nextTask?.title,
        nextTaskDueDate = nextTask?.dueDate,
        latestVitalSummary = latestVital?.summary(),
        isHighRisk = redFlag,
        highRiskReasons = redFlagReasons.joinToString(separator = "\n"),
        updatedAtMillis = System.currentTimeMillis(),
    )

private fun CaseStatsDto.toEntityForSync(
    ownerAccountId: String,
    cacheKey: String,
    updatedAtMillis: Long,
): CaseStatsEntity =
    CaseStatsEntity(
        ownerAccountId = ownerAccountId,
        cacheKey = cacheKey,
        today = today,
        upcoming = upcoming,
        overdue = overdue,
        awaiting = awaiting,
        red = red,
        updatedAtMillis = updatedAtMillis,
    )

private fun TaskDto.toEntityForSync(ownerAccountId: String, caseId: String): TaskEntity =
    TaskEntity(
        ownerAccountId = ownerAccountId,
        id = id.toString(),
        caseId = caseId,
        title = title,
        dueDate = dueDate,
        status = status,
        statusLabel = statusLabel?.takeIf { it.isNotBlank() } ?: status,
        canComplete = canComplete ?: status.uppercase() !in setOf("COMPLETED", "CANCELLED"),
        updatedAtMillis = System.currentTimeMillis(),
    )

private fun VitalDto.toEntityForSync(ownerAccountId: String, caseId: String): VitalEntity =
    VitalEntity(
        ownerAccountId = ownerAccountId,
        id = id.toString(),
        caseId = caseId,
        recordedAt = recordedAt,
        bpSystolic = bpSystolic,
        bpDiastolic = bpDiastolic,
        pulse = pr,
        spo2 = spo2,
        weightKg = weightKg,
        hemoglobin = hemoglobin,
        summary = summary(),
        updatedAtMillis = System.currentTimeMillis(),
    )

private val vitalsThresholdsJsonAdapter = Moshi.Builder()
    .add(KotlinJsonAdapterFactory())
    .build()
    .adapter(VitalsThresholdsDto::class.java)

private val categoryOptionsJsonAdapter = Moshi.Builder()
    .add(KotlinJsonAdapterFactory())
    .build()
    .adapter(CategoriesResponseDto::class.java)

private fun VitalsThresholdsDto.toEntityForSync(ownerAccountId: String, updatedAtMillis: Long): VitalsThresholdEntity =
    VitalsThresholdEntity(
        ownerAccountId = ownerAccountId,
        id = "current",
        payloadJson = vitalsThresholdsJsonAdapter.toJson(this),
        updatedAtMillis = updatedAtMillis,
    )

private fun CategoriesResponseDto.toEntityForSync(ownerAccountId: String, updatedAtMillis: Long): CategoryOptionsEntity =
    CategoryOptionsEntity(
        ownerAccountId = ownerAccountId,
        id = "current",
        payloadJson = categoryOptionsJsonAdapter.toJson(this),
        updatedAtMillis = updatedAtMillis,
    )

private fun NotificationDto.toEntityForSync(ownerAccountId: String): NotificationEntity =
    NotificationEntity(
        ownerAccountId = ownerAccountId,
        id = id.toString(),
        type = type,
        title = title,
        body = body,
        caseId = caseId?.toString(),
        taskId = taskId?.toString(),
        createdAt = createdAt,
        isRead = readAt != null,
        payloadJson = notificationPayloadToJson(payload.orEmpty() + ("event_id" to eventId)),
    )

private fun VitalDto.summary(): String {
    val parts = buildList {
        if (bpSystolic != null && bpDiastolic != null) add("BP $bpSystolic/$bpDiastolic")
        if (pr != null) add("PR $pr")
        if (spo2 != null) add("SpO2 $spo2")
        if (!hemoglobin.isNullOrBlank()) add("Hb $hemoglobin")
    }
    return parts.joinToString(" | ")
}
