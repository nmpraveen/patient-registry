package com.naveenhospital.medtrack.core.data.sync

import android.content.Context
import androidx.work.Constraints
import androidx.work.CoroutineWorker
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.ExistingWorkPolicy
import androidx.work.NetworkType
import androidx.work.OneTimeWorkRequest
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.PeriodicWorkRequest
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import androidx.work.workDataOf
import androidx.room.withTransaction
import com.naveenhospital.medtrack.core.data.auth.TokenStore
import com.naveenhospital.medtrack.core.data.local.CacheMetadataEntity
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
import java.security.MessageDigest
import android.util.Base64
import retrofit2.HttpException

class MedtrackSyncWorker(
    appContext: Context,
    params: WorkerParameters,
) : CoroutineWorker(appContext, params) {
    override suspend fun doWork(): Result {
        val baseUrl = inputData.getString(KEY_BASE_URL) ?: return Result.failure()
        val ownerAccountId = inputData.getString(KEY_ACCOUNT_ID)?.takeIf { it.isNotBlank() }
            ?: return Result.failure()
        val tokenStore = TokenStore(applicationContext)
        if (tokenStore.accountId() != ownerAccountId) return Result.success()
        val refreshToken = tokenStore.refreshTokenFor(ownerAccountId) ?: return Result.failure()

        val session = runCatching {
            MedtrackNetwork.create(baseUrl).refresh(RefreshTokenRequestDto(refresh = refreshToken))
        }.getOrElse { error ->
            if (error is HttpException && error.code() in 400..499) {
                tokenStore.clear()
                return Result.failure()
            }
            return Result.retry()
        }
        val verifiedProfile = runCatching {
            MedtrackNetwork.create(
                baseUrl = baseUrl,
                accessTokenProvider = { session.access },
            ).me()
        }.getOrElse { error ->
            if (error is HttpException && error.code() in 400..499) {
                tokenStore.clear()
                return Result.failure()
            }
            return Result.retry()
        }
        if (verifiedProfile.id.toString() != ownerAccountId || tokenStore.accountId() != ownerAccountId) {
            tokenStore.clear()
            return Result.failure()
        }
        if (!tokenStore.updateSessionForAccount(ownerAccountId, session.access, session.refresh)) {
            return Result.failure()
        }
        val api = MedtrackNetwork.create(
            baseUrl = baseUrl,
            accessTokenProvider = { tokenStore.accessTokenFor(ownerAccountId) },
            refreshTokenProvider = { tokenStore.refreshTokenFor(ownerAccountId) },
            sessionUpdater = { access, refresh ->
                tokenStore.updateSessionForAccount(ownerAccountId, access, refresh)
            },
        )
        val database = MedtrackDatabase.build(applicationContext)

        if (!drainPendingWritesForSync(
                api = api,
                database = database,
                ownerAccountId = ownerAccountId,
                activeAccountId = tokenStore::accountId,
            )
        ) {
            return Result.retry()
        }
        if (!syncPendingPushTokens(api = api, database = database, ownerAccountId = ownerAccountId)) {
            return Result.retry()
        }
        if (tokenStore.accountId() != ownerAccountId) return Result.success()
        refreshStaleReadCaches(api = api, database = database, ownerAccountId = ownerAccountId)
        return Result.success()
    }

    private suspend fun refreshStaleReadCaches(
        api: com.naveenhospital.medtrack.core.network.api.MedtrackApi,
        database: MedtrackDatabase,
        ownerAccountId: String,
    ) {
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
            database.withTransaction {
                database.caseDao().clearCases(ownerAccountId)
                database.caseDao().upsertCases(response.results.map { it.toEntityForSync(ownerAccountId) })
                database.caseStatsDao().upsertStats(response.stats.toEntityForSync(ownerAccountId, defaultCaseListKey, now))
                database.markCacheFresh(ownerAccountId, defaultCaseListKey, now)
            }
        }

        if (database.shouldRefresh(ownerAccountId, CACHE_KEY_VITALS_THRESHOLDS, now)) {
            database.vitalsThresholdDao().upsertThresholds(api.vitalsThresholds().toEntityForSync(ownerAccountId, now))
            database.markCacheFresh(ownerAccountId, CACHE_KEY_VITALS_THRESHOLDS, now)
        }

        if (database.shouldRefresh(ownerAccountId, CACHE_KEY_CATEGORY_OPTIONS, now)) {
            database.categoryOptionsDao().upsertOptions(api.categories().toEntityForSync(ownerAccountId, now))
            database.markCacheFresh(ownerAccountId, CACHE_KEY_CATEGORY_OPTIONS, now)
        }

        if (database.shouldRefresh(ownerAccountId, CACHE_KEY_NOTIFICATIONS, now)) {
            database.notificationDao().upsertNotifications(api.notifications().results.map { it.toEntityForSync(ownerAccountId) })
            database.markCacheFresh(ownerAccountId, CACHE_KEY_NOTIFICATIONS, now)
        }

        database.cacheMetadataDao().cacheKeysStartingWith(ownerAccountId, CASE_DETAIL_CACHE_PREFIX).forEach { cacheKey ->
            if (!database.shouldRefresh(ownerAccountId, cacheKey, now)) {
                return@forEach
            }
            val caseId = cacheKey.removePrefix(CASE_DETAIL_CACHE_PREFIX).takeIf { it.isNotBlank() }
                ?: return@forEach
            runCatching {
                refreshServerCase(api = api, database = database, ownerAccountId = ownerAccountId, caseId = caseId)
                database.markCacheFresh(ownerAccountId, caseDetailCacheKey(caseId), now)
            }
        }
    }

    companion object {
        private const val WORK_NAME_PREFIX = "medtrack_periodic_sync"
        private const val ONE_TIME_WORK_NAME_PREFIX = "medtrack_pending_write_sync"
        private const val CASE_DETAIL_CACHE_PREFIX = "case_detail:"
        private const val KEY_BASE_URL = "base_url"
        private const val KEY_ACCOUNT_ID = "account_id"

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

        fun cancelForAccount(context: Context, accountId: String) {
            WorkManager.getInstance(context).cancelUniqueWork(periodicWorkName(accountId))
            WorkManager.getInstance(context).cancelUniqueWork(oneTimeWorkName(accountId))
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

internal suspend fun drainPendingWritesForSync(
    api: MedtrackApi,
    database: MedtrackDatabase,
    ownerAccountId: String,
    activeAccountId: () -> String? = { ownerAccountId },
): Boolean {
    val pendingWriteDao = database.pendingWriteDao()
    pendingWriteDao.pendingWrites(ownerAccountId).forEach { write ->
        if (activeAccountId() != ownerAccountId) return true
        val now = System.currentTimeMillis()
        val result = runCatching {
            ensureAccountActive(ownerAccountId, activeAccountId)
            when (val pendingWrite = PendingWriteJson.decodeForSync(write)) {
                is DecodedPendingWrite.TaskComplete -> {
                    val response = api.completeTask(pendingWrite.taskId, pendingWrite.payload)
                    ensureAccountActive(ownerAccountId, activeAccountId)
                    database.caseDao().upsertCase(response.case.toEntityForSync(ownerAccountId))
                    database.taskDao().upsertTask(response.task.toEntityForSync(ownerAccountId, pendingWrite.caseId))
                }
                is DecodedPendingWrite.CallOutcome -> {
                    val response = api.logCall(pendingWrite.caseId, pendingWrite.payload)
                    ensureAccountActive(ownerAccountId, activeAccountId)
                    database.caseDao().upsertCase(response.case.toEntityForSync(ownerAccountId))
                }
                is DecodedPendingWrite.VitalsCreate -> {
                    val response = api.addVitals(pendingWrite.caseId, pendingWrite.payload)
                    ensureAccountActive(ownerAccountId, activeAccountId)
                    database.caseDao().upsertCase(response.case.toEntityForSync(ownerAccountId))
                    database.vitalDao().deleteVital(ownerAccountId, pendingVitalId(write.clientWriteId))
                    database.vitalDao().upsertVital(response.vital.toEntityForSync(ownerAccountId, pendingWrite.caseId))
                }
                is DecodedPendingWrite.NotificationRead -> {
                    api.markNotificationRead(pendingWrite.notificationId)
                    ensureAccountActive(ownerAccountId, activeAccountId)
                    database.notificationDao().markRead(ownerAccountId, pendingWrite.notificationId)
                }
            }
        }
        if (result.isSuccess) {
            pendingWriteDao.deletePendingWrite(ownerAccountId, write.clientWriteId)
        } else {
            val error = result.exceptionOrNull()
            if (error is AccountChangedException) return true
            if (error is MalformedPendingWriteException) {
                database.recordLocalSyncConflict(
                    ownerAccountId = ownerAccountId,
                    write = write,
                    message = error.message ?: "Malformed pending write.",
                    createdAtMillis = now,
                )
                pendingWriteDao.deletePendingWrite(ownerAccountId, write.clientWriteId)
                return@forEach
            }
            if (error is HttpException && error.code() == 409) {
                database.syncConflictDao().upsertConflict(
                    SyncConflictEntity(
                        ownerAccountId = ownerAccountId,
                        clientWriteId = write.clientWriteId,
                        writeType = write.writeType,
                        caseId = write.caseId,
                        taskId = write.taskId,
                        message = error.conflictMessage(),
                        serverPayloadJson = null,
                        createdAtMillis = now,
                    ),
                )
                pendingWriteDao.deletePendingWrite(ownerAccountId, write.clientWriteId)
                write.caseId?.let { caseId ->
                    runCatching { refreshServerCase(api = api, database = database, ownerAccountId = ownerAccountId, caseId = caseId) }
                }
                return@forEach
            }
            if (error is HttpException && error.code() in 400..499) {
                if (write.writeType != PendingWriteTypes.NOTIFICATION_READ) {
                    database.recordLocalSyncConflict(
                        ownerAccountId = ownerAccountId,
                        write = write,
                        message = error.rejectedMessage(),
                        createdAtMillis = now,
                    )
                }
                pendingWriteDao.deletePendingWrite(ownerAccountId, write.clientWriteId)
                write.caseId?.let { caseId ->
                    runCatching { refreshServerCase(api = api, database = database, ownerAccountId = ownerAccountId, caseId = caseId) }
                }
                return@forEach
            }
            pendingWriteDao.markAttempt(
                ownerAccountId = ownerAccountId,
                clientWriteId = write.clientWriteId,
                lastError = error?.message,
                updatedAtMillis = now,
            )
            if (error !is HttpException || error.code() >= 500) {
                return false
            }
        }
    }
    return true
}

private suspend fun syncPendingPushTokens(
    api: MedtrackApi,
    database: MedtrackDatabase,
    ownerAccountId: String,
): Boolean {
    database.pushTokenDao().pendingTokens(ownerAccountId).forEach { token ->
        val result = runCatching {
            api.registerPushToken(
                RegisterPushTokenRequestDto(
                    token = token.token,
                    deviceLabel = token.deviceLabel,
                ),
            )
            database.pushTokenDao().markTokenSynced(ownerAccountId, token.token, System.currentTimeMillis())
        }
        if (result.isFailure) {
            val error = result.exceptionOrNull()
            if (error is HttpException && error.code() in 400..499) {
                database.pushTokenDao().deleteToken(ownerAccountId, token.token)
                return@forEach
            }
            return false
        }
    }
    return true
}

private suspend fun refreshServerCase(
    api: MedtrackApi,
    database: MedtrackDatabase,
    ownerAccountId: String,
    caseId: String,
) {
    val response = api.caseDetail(caseId)
    database.caseDao().upsertCase(response.case.toEntityForSync(ownerAccountId))
    database.taskDao().clearTasksForCase(ownerAccountId, caseId)
    database.taskDao().upsertTasks(response.tasks.map { it.toEntityForSync(ownerAccountId, caseId) })
    database.vitalDao().clearVitalsForCase(ownerAccountId, caseId)
    database.vitalDao().upsertVitals(response.vitals.map { it.toEntityForSync(ownerAccountId, caseId) })
}

private suspend fun MedtrackDatabase.recordLocalSyncConflict(
    ownerAccountId: String,
    write: com.naveenhospital.medtrack.core.data.local.PendingWriteEntity,
    message: String,
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
            serverPayloadJson = null,
            createdAtMillis = createdAtMillis,
        ),
    )
}

private suspend fun MedtrackDatabase.shouldRefresh(ownerAccountId: String, cacheKey: String, now: Long): Boolean =
    !isCacheFresh(cacheMetadataDao().updatedAtMillis(ownerAccountId, cacheKey), now)

private suspend fun MedtrackDatabase.markCacheFresh(ownerAccountId: String, cacheKey: String, now: Long) {
    cacheMetadataDao().upsertMetadata(
        CacheMetadataEntity(ownerAccountId = ownerAccountId, cacheKey = cacheKey, updatedAtMillis = now),
    )
}

private class AccountChangedException : IllegalStateException("Authenticated account changed during sync.")

private fun ensureAccountActive(ownerAccountId: String, activeAccountId: () -> String?) {
    if (activeAccountId() != ownerAccountId) throw AccountChangedException()
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
        payloadJson = notificationPayloadToJson(payload),
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

private fun HttpException.conflictMessage(): String =
    response()?.errorBody()?.string()?.takeIf { it.isNotBlank() } ?: "The server version was kept."

private fun HttpException.rejectedMessage(): String =
    "Server rejected offline change (${code()}). ${conflictMessage()}"
