package com.naveenhospital.medtrack.core.data.repository

import androidx.paging.ExperimentalPagingApi
import androidx.paging.LoadType
import androidx.paging.Pager
import androidx.paging.PagingConfig
import androidx.paging.PagingData
import androidx.paging.PagingState
import androidx.paging.RemoteMediator
import androidx.paging.map
import androidx.room.withTransaction
import com.naveenhospital.medtrack.core.data.local.CaseEntity
import com.naveenhospital.medtrack.core.data.local.CaseStatsEntity
import com.naveenhospital.medtrack.core.data.local.CacheMetadataEntity
import com.naveenhospital.medtrack.core.data.local.CategoryOptionsEntity
import com.naveenhospital.medtrack.core.data.local.MedtrackDatabase
import com.naveenhospital.medtrack.core.data.local.NotificationEntity
import com.naveenhospital.medtrack.core.data.notification.notificationPayloadToJson
import com.naveenhospital.medtrack.core.data.notification.parseNotificationPayload
import com.naveenhospital.medtrack.core.data.local.PendingWriteEntity
import com.naveenhospital.medtrack.core.data.local.PushTokenEntity
import com.naveenhospital.medtrack.core.data.local.SyncConflictEntity
import com.naveenhospital.medtrack.core.data.local.TaskEntity
import com.naveenhospital.medtrack.core.data.local.VitalEntity
import com.naveenhospital.medtrack.core.data.local.VitalsThresholdEntity
import com.naveenhospital.medtrack.core.data.sync.PendingWriteJson
import com.naveenhospital.medtrack.core.data.sync.PendingWriteTypes
import com.naveenhospital.medtrack.core.data.sync.NotificationReadPayload
import com.naveenhospital.medtrack.core.domain.model.CaseCategory
import com.naveenhospital.medtrack.core.domain.model.CaseCreateOutcome
import com.naveenhospital.medtrack.core.domain.model.CaseEditOutcome
import com.naveenhospital.medtrack.core.domain.model.CaseEditPrefill
import com.naveenhospital.medtrack.core.domain.model.CaseFormCategory
import com.naveenhospital.medtrack.core.domain.model.CaseFormMetadata
import com.naveenhospital.medtrack.core.domain.model.CaseStatus
import com.naveenhospital.medtrack.core.domain.model.CategoryFilterOption
import com.naveenhospital.medtrack.core.domain.model.FormChoice
import com.naveenhospital.medtrack.core.domain.model.InboxStats
import com.naveenhospital.medtrack.core.domain.model.NewCaseInput
import com.naveenhospital.medtrack.core.domain.model.NewTaskInput
import com.naveenhospital.medtrack.core.domain.model.TaskAssignee
import com.naveenhospital.medtrack.core.domain.model.TaskEditInput
import com.naveenhospital.medtrack.core.domain.model.TaskFormMetadata
import com.naveenhospital.medtrack.core.domain.model.TaskWriteOutcome
import com.naveenhospital.medtrack.core.domain.model.VitalsWriteOutcome
import com.naveenhospital.medtrack.core.domain.model.PatientLookup
import com.naveenhospital.medtrack.core.domain.model.NotificationItem
import com.naveenhospital.medtrack.core.domain.model.PatientCase
import com.naveenhospital.medtrack.core.domain.model.PatientTask
import com.naveenhospital.medtrack.core.domain.model.PatientVital
import com.naveenhospital.medtrack.core.domain.model.SubcategoryFilterOption
import com.naveenhospital.medtrack.core.domain.model.SyncConflict
import com.naveenhospital.medtrack.core.domain.model.VitalsThresholdConfig
import com.naveenhospital.medtrack.core.domain.model.WriteResult
import com.naveenhospital.medtrack.core.network.api.MedtrackApi
import com.naveenhospital.medtrack.core.network.model.CaseCreateErrorDto
import com.naveenhospital.medtrack.core.network.model.CaseFormMetadataDto
import com.naveenhospital.medtrack.core.network.model.CategoriesResponseDto
import com.naveenhospital.medtrack.core.network.model.CaseCategoryDto
import com.naveenhospital.medtrack.core.network.model.ChoiceDto
import com.naveenhospital.medtrack.core.network.model.CreateCaseRequestDto
import com.naveenhospital.medtrack.core.network.model.CaseEditFormDto
import com.naveenhospital.medtrack.core.network.model.CreateTaskRequestDto
import com.naveenhospital.medtrack.core.network.model.TaskFormMetadataDto
import com.naveenhospital.medtrack.core.network.model.TaskNoteRequestDto
import com.naveenhospital.medtrack.core.network.model.UpdateTaskRequestDto
import com.naveenhospital.medtrack.core.network.model.VitalsUpdateRequestDto
import com.naveenhospital.medtrack.core.network.model.PatientLookupDto
import com.naveenhospital.medtrack.core.network.model.CaseListResponseDto
import com.naveenhospital.medtrack.core.network.model.CaseStatsDto
import com.naveenhospital.medtrack.core.network.model.CaseSummaryDto
import com.naveenhospital.medtrack.core.network.model.CaseSubcategoryDto
import com.naveenhospital.medtrack.core.network.model.ClientWriteRequestDto
import com.naveenhospital.medtrack.core.network.model.LogCallRequestDto
import com.naveenhospital.medtrack.core.network.model.NotificationDto
import com.naveenhospital.medtrack.core.network.model.RegisterPushTokenRequestDto
import com.naveenhospital.medtrack.core.network.model.TaskDto
import com.naveenhospital.medtrack.core.network.model.VitalDto
import com.naveenhospital.medtrack.core.network.model.VitalsRequestDto
import com.naveenhospital.medtrack.core.network.model.VitalsThresholdsDto
import com.squareup.moshi.Moshi
import com.squareup.moshi.kotlin.reflect.KotlinJsonAdapterFactory
import java.io.IOException
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.TimeZone
import java.util.UUID
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.map
import retrofit2.HttpException

const val CACHE_TTL_MILLIS: Long = 60 * 60 * 1000L
const val CACHE_KEY_CATEGORY_OPTIONS = "category_options"
const val CACHE_KEY_VITALS_THRESHOLDS = "vitals_thresholds"
const val CACHE_KEY_NOTIFICATIONS = "notifications"
private const val CASE_PAGE_SIZE = 20

class MedtrackRepository(
    private val api: MedtrackApi,
    private val database: MedtrackDatabase,
    private val onPendingWriteQueued: () -> Unit = {},
) {
    private val _stats = MutableStateFlow(InboxStats())
    val stats: StateFlow<InboxStats> = _stats
    private val _categoryOptions = MutableStateFlow<List<CategoryFilterOption>>(emptyList())
    val categoryOptions: StateFlow<List<CategoryFilterOption>> = _categoryOptions
    private val _vitalsThresholds = MutableStateFlow<VitalsThresholdConfig?>(null)
    val vitalsThresholds: StateFlow<VitalsThresholdConfig?> = _vitalsThresholds
    private val _hasMoreCases = MutableStateFlow(false)
    val hasMoreCases: StateFlow<Boolean> = _hasMoreCases
    private var nextCasePage: Int? = null
    private var activeCaseListKey: String = ""
    private val caseCreateErrorAdapter =
        Moshi.Builder().add(KotlinJsonAdapterFactory()).build().adapter(CaseCreateErrorDto::class.java)

    val cases: Flow<List<PatientCase>> =
        database.caseDao().observeCases().map { entities -> entities.map { it.toDomain() } }

    @OptIn(ExperimentalPagingApi::class)
    fun pagedCases(
        bucket: String? = "today",
        query: String? = null,
        assignedTo: String? = null,
        scopeContext: String? = null,
        categories: List<String> = emptyList(),
        subcategories: List<String> = emptyList(),
    ): Flow<PagingData<PatientCase>> {
        val cacheKey = caseListCacheKey(bucket, query, assignedTo, scopeContext, categories, subcategories)
        activeCaseListKey = cacheKey
        return Pager(
            config = PagingConfig(
                pageSize = CASE_PAGE_SIZE,
                prefetchDistance = 6,
                enablePlaceholders = false,
            ),
            remoteMediator = CaseRemoteMediator(
                api = api,
                database = database,
                cacheKey = cacheKey,
                bucket = bucket,
                query = query,
                assignedTo = assignedTo,
                scopeContext = scopeContext,
                categories = categories,
                subcategories = subcategories,
                onStats = { stats -> _stats.value = stats },
            ),
            pagingSourceFactory = { database.caseDao().pagingSource() },
        ).flow.map { pagingData -> pagingData.map { entity -> entity.toDomain() } }
    }

    val notifications: Flow<List<NotificationItem>> =
        database.notificationDao().observeNotifications().map { entities -> entities.map { it.toDomain() } }

    val pendingWriteCount: Flow<Int> =
        database.pendingWriteDao().observePendingWriteCount()

    val syncConflictCount: Flow<Int> =
        database.syncConflictDao().observeConflictCount()

    val syncConflicts: Flow<List<SyncConflict>> =
        database.syncConflictDao().observeConflicts().map { entities -> entities.map { it.toDomain() } }

    fun observeCase(caseId: String): Flow<PatientCase?> =
        database.caseDao().observeCase(caseId).map { it?.toDomain() }

    fun observeTasks(caseId: String): Flow<List<PatientTask>> =
        database.taskDao().observeTasksForCase(caseId).map { entities -> entities.map { it.toDomain() } }

    fun observeVitals(caseId: String): Flow<List<PatientVital>> =
        database.vitalDao().observeVitalsForCase(caseId).map { entities -> entities.map { it.toDomain() } }

    suspend fun refreshCases(
        bucket: String? = "today",
        query: String? = null,
        assignedTo: String? = null,
        scopeContext: String? = null,
        categories: List<String> = emptyList(),
        subcategories: List<String> = emptyList(),
    ) {
        activeCaseListKey = caseListCacheKey(bucket, query, assignedTo, scopeContext, categories, subcategories)
        database.caseStatsDao().statsForKey(activeCaseListKey)?.let { cachedStats ->
            _stats.value = cachedStats.toDomain()
        }
        val response = api.listCases(
            bucket = bucket ?: "all",
            query = query?.takeIf { it.isNotBlank() },
            assignedTo = assignedTo,
            scopeContext = scopeContext,
            categories = categories.takeIf { it.isNotEmpty() },
            subcategories = subcategories.takeIf { it.isNotEmpty() },
            page = 1,
        )
        _stats.value = response.stats.toDomain()
        nextCasePage = response.nextPageAfter(1)
        _hasMoreCases.value = nextCasePage != null
        database.caseDao().clearCases()
        database.caseDao().upsertCases(response.results.map { it.toEntity() })
        database.caseStatsDao().upsertStats(response.stats.toEntity(activeCaseListKey))
        markCacheFresh(caseListCacheKey(bucket, query, assignedTo, scopeContext, categories, subcategories))
    }

    suspend fun loadNextCases(
        bucket: String? = "today",
        query: String? = null,
        assignedTo: String? = null,
        scopeContext: String? = null,
        categories: List<String> = emptyList(),
        subcategories: List<String> = emptyList(),
    ) {
        val requestedKey = caseListCacheKey(bucket, query, assignedTo, scopeContext, categories, subcategories)
        if (requestedKey != activeCaseListKey) {
            refreshCases(
                bucket = bucket,
                query = query,
                assignedTo = assignedTo,
                scopeContext = scopeContext,
                categories = categories,
                subcategories = subcategories,
            )
            return
        }
        val page = nextCasePage ?: return
        val response = api.listCases(
            bucket = bucket ?: "all",
            query = query?.takeIf { it.isNotBlank() },
            assignedTo = assignedTo,
            scopeContext = scopeContext,
            categories = categories.takeIf { it.isNotEmpty() },
            subcategories = subcategories.takeIf { it.isNotEmpty() },
            page = page,
        )
        _stats.value = response.stats.toDomain()
        nextCasePage = response.nextPageAfter(page)
        _hasMoreCases.value = nextCasePage != null
        database.caseDao().upsertCases(response.results.map { it.toEntity() })
        database.caseStatsDao().upsertStats(response.stats.toEntity(requestedKey))
    }

    suspend fun loadCaseFormMetadata(): CaseFormMetadata = api.caseFormMetadata().toDomain()

    suspend fun searchPatients(query: String): List<PatientLookup> =
        api.searchPatients(query = query.trim().ifBlank { null }).results.map { it.toDomain() }

    suspend fun createCase(input: NewCaseInput): CaseCreateOutcome {
        val request = input.toRequestDto(newClientWriteId("case"))
        return runCatching {
            val response = api.createCase(request)
            database.caseDao().upsertCase(response.case.toEntity())
            CaseCreateOutcome.Success(caseId = response.caseId, message = response.message)
        }.getOrElse { throwable ->
            if (throwable is HttpException && throwable.code() == 400) {
                val parsed = runCatching {
                    caseCreateErrorAdapter.fromJson(throwable.response()?.errorBody()?.string().orEmpty())
                }.getOrNull()
                CaseCreateOutcome.ValidationError(
                    errors = parsed?.errors ?: emptyMap(),
                    message = parsed?.message ?: "Please fix the highlighted fields.",
                )
            } else {
                throw throwable
            }
        }
    }

    suspend fun loadCaseEditForm(caseId: String): CaseEditPrefill =
        api.caseEditForm(caseId).toDomain()

    suspend fun updateCase(caseId: String, input: NewCaseInput): CaseEditOutcome {
        val request = input.toRequestDto(newClientWriteId("case-edit"))
        return runCatching {
            val response = api.updateCase(caseId, request)
            database.caseDao().upsertCase(response.case.toEntity())
            CaseEditOutcome.Success(caseId = response.caseId, message = response.message)
        }.getOrElse { throwable ->
            parseFormErrors(throwable)?.let {
                CaseEditOutcome.ValidationError(errors = it.errors, message = it.message ?: "Please fix the highlighted fields.")
            } ?: CaseEditOutcome.Failure(throwable.message ?: "Could not save the case. Try again.")
        }
    }

    suspend fun loadTaskFormMetadata(): TaskFormMetadata = api.taskFormMetadata().toDomain()

    suspend fun createTask(caseId: String, input: NewTaskInput): TaskWriteOutcome {
        val request = CreateTaskRequestDto(
            title = input.title,
            dueDate = input.dueDate,
            status = input.status,
            taskType = input.taskType,
            assignedUser = input.assignedUserId,
            notes = input.notes?.takeIf { it.isNotBlank() },
            clientWriteId = newClientWriteId("task-create"),
        )
        return runCatching {
            val response = api.createTask(caseId, request)
            database.caseDao().upsertCase(response.case.toEntity())
            database.taskDao().upsertTask(response.task.toEntity(caseId))
            TaskWriteOutcome.Success(response.message)
        }.getOrElse { throwable -> throwable.toTaskOutcome() }
    }

    suspend fun updateTask(taskId: String, caseId: String, input: TaskEditInput): TaskWriteOutcome {
        val assignedUserValue = when {
            input.assignedUserId != null -> input.assignedUserId.toString()
            input.clearAssignee -> "" // explicit unassign
            else -> null // omitted -> server keeps current assignee
        }
        val request = UpdateTaskRequestDto(
            title = input.title,
            dueDate = input.dueDate,
            status = input.status,
            taskType = input.taskType,
            assignedUser = assignedUserValue,
        )
        return runCatching {
            val response = api.updateTask(taskId, request)
            database.caseDao().upsertCase(response.case.toEntity())
            database.taskDao().upsertTask(response.task.toEntity(caseId))
            TaskWriteOutcome.Success(response.message)
        }.getOrElse { throwable -> throwable.toTaskOutcome() }
    }

    suspend fun addTaskNote(taskId: String, caseId: String, note: String): TaskWriteOutcome {
        return runCatching {
            val response = api.addTaskNote(taskId, TaskNoteRequestDto(note = note))
            database.caseDao().upsertCase(response.case.toEntity())
            database.taskDao().upsertTask(response.task.toEntity(caseId))
            TaskWriteOutcome.Success(response.message)
        }.getOrElse { throwable -> throwable.toTaskOutcome() }
    }

    suspend fun updateVitals(
        vitalId: String,
        caseId: String,
        bpSystolic: Int?,
        bpDiastolic: Int?,
        pulse: Int?,
        spo2: Int?,
        weightKg: String?,
        hemoglobin: String?,
    ): VitalsWriteOutcome {
        val request = VitalsUpdateRequestDto(
            bpSystolic = bpSystolic,
            bpDiastolic = bpDiastolic,
            pr = pulse,
            spo2 = spo2,
            weightKg = weightKg,
            hemoglobin = hemoglobin,
        )
        return runCatching {
            val response = api.updateVitals(vitalId, request)
            database.caseDao().upsertCase(response.case.toEntity())
            database.vitalDao().upsertVital(response.vital.toEntity(caseId))
            VitalsWriteOutcome.Success(response.message)
        }.getOrElse { throwable ->
            parseFormErrors(throwable)?.let {
                VitalsWriteOutcome.ValidationError(errors = it.errors, message = it.message ?: "Please check the vitals.")
            } ?: VitalsWriteOutcome.Failure(throwable.message ?: "Could not save vitals. Try again.")
        }
    }

    private fun parseFormErrors(throwable: Throwable): CaseCreateErrorDto? {
        val httpError = throwable as? HttpException ?: return null
        if (httpError.code() != 400) return null
        return runCatching {
            caseCreateErrorAdapter.fromJson(httpError.response()?.errorBody()?.string().orEmpty())
        }.getOrNull()
    }

    private fun Throwable.toTaskOutcome(): TaskWriteOutcome {
        parseFormErrors(this)?.let {
            return TaskWriteOutcome.ValidationError(errors = it.errors, message = it.message ?: "Please fix the highlighted fields.")
        }
        if (this is HttpException && code() == 403) {
            return TaskWriteOutcome.Failure("You do not have permission for this action.")
        }
        return TaskWriteOutcome.Failure(message ?: "Could not save the task. Try again.")
    }

    suspend fun loadCachedCategoryOptions() {
        val cached = database.categoryOptionsDao().currentOptions() ?: return
        _categoryOptions.value = cached.toDomain()
    }

    suspend fun refreshCategoryOptions() {
        val response = api.categories()
        _categoryOptions.value = response.categories.map { it.toFilterOption() }
        database.categoryOptionsDao().upsertOptions(response.toEntity())
        markCacheFresh(CACHE_KEY_CATEGORY_OPTIONS)
    }

    suspend fun loadCachedVitalsThresholds() {
        val cached = database.vitalsThresholdDao().currentThresholds() ?: return
        _vitalsThresholds.value = cached.toDomain()
    }

    suspend fun refreshVitalsThresholds() {
        val response = api.vitalsThresholds()
        _vitalsThresholds.value = response.toDomain()
        database.vitalsThresholdDao().upsertThresholds(response.toEntity())
        markCacheFresh(CACHE_KEY_VITALS_THRESHOLDS)
    }

    suspend fun refreshCaseDetail(caseId: String) {
        val response = api.caseDetail(caseId)
        database.caseDao().upsertCase(response.case.toEntity())
        database.taskDao().clearTasksForCase(caseId)
        database.taskDao().upsertTasks(response.tasks.map { it.toEntity(caseId) })
        database.vitalDao().clearVitalsForCase(caseId)
        database.vitalDao().upsertVitals(response.vitals.map { it.toEntity(caseId) })
        markCacheFresh(caseDetailCacheKey(caseId))
    }

    suspend fun refreshNotifications(type: String? = null) {
        // When a Me-page category is open, fetch that type server-side so paginated
        // matches beyond the untyped first page aren't missed by client-side filtering.
        val response = api.notifications(type = type)
        database.notificationDao().upsertNotifications(response.results.map { it.toEntity() })
        // Only a full (untyped) refresh covers every category, so only it may mark the
        // shared cache fresh. A typed refresh must not suppress the global sync, or the
        // Me badge/counts could miss other categories until "All" is opened.
        if (type == null) {
            markCacheFresh(CACHE_KEY_NOTIFICATIONS)
        }
    }

    suspend fun markNotificationRead(notificationId: String) {
        val clientWriteId = newClientWriteId("notification")
        val payload = NotificationReadPayload(
            notificationId = notificationId,
            clientWriteId = clientWriteId,
        )
        database.notificationDao().markRead(notificationId)
        runCatching {
            api.markNotificationRead(notificationId)
        }.getOrElse { throwable ->
            if (!throwable.shouldQueue()) {
                throw throwable
            }
            queuePendingWrite(
                clientWriteId = clientWriteId,
                writeType = PendingWriteTypes.NOTIFICATION_READ,
                caseId = null,
                taskId = notificationId,
                payloadJson = PendingWriteJson.encodeNotificationRead(payload),
                lastError = throwable.message,
            )
            onPendingWriteQueued()
        }
    }

    suspend fun registerPushToken(token: String, deviceLabel: String) {
        database.pushTokenDao().upsertToken(
            PushTokenEntity(
                token = token,
                deviceLabel = deviceLabel,
                syncedAtMillis = 0L,
            ),
        )
        api.registerPushToken(RegisterPushTokenRequestDto(token = token, deviceLabel = deviceLabel))
        database.pushTokenDao().markTokenSynced(token, System.currentTimeMillis())
    }

    suspend fun currentPushTokenForLogout(): String? {
        val dao = database.pushTokenDao()
        return (dao.latestSyncedToken() ?: dao.latestToken())
            ?.token
            ?.takeIf { it.isNotBlank() }
    }

    suspend fun completeTask(taskId: String, caseId: String): WriteResult {
        val clientWriteId = newClientWriteId("task")
        val payload = ClientWriteRequestDto(clientWriteId = clientWriteId)
        return runCatching {
            val response = api.completeTask(taskId = taskId, request = payload)
            database.caseDao().upsertCase(response.case.toEntity())
            database.taskDao().upsertTask(response.task.toEntity(caseId))
            WriteResult(clientWriteId = clientWriteId, queued = false, message = response.message)
        }.getOrElse { throwable ->
            when {
                throwable.isConflict() -> {
                    recordConflict(
                        clientWriteId = clientWriteId,
                        writeType = PendingWriteTypes.TASK_COMPLETE,
                        caseId = caseId,
                        taskId = taskId,
                        error = throwable,
                    )
                    WriteResult(
                        clientWriteId = clientWriteId,
                        queued = false,
                        conflict = true,
                        message = "Server version kept. Review the updated case.",
                    )
                }
                throwable.shouldQueue() -> {
                    queuePendingWrite(
                        clientWriteId = clientWriteId,
                        writeType = PendingWriteTypes.TASK_COMPLETE,
                        caseId = caseId,
                        taskId = taskId,
                        payloadJson = PendingWriteJson.encodeTaskComplete(payload),
                        lastError = throwable.message,
                    )
                    database.taskDao().markTaskCompletedLocally(taskId, System.currentTimeMillis())
                    onPendingWriteQueued()
                    WriteResult(
                        clientWriteId = clientWriteId,
                        queued = true,
                        message = "Task completion queued for sync.",
                    )
                }
                else -> throw throwable
            }
        }
    }

    suspend fun logCallOutcome(
        caseId: String,
        taskId: String?,
        outcome: String,
        note: String?,
        attemptedAt: String? = null,
    ): WriteResult {
        val clientWriteId = newClientWriteId("call")
        val payload = LogCallRequestDto(
            outcome = outcome,
            note = note,
            taskId = taskId?.toLongOrNull(),
            attemptedAt = attemptedAt?.takeIf { it.isNotBlank() } ?: currentUtcTimestamp(),
            clientWriteId = clientWriteId,
        )
        return runCatching {
            val response = api.logCall(caseId = caseId, request = payload)
            database.caseDao().upsertCase(response.case.toEntity())
            WriteResult(clientWriteId = clientWriteId, queued = false, message = response.message)
        }.getOrElse { throwable ->
            when {
                throwable.isConflict() -> {
                    recordConflict(
                        clientWriteId = clientWriteId,
                        writeType = PendingWriteTypes.CALL_OUTCOME,
                        caseId = caseId,
                        taskId = taskId,
                        error = throwable,
                    )
                    WriteResult(
                        clientWriteId = clientWriteId,
                        queued = false,
                        conflict = true,
                        message = "Server version kept. Review the updated case.",
                    )
                }
                throwable.shouldQueue() -> {
                    queuePendingWrite(
                        clientWriteId = clientWriteId,
                        writeType = PendingWriteTypes.CALL_OUTCOME,
                        caseId = caseId,
                        taskId = taskId,
                        payloadJson = PendingWriteJson.encodeCallOutcome(payload),
                        lastError = throwable.message,
                    )
                    onPendingWriteQueued()
                    WriteResult(
                        clientWriteId = clientWriteId,
                        queued = true,
                        message = "Call outcome queued for sync.",
                    )
                }
                else -> throw throwable
            }
        }
    }

    suspend fun addVitals(
        caseId: String,
        bpSystolic: Int?,
        bpDiastolic: Int?,
        pulse: Int?,
        spo2: Int?,
        weightKg: String?,
        hemoglobin: String?,
    ): WriteResult {
        val clientWriteId = newClientWriteId("vitals")
        val payload = VitalsRequestDto(
            clientWriteId = clientWriteId,
            bpSystolic = bpSystolic,
            bpDiastolic = bpDiastolic,
            pr = pulse,
            spo2 = spo2,
            weightKg = weightKg,
            hemoglobin = hemoglobin,
        )
        return runCatching {
            val response = api.addVitals(caseId = caseId, request = payload)
            database.caseDao().upsertCase(response.case.toEntity())
            database.vitalDao().upsertVital(response.vital.toEntity(caseId))
            WriteResult(clientWriteId = clientWriteId, queued = false, message = response.message)
        }.getOrElse { throwable ->
            when {
                throwable.isConflict() -> {
                    recordConflict(
                        clientWriteId = clientWriteId,
                        writeType = PendingWriteTypes.VITALS_CREATE,
                        caseId = caseId,
                        taskId = null,
                        error = throwable,
                    )
                    WriteResult(
                        clientWriteId = clientWriteId,
                        queued = false,
                        conflict = true,
                        message = "Server version kept. Review the updated case.",
                    )
                }
                throwable.shouldQueue() -> {
                    queuePendingWrite(
                        clientWriteId = clientWriteId,
                        writeType = PendingWriteTypes.VITALS_CREATE,
                        caseId = caseId,
                        taskId = null,
                        payloadJson = PendingWriteJson.encodeVitals(payload),
                        lastError = throwable.message,
                    )
                    database.vitalDao().upsertVital(payload.toPendingVitalEntity(caseId, clientWriteId))
                    onPendingWriteQueued()
                    WriteResult(
                        clientWriteId = clientWriteId,
                        queued = true,
                        message = "Vitals queued for sync.",
                    )
                }
                else -> throw throwable
            }
        }
    }

    suspend fun dismissSyncConflict(clientWriteId: String) {
        database.syncConflictDao().deleteConflict(clientWriteId)
    }

    private suspend fun recordConflict(
        clientWriteId: String,
        writeType: String,
        caseId: String?,
        taskId: String?,
        error: Throwable,
    ) {
        database.syncConflictDao().upsertConflict(
            SyncConflictEntity(
                clientWriteId = clientWriteId,
                writeType = writeType,
                caseId = caseId,
                taskId = taskId,
                message = conflictMessage(error),
                serverPayloadJson = null,
                createdAtMillis = System.currentTimeMillis(),
            ),
        )
        caseId?.let { runCatching { refreshCaseDetail(it) } }
    }

    private suspend fun queuePendingWrite(
        clientWriteId: String,
        writeType: String,
        caseId: String?,
        taskId: String?,
        payloadJson: String,
        lastError: String?,
    ) {
        val now = System.currentTimeMillis()
        database.pendingWriteDao().upsertPendingWrite(
            PendingWriteEntity(
                clientWriteId = clientWriteId,
                writeType = writeType,
                caseId = caseId,
                taskId = taskId,
                payloadJson = payloadJson,
                retryCount = 0,
                lastError = lastError,
                createdAtMillis = now,
                updatedAtMillis = now,
            ),
        )
    }

    private suspend fun markCacheFresh(cacheKey: String) {
        database.cacheMetadataDao().upsertMetadata(
            CacheMetadataEntity(
                cacheKey = cacheKey,
                updatedAtMillis = System.currentTimeMillis(),
            ),
        )
    }
}

@OptIn(ExperimentalPagingApi::class)
private class CaseRemoteMediator(
    private val api: MedtrackApi,
    private val database: MedtrackDatabase,
    private val cacheKey: String,
    private val bucket: String?,
    private val query: String?,
    private val assignedTo: String?,
    private val scopeContext: String?,
    private val categories: List<String>,
    private val subcategories: List<String>,
    private val onStats: (InboxStats) -> Unit,
) : RemoteMediator<Int, CaseEntity>() {
    private var nextPage: Int? = 1

    override suspend fun load(loadType: LoadType, state: PagingState<Int, CaseEntity>): MediatorResult {
        val page = when (loadType) {
            LoadType.REFRESH -> 1
            LoadType.PREPEND -> return MediatorResult.Success(endOfPaginationReached = true)
            LoadType.APPEND -> nextPage ?: return MediatorResult.Success(endOfPaginationReached = true)
        }

        return runCatching {
            val response = api.listCases(
                bucket = bucket ?: "all",
                query = query?.takeIf { it.isNotBlank() },
                assignedTo = assignedTo,
                scopeContext = scopeContext,
                categories = categories.takeIf { it.isNotEmpty() },
                subcategories = subcategories.takeIf { it.isNotEmpty() },
                page = page,
            )
            val updatedAtMillis = System.currentTimeMillis()
            val upcomingPage = response.nextPageAfter(page)

            database.withTransaction {
                if (loadType == LoadType.REFRESH) {
                    database.caseDao().clearCases()
                }
                database.caseDao().upsertCases(response.results.map { it.toEntity() })
                database.caseStatsDao().upsertStats(response.stats.toEntity(cacheKey))
                database.cacheMetadataDao().upsertMetadata(
                    CacheMetadataEntity(
                        cacheKey = cacheKey,
                        updatedAtMillis = updatedAtMillis,
                    ),
                )
            }

            nextPage = upcomingPage
            onStats(response.stats.toDomain())
            MediatorResult.Success(endOfPaginationReached = upcomingPage == null)
        }.getOrElse { error ->
            MediatorResult.Error(error)
        }
    }
}

private fun newClientWriteId(prefix: String): String = "$prefix-${UUID.randomUUID()}"

private fun List<ChoiceDto>.toChoices(): List<FormChoice> = map { FormChoice(it.value, it.label) }

private fun CaseFormMetadataDto.toDomain(): CaseFormMetadata = CaseFormMetadata(
    canCreate = canCreate,
    categories = categories.map { category ->
        CaseFormCategory(
            id = category.id ?: 0L,
            name = category.name,
            subcategories = category.subcategories.mapNotNull { sub ->
                val value = sub.value ?: return@mapNotNull null
                FormChoice(value = value, label = sub.label ?: value)
            },
        )
    },
    prefixes = prefixes.toChoices(),
    bloodGroups = bloodGroups.toChoices(),
    genders = genders.toChoices(),
    ncdFlags = ncdFlags.toChoices(),
    ancHighRiskReasons = ancHighRiskReasons.toChoices(),
    surgicalPathways = surgicalPathways.toChoices(),
    reviewFrequencies = reviewFrequencies.toChoices(),
)

private fun PatientLookupDto.toDomain(): PatientLookup = PatientLookup(
    id = id,
    uhid = uhid,
    name = name.orEmpty(),
    prefix = prefix.orEmpty(),
    firstName = firstName.orEmpty(),
    lastName = lastName.orEmpty(),
    gender = gender.orEmpty(),
    genderLabel = genderLabel.orEmpty(),
    bloodGroup = bloodGroup.orEmpty(),
    dateOfBirth = dateOfBirth,
    age = age,
    place = place.orEmpty(),
    phoneNumber = phoneNumber.orEmpty(),
    alternatePhoneNumber = alternatePhoneNumber.orEmpty(),
    isTemporaryId = isTemporaryId,
    activeCaseCount = activeCaseCount,
)

private fun NewCaseInput.toRequestDto(clientWriteId: String): CreateCaseRequestDto = CreateCaseRequestDto(
    patientMode = patientMode,
    selectedPatient = selectedPatientId,
    useTemporaryUhid = useTemporaryUhid,
    uhid = uhid,
    prefix = prefix,
    firstName = firstName,
    lastName = lastName,
    gender = gender,
    bloodGroup = bloodGroup,
    dateOfBirth = dateOfBirth,
    place = place,
    age = age,
    phoneNumber = phoneNumber,
    alternatePhoneNumber = alternatePhoneNumber,
    category = categoryId,
    subcategory = subcategory,
    status = status,
    diagnosis = diagnosis,
    referredBy = referredBy,
    notes = notes,
    highRisk = highRisk,
    ncdFlags = ncdFlags,
    ancHighRiskReasons = ancHighRiskReasons,
    rchNumber = rchNumber,
    rchBypass = rchBypass,
    lmp = lmp,
    edd = edd,
    usgEdd = usgEdd,
    surgicalPathway = surgicalPathway,
    surgeryDate = surgeryDate,
    reviewFrequency = reviewFrequency,
    reviewDate = reviewDate,
    gravida = gravida,
    para = para,
    abortions = abortions,
    living = living,
    ftnd = ftnd,
    lscs = lscs,
    clientWriteId = clientWriteId,
)

private fun CaseEditFormDto.toDomain(): CaseEditPrefill {
    val metadata = CaseFormMetadata(
        canCreate = canEdit,
        categories = categories.map { category ->
            CaseFormCategory(
                id = category.id ?: 0L,
                name = category.name,
                subcategories = category.subcategories.mapNotNull { sub ->
                    val value = sub.value ?: return@mapNotNull null
                    FormChoice(value = value, label = sub.label ?: value)
                },
            )
        },
        prefixes = prefixes.toChoices(),
        bloodGroups = bloodGroups.toChoices(),
        genders = genders.toChoices(),
        ncdFlags = ncdFlags.toChoices(),
        ancHighRiskReasons = ancHighRiskReasons.toChoices(),
        surgicalPathways = surgicalPathways.toChoices(),
        reviewFrequencies = reviewFrequencies.toChoices(),
    )
    return CaseEditPrefill(
        canEdit = canEdit,
        metadata = metadata,
        patientMode = case.patientMode ?: "existing",
        selectedPatientId = case.selectedPatient,
        useTemporaryUhid = case.useTemporaryUhid,
        uhid = case.uhid,
        prefix = case.prefix,
        firstName = case.firstName,
        lastName = case.lastName,
        gender = case.gender,
        bloodGroup = case.bloodGroup,
        place = case.place,
        age = case.age,
        phoneNumber = case.phoneNumber,
        categoryId = case.category,
        subcategory = case.subcategory,
        status = case.status,
        diagnosis = case.diagnosis,
        referredBy = case.referredBy,
        notes = case.notes,
        highRisk = case.highRisk,
        ncdFlags = case.ncdFlags,
        ancHighRiskReasons = case.ancHighRiskReasons,
        rchNumber = case.rchNumber,
        rchBypass = case.rchBypass,
        lmp = case.lmp,
        edd = case.edd,
        usgEdd = case.usgEdd,
        surgicalPathway = case.surgicalPathway,
        surgeryDate = case.surgeryDate,
        reviewFrequency = case.reviewFrequency,
        reviewDate = case.reviewDate,
        gravida = case.gravida,
        para = case.para,
        abortions = case.abortions,
        living = case.living,
        ftnd = case.ftnd,
        lscs = case.lscs,
    )
}

private fun TaskFormMetadataDto.toDomain(): TaskFormMetadata = TaskFormMetadata(
    canCreate = canCreate,
    canEdit = canEdit,
    canReopen = canReopen,
    defaultStatus = defaultStatus,
    taskTypes = taskTypes.toChoices(),
    statuses = statuses.toChoices(),
    assignableUsers = assignableUsers.map { TaskAssignee(id = it.id, name = it.name) },
)

fun caseListCacheKey(
    bucket: String?,
    query: String?,
    assignedTo: String?,
    scopeContext: String?,
    categories: List<String>,
    subcategories: List<String>,
): String =
    "cases:" + listOf(
        bucket.orEmpty(),
        query.orEmpty().trim(),
        assignedTo.orEmpty(),
        scopeContext.orEmpty(),
        categories.sorted().joinToString(","),
        subcategories.sorted().joinToString(","),
    ).joinToString("|")

fun caseDetailCacheKey(caseId: String): String = "case_detail:$caseId"

fun isCacheFresh(updatedAtMillis: Long?, nowMillis: Long = System.currentTimeMillis()): Boolean =
    updatedAtMillis != null && nowMillis - updatedAtMillis < CACHE_TTL_MILLIS

private fun CaseListResponseDto.nextPageAfter(currentPage: Int): Int? =
    if (next.isNullOrBlank()) null else currentPage + 1

private fun Throwable.shouldQueue(): Boolean =
    this is IOException || (this is HttpException && code() in setOf(408, 429, 500, 502, 503, 504))

private fun Throwable.isConflict(): Boolean =
    this is HttpException && code() == 409

private fun conflictMessage(error: Throwable): String =
    if (error is HttpException) {
        error.response()?.errorBody()?.string()?.takeIf { it.isNotBlank() } ?: "The server version was kept."
    } else {
        "The server version was kept."
    }

private fun VitalsRequestDto.toPendingVitalEntity(caseId: String, clientWriteId: String): VitalEntity =
    VitalEntity(
        id = pendingVitalId(clientWriteId),
        caseId = caseId,
        recordedAt = currentUtcTimestamp(),
        bpSystolic = bpSystolic,
        bpDiastolic = bpDiastolic,
        pulse = pr,
        spo2 = spo2,
        weightKg = weightKg,
        hemoglobin = hemoglobin,
        summary = pendingVitalSummary(),
        updatedAtMillis = System.currentTimeMillis(),
    )

private fun VitalsRequestDto.pendingVitalSummary(): String {
    val parts = buildList {
        if (bpSystolic != null && bpDiastolic != null) add("BP $bpSystolic/$bpDiastolic")
        if (pr != null) add("PR $pr")
        if (spo2 != null) add("SpO2 $spo2")
        if (!hemoglobin.isNullOrBlank()) add("Hb $hemoglobin")
        if (!weightKg.isNullOrBlank()) add("Wt $weightKg kg")
    }
    return parts.joinToString(" | ").ifBlank { "Vitals pending sync" }
}

private fun currentUtcTimestamp(): String =
    SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss'Z'", Locale.US).apply {
        timeZone = TimeZone.getTimeZone("UTC")
    }.format(Date())

fun pendingVitalId(clientWriteId: String): String = "pending-$clientWriteId"

private fun CaseSummaryDto.toEntity(): CaseEntity =
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

private fun CaseEntity.toDomain(): PatientCase =
    PatientCase(
        id = id,
        uhid = uhid,
        patientName = patientName,
        age = age,
        sexLabel = sexLabel,
        place = place,
        phoneNumber = phoneNumber,
        category = category.toCategory(),
        categoryLabel = category.ifBlank { category.toCategory().label },
        subcategoryValue = subcategoryValue,
        subcategoryLabel = subcategoryLabel,
        status = status.toStatus(),
        diagnosis = diagnosis,
        nextTaskId = nextTaskId,
        nextTaskTitle = nextTaskTitle,
        nextTaskDueDate = nextTaskDueDate,
        latestVitalSummary = latestVitalSummary,
        isHighRisk = isHighRisk,
        highRiskReasons = highRiskReasons.lines().filter { it.isNotBlank() },
    )

private fun TaskDto.toEntity(caseId: String): TaskEntity =
    TaskEntity(
        id = id.toString(),
        caseId = caseId,
        title = title,
        dueDate = dueDate,
        status = status,
        statusLabel = statusLabel?.takeIf { it.isNotBlank() } ?: status,
        canComplete = canComplete ?: status.uppercase() !in setOf("COMPLETED", "CANCELLED"),
        taskType = taskType,
        taskTypeLabel = taskTypeLabel,
        assignedUserId = assignedUserId,
        assignedUser = assignedUser?.takeIf { it.isNotBlank() },
        notes = notes?.takeIf { it.isNotBlank() },
        updatedAtMillis = System.currentTimeMillis(),
    )

private fun TaskEntity.toDomain(): PatientTask =
    PatientTask(
        id = id,
        caseId = caseId,
        title = title,
        dueDate = dueDate,
        status = status,
        statusLabel = statusLabel,
        canComplete = canComplete,
        taskType = taskType,
        taskTypeLabel = taskTypeLabel,
        assignedUserId = assignedUserId,
        assignedUser = assignedUser,
        notes = notes,
    )

private fun VitalDto.toEntity(caseId: String): VitalEntity =
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

private fun VitalEntity.toDomain(): PatientVital =
    PatientVital(
        id = id,
        caseId = caseId,
        recordedAt = recordedAt,
        bpSystolic = bpSystolic,
        bpDiastolic = bpDiastolic,
        pulse = pulse,
        spo2 = spo2,
        weightKg = weightKg,
        hemoglobin = hemoglobin,
        summary = summary,
    )

private fun CaseStatsDto.toDomain(): InboxStats =
    InboxStats(
        today = today,
        upcoming = upcoming,
        overdue = overdue,
        awaiting = awaiting,
        red = red,
    )

private fun CaseStatsDto.toEntity(cacheKey: String): CaseStatsEntity =
    CaseStatsEntity(
        cacheKey = cacheKey,
        today = today,
        upcoming = upcoming,
        overdue = overdue,
        awaiting = awaiting,
        red = red,
        updatedAtMillis = System.currentTimeMillis(),
    )

private fun CaseStatsEntity.toDomain(): InboxStats =
    InboxStats(
        today = today,
        upcoming = upcoming,
        overdue = overdue,
        awaiting = awaiting,
        red = red,
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

private fun NotificationDto.toEntity(): NotificationEntity =
    NotificationEntity(
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

private fun NotificationEntity.toDomain(): NotificationItem =
    NotificationItem(
        id = id,
        type = type,
        title = title,
        body = body,
        caseId = caseId,
        taskId = taskId,
        createdAt = createdAt,
        isRead = isRead,
        payload = parseNotificationPayload(type = type, payloadJson = payloadJson),
    )

private fun SyncConflictEntity.toDomain(): SyncConflict =
    SyncConflict(
        clientWriteId = clientWriteId,
        writeType = writeType,
        caseId = caseId,
        taskId = taskId,
        message = message,
        createdAtMillis = createdAtMillis,
    )

private val vitalsThresholdsJsonAdapter = Moshi.Builder()
    .add(KotlinJsonAdapterFactory())
    .build()
    .adapter(VitalsThresholdsDto::class.java)

private val categoryOptionsJsonAdapter = Moshi.Builder()
    .add(KotlinJsonAdapterFactory())
    .build()
    .adapter(CategoriesResponseDto::class.java)

private fun CategoriesResponseDto.toEntity(): CategoryOptionsEntity =
    CategoryOptionsEntity(
        id = "current",
        payloadJson = categoryOptionsJsonAdapter.toJson(this),
        updatedAtMillis = System.currentTimeMillis(),
    )

private fun CategoryOptionsEntity.toDomain(): List<CategoryFilterOption> =
    categoryOptionsJsonAdapter.fromJson(payloadJson)
        ?.categories
        ?.map { it.toFilterOption() }
        .orEmpty()

private fun VitalsThresholdsDto.toEntity(): VitalsThresholdEntity =
    VitalsThresholdEntity(
        id = "current",
        payloadJson = vitalsThresholdsJsonAdapter.toJson(this),
        updatedAtMillis = System.currentTimeMillis(),
    )

private fun VitalsThresholdEntity.toDomain(): VitalsThresholdConfig? =
    vitalsThresholdsJsonAdapter.fromJson(payloadJson)?.toDomain()

private fun VitalsThresholdsDto.toDomain(): VitalsThresholdConfig =
    VitalsThresholdConfig(
        version = version,
        metrics = metrics,
        statusLabels = statusLabels,
    )

private fun CaseCategoryDto.toFilterOption(): CategoryFilterOption =
    CategoryFilterOption(
        value = id?.toString() ?: name,
        label = name,
        category = name.toCategory(),
        iconPath = iconPath,
        subcategories = subcategories.mapNotNull { it.toFilterOption() },
    )

private fun CaseSubcategoryDto.toFilterOption(): SubcategoryFilterOption? {
    val value = value?.takeIf { it.isNotBlank() } ?: return null
    val label = label?.takeIf { it.isNotBlank() } ?: value
    return SubcategoryFilterOption(
        value = value,
        label = label,
        iconPath = iconPath,
    )
}

private fun String.toCategory(): CaseCategory =
    when (uppercase()) {
        "ANC" -> CaseCategory.ANC
        "SURGERY" -> CaseCategory.SURGERY
        "MEDICINE", "NON_SURGICAL", "NON-SURGICAL" -> CaseCategory.MEDICINE
        else -> CaseCategory.OTHER
    }

private fun String.toStatus(): CaseStatus =
    when (uppercase()) {
        "ACTIVE" -> CaseStatus.ACTIVE
        "COMPLETED" -> CaseStatus.COMPLETED
        "CANCELLED" -> CaseStatus.CANCELLED
        "LOSS_TO_FOLLOW_UP", "LOSS TO FOLLOW-UP" -> CaseStatus.LOSS_TO_FOLLOW_UP
        else -> CaseStatus.ACTIVE
    }
