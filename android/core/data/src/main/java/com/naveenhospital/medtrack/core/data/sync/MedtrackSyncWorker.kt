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
import retrofit2.HttpException

class MedtrackSyncWorker(
    appContext: Context,
    params: WorkerParameters,
) : CoroutineWorker(appContext, params) {
    override suspend fun doWork(): Result {
        val baseUrl = inputData.getString(KEY_BASE_URL) ?: return Result.failure()
        val tokenStore = TokenStore(applicationContext)
        val refreshToken = tokenStore.refreshToken() ?: return Result.retry()
        val api = MedtrackNetwork.create(
            baseUrl = baseUrl,
            accessTokenProvider = { tokenStore.accessToken },
            refreshTokenProvider = { tokenStore.refreshToken() },
            sessionUpdater = { access, refresh -> tokenStore.saveSession(access = access, refresh = refresh) },
        )
        val database = MedtrackDatabase.build(applicationContext)

        runCatching {
            val session = api.refresh(RefreshTokenRequestDto(refresh = refreshToken))
            tokenStore.saveSession(access = session.access, refresh = session.refresh)
        }.getOrElse {
            return Result.retry()
        }

        if (!drainPendingWritesForSync(api = api, database = database)) {
            return Result.retry()
        }
        if (!syncPendingPushTokens(api = api, database = database)) {
            return Result.retry()
        }
        refreshStaleReadCaches(api = api, database = database)
        return Result.success()
    }

    private suspend fun refreshStaleReadCaches(
        api: com.naveenhospital.medtrack.core.network.api.MedtrackApi,
        database: MedtrackDatabase,
    ) {
        val now = System.currentTimeMillis()
        val defaultCaseListKey = caseListCacheKey(
            bucket = "today",
            query = null,
            assignedTo = "me",
            categories = emptyList(),
            subcategories = emptyList(),
        )
        if (database.shouldRefresh(defaultCaseListKey, now)) {
            val response = api.listCases(bucket = "today", assignedTo = "me", page = 1)
            database.withTransaction {
                database.caseDao().clearCases()
                database.caseDao().upsertCases(response.results.map { it.toEntityForSync() })
                database.caseStatsDao().upsertStats(response.stats.toEntityForSync(defaultCaseListKey, now))
                database.markCacheFresh(defaultCaseListKey, now)
            }
        }

        if (database.shouldRefresh(CACHE_KEY_VITALS_THRESHOLDS, now)) {
            database.vitalsThresholdDao().upsertThresholds(api.vitalsThresholds().toEntityForSync(now))
            database.markCacheFresh(CACHE_KEY_VITALS_THRESHOLDS, now)
        }

        if (database.shouldRefresh(CACHE_KEY_CATEGORY_OPTIONS, now)) {
            database.categoryOptionsDao().upsertOptions(api.categories().toEntityForSync(now))
            database.markCacheFresh(CACHE_KEY_CATEGORY_OPTIONS, now)
        }

        if (database.shouldRefresh(CACHE_KEY_NOTIFICATIONS, now)) {
            database.notificationDao().upsertNotifications(api.notifications().results.map { it.toEntityForSync() })
            database.markCacheFresh(CACHE_KEY_NOTIFICATIONS, now)
        }

        database.cacheMetadataDao().cacheKeysStartingWith(CASE_DETAIL_CACHE_PREFIX).forEach { cacheKey ->
            if (!database.shouldRefresh(cacheKey, now)) {
                return@forEach
            }
            val caseId = cacheKey.removePrefix(CASE_DETAIL_CACHE_PREFIX).takeIf { it.isNotBlank() }
                ?: return@forEach
            runCatching {
                refreshServerCase(api = api, database = database, caseId = caseId)
                database.markCacheFresh(caseDetailCacheKey(caseId), now)
            }
        }
    }

    companion object {
        const val WORK_NAME = "medtrack_periodic_sync"
        const val ONE_TIME_WORK_NAME = "medtrack_pending_write_sync"
        private const val CASE_DETAIL_CACHE_PREFIX = "case_detail:"
        private const val KEY_BASE_URL = "base_url"

        fun enqueue(context: Context, baseUrl: String) {
            WorkManager.getInstance(context).enqueueUniquePeriodicWork(
                WORK_NAME,
                ExistingPeriodicWorkPolicy.UPDATE,
                periodicRequest(baseUrl),
            )
        }

        fun enqueueOneTime(context: Context, baseUrl: String) {
            WorkManager.getInstance(context).enqueueUniqueWork(
                ONE_TIME_WORK_NAME,
                ExistingWorkPolicy.APPEND_OR_REPLACE,
                oneTimeRequest(baseUrl),
            )
        }

        fun periodicRequest(baseUrl: String): PeriodicWorkRequest =
            PeriodicWorkRequestBuilder<MedtrackSyncWorker>(15, TimeUnit.MINUTES)
                .setConstraints(
                    Constraints.Builder()
                        .setRequiredNetworkType(NetworkType.CONNECTED)
                        .build(),
                )
                .setInputData(workDataOf(KEY_BASE_URL to baseUrl))
                .build()

        fun oneTimeRequest(baseUrl: String): OneTimeWorkRequest =
            OneTimeWorkRequestBuilder<MedtrackSyncWorker>()
                .setConstraints(
                    Constraints.Builder()
                        .setRequiredNetworkType(NetworkType.CONNECTED)
                        .build(),
                )
                .setInputData(workDataOf(KEY_BASE_URL to baseUrl))
                .build()
    }
}

internal suspend fun drainPendingWritesForSync(
    api: MedtrackApi,
    database: MedtrackDatabase,
): Boolean {
    val pendingWriteDao = database.pendingWriteDao()
    pendingWriteDao.pendingWrites().forEach { write ->
        val now = System.currentTimeMillis()
        val result = runCatching {
            when (val pendingWrite = PendingWriteJson.decodeForSync(write)) {
                is DecodedPendingWrite.TaskComplete -> {
                    val response = api.completeTask(pendingWrite.taskId, pendingWrite.payload)
                    database.caseDao().upsertCase(response.case.toEntityForSync())
                    database.taskDao().upsertTask(response.task.toEntityForSync(pendingWrite.caseId))
                }
                is DecodedPendingWrite.CallOutcome -> {
                    val response = api.logCall(pendingWrite.caseId, pendingWrite.payload)
                    database.caseDao().upsertCase(response.case.toEntityForSync())
                }
                is DecodedPendingWrite.VitalsCreate -> {
                    val response = api.addVitals(pendingWrite.caseId, pendingWrite.payload)
                    database.caseDao().upsertCase(response.case.toEntityForSync())
                    database.vitalDao().deleteVital(pendingVitalId(write.clientWriteId))
                    database.vitalDao().upsertVital(response.vital.toEntityForSync(pendingWrite.caseId))
                }
                is DecodedPendingWrite.NotificationRead -> {
                    api.markNotificationRead(pendingWrite.notificationId)
                    database.notificationDao().markRead(pendingWrite.notificationId)
                }
            }
        }
        if (result.isSuccess) {
            pendingWriteDao.deletePendingWrite(write.clientWriteId)
        } else {
            val error = result.exceptionOrNull()
            if (error is MalformedPendingWriteException) {
                database.recordLocalSyncConflict(
                    write = write,
                    message = error.message ?: "Malformed pending write.",
                    createdAtMillis = now,
                )
                pendingWriteDao.deletePendingWrite(write.clientWriteId)
                return@forEach
            }
            if (error is HttpException && error.code() == 409) {
                database.syncConflictDao().upsertConflict(
                    SyncConflictEntity(
                        clientWriteId = write.clientWriteId,
                        writeType = write.writeType,
                        caseId = write.caseId,
                        taskId = write.taskId,
                        message = error.conflictMessage(),
                        serverPayloadJson = null,
                        createdAtMillis = now,
                    ),
                )
                pendingWriteDao.deletePendingWrite(write.clientWriteId)
                write.caseId?.let { caseId ->
                    runCatching { refreshServerCase(api = api, database = database, caseId = caseId) }
                }
                return@forEach
            }
            if (error is HttpException && error.code() in 400..499) {
                if (write.writeType != PendingWriteTypes.NOTIFICATION_READ) {
                    database.recordLocalSyncConflict(
                        write = write,
                        message = error.rejectedMessage(),
                        createdAtMillis = now,
                    )
                }
                pendingWriteDao.deletePendingWrite(write.clientWriteId)
                write.caseId?.let { caseId ->
                    runCatching { refreshServerCase(api = api, database = database, caseId = caseId) }
                }
                return@forEach
            }
            pendingWriteDao.markAttempt(
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
): Boolean {
    database.pushTokenDao().pendingTokens().forEach { token ->
        val result = runCatching {
            api.registerPushToken(
                RegisterPushTokenRequestDto(
                    token = token.token,
                    deviceLabel = token.deviceLabel,
                ),
            )
            database.pushTokenDao().markTokenSynced(token.token, System.currentTimeMillis())
        }
        if (result.isFailure) {
            val error = result.exceptionOrNull()
            if (error is HttpException && error.code() in 400..499) {
                database.pushTokenDao().deleteToken(token.token)
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
    caseId: String,
) {
    val response = api.caseDetail(caseId)
    database.caseDao().upsertCase(response.case.toEntityForSync())
    database.taskDao().clearTasksForCase(caseId)
    database.taskDao().upsertTasks(response.tasks.map { it.toEntityForSync(caseId) })
    database.vitalDao().clearVitalsForCase(caseId)
    database.vitalDao().upsertVitals(response.vitals.map { it.toEntityForSync(caseId) })
}

private suspend fun MedtrackDatabase.recordLocalSyncConflict(
    write: com.naveenhospital.medtrack.core.data.local.PendingWriteEntity,
    message: String,
    createdAtMillis: Long,
) {
    syncConflictDao().upsertConflict(
        SyncConflictEntity(
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

private suspend fun MedtrackDatabase.shouldRefresh(cacheKey: String, now: Long): Boolean =
    !isCacheFresh(cacheMetadataDao().updatedAtMillis(cacheKey), now)

private suspend fun MedtrackDatabase.markCacheFresh(cacheKey: String, now: Long) {
    cacheMetadataDao().upsertMetadata(CacheMetadataEntity(cacheKey = cacheKey, updatedAtMillis = now))
}

private fun CaseSummaryDto.toEntityForSync(): CaseEntity =
    CaseEntity(
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

private fun CaseStatsDto.toEntityForSync(cacheKey: String, updatedAtMillis: Long): CaseStatsEntity =
    CaseStatsEntity(
        cacheKey = cacheKey,
        today = today,
        upcoming = upcoming,
        overdue = overdue,
        awaiting = awaiting,
        red = red,
        updatedAtMillis = updatedAtMillis,
    )

private fun TaskDto.toEntityForSync(caseId: String): TaskEntity =
    TaskEntity(
        id = id.toString(),
        caseId = caseId,
        title = title,
        dueDate = dueDate,
        status = status,
        statusLabel = statusLabel?.takeIf { it.isNotBlank() } ?: status,
        canComplete = canComplete ?: status.uppercase() !in setOf("COMPLETED", "CANCELLED"),
        updatedAtMillis = System.currentTimeMillis(),
    )

private fun VitalDto.toEntityForSync(caseId: String): VitalEntity =
    VitalEntity(
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

private fun VitalsThresholdsDto.toEntityForSync(updatedAtMillis: Long): VitalsThresholdEntity =
    VitalsThresholdEntity(
        id = "current",
        payloadJson = vitalsThresholdsJsonAdapter.toJson(this),
        updatedAtMillis = updatedAtMillis,
    )

private fun CategoriesResponseDto.toEntityForSync(updatedAtMillis: Long): CategoryOptionsEntity =
    CategoryOptionsEntity(
        id = "current",
        payloadJson = categoryOptionsJsonAdapter.toJson(this),
        updatedAtMillis = updatedAtMillis,
    )

private fun NotificationDto.toEntityForSync(): NotificationEntity =
    NotificationEntity(
        id = id.toString(),
        type = type,
        title = title,
        body = body,
        caseId = caseId?.toString(),
        taskId = taskId?.toString(),
        createdAt = createdAt,
        isRead = readAt != null,
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
