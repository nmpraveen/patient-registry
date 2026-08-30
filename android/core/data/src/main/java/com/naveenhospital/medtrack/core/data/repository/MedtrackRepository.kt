package com.naveenhospital.medtrack.core.data.repository

import androidx.paging.ExperimentalPagingApi
import androidx.paging.LoadType
import androidx.paging.Pager
import androidx.paging.PagingConfig
import androidx.paging.PagingData
import androidx.paging.PagingState
import androidx.paging.RemoteMediator
import androidx.paging.map
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
import com.naveenhospital.medtrack.core.data.sync.SyncFailureKinds
import com.naveenhospital.medtrack.core.data.sync.SyncRecoveryJson
import com.naveenhospital.medtrack.core.data.sync.SyncRecoveryPayload
import com.naveenhospital.medtrack.core.data.sync.SyncResolutionStates
import com.naveenhospital.medtrack.core.data.sync.fetchAllNotifications
import com.naveenhospital.medtrack.core.data.sync.replaceNotificationSnapshot
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
import com.naveenhospital.medtrack.core.network.model.CaseEditCaseDto
import com.naveenhospital.medtrack.core.network.model.CreateTaskRequestDto
import com.naveenhospital.medtrack.core.network.model.TaskFormMetadataDto
import com.naveenhospital.medtrack.core.network.model.TaskNoteRequestDto
import com.naveenhospital.medtrack.core.network.model.UpdateTaskRequestDto
import com.naveenhospital.medtrack.core.network.model.UpdateCaseRequestDto
import com.naveenhospital.medtrack.core.network.model.VitalsUpdateRequestDto
import com.naveenhospital.medtrack.core.network.model.PatientLookupDto
import com.naveenhospital.medtrack.core.network.model.PatientSearchRequestDto
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
import java.util.concurrent.ConcurrentHashMap
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.flatMapLatest
import kotlinx.coroutines.flow.flowOf
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.ExperimentalCoroutinesApi
import retrofit2.HttpException

const val CACHE_TTL_MILLIS: Long = 60 * 60 * 1000L
const val CACHE_KEY_CATEGORY_OPTIONS = "category_options"
const val CACHE_KEY_VITALS_THRESHOLDS = "vitals_thresholds"
const val CACHE_KEY_NOTIFICATIONS = "notifications"
const val CACHE_KEY_NOTIFICATION_DATASET_EPOCH_PREFIX = "notification_dataset_epoch:"
private const val CASE_PAGE_SIZE = 20

@OptIn(ExperimentalCoroutinesApi::class)
class MedtrackRepository(
    private val apiForAccount: (String) -> MedtrackApi,
    private val database: MedtrackDatabase,
    private val onPendingWriteQueued: (String) -> Unit = {},
    private val beforeLocalCommit: suspend (String) -> Unit = {},
) {
    constructor(
        api: MedtrackApi,
        database: MedtrackDatabase,
        onPendingWriteQueued: (String) -> Unit = {},
    ) : this(
        apiForAccount = { api },
        database = database,
        onPendingWriteQueued = onPendingWriteQueued,
    )

    private data class AccountSession(
        val ownerAccountId: String,
        val generation: Long,
        val api: MedtrackApi,
    )

    private val activeAccountId = MutableStateFlow<String?>(null)
    @Volatile
    private var activeGeneration: Long? = null
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
    private val caseEditBaselines = ConcurrentHashMap<String, CaseEditCaseDto>()
    private val caseCreateErrorAdapter =
        Moshi.Builder().add(KotlinJsonAdapterFactory()).build().adapter(CaseCreateErrorDto::class.java)

    val cases: Flow<List<PatientCase>> =
        activeAccountId.flatMapLatest { ownerAccountId ->
            if (ownerAccountId == null) flowOf(emptyList())
            else database.caseDao().observeCases(ownerAccountId).map { entities -> entities.map { it.toDomain() } }
        }

    suspend fun activateAccount(accountId: String) {
        require(accountId.isNotBlank()) { "A verified account ID is required." }
        val generation = database.activateAccount(accountId)
        resetInMemoryState()
        activeGeneration = generation
        activeAccountId.value = accountId
    }

    fun deactivateAccount() {
        activeAccountId.value = null
        activeGeneration = null
        resetInMemoryState()
    }

    fun activeAccountId(): String? = activeAccountId.value

    suspend fun wipeAccountData(accountId: String) {
        database.invalidateAndClearAccountData(accountId)
        if (activeAccountId.value == accountId) resetInMemoryState()
    }

    private fun resetInMemoryState() {
        _stats.value = InboxStats()
        _categoryOptions.value = emptyList()
        _vitalsThresholds.value = null
        _hasMoreCases.value = false
        nextCasePage = null
        activeCaseListKey = ""
        caseEditBaselines.clear()
    }

    private fun activeSession(): AccountSession {
        val ownerAccountId = activeAccountId.value ?: error("No verified MEDTRACK account is active.")
        val generation = activeGeneration ?: error("No verified MEDTRACK account generation is active.")
        return AccountSession(ownerAccountId, generation, apiForAccount(ownerAccountId))
    }

    private fun requireStillActive(session: AccountSession) {
        check(
            activeAccountId.value == session.ownerAccountId && activeGeneration == session.generation,
        ) { "The authenticated MEDTRACK account changed." }
    }

    private suspend fun <T> commitAccountMutation(
        session: AccountSession,
        block: suspend () -> T,
    ): T {
        beforeLocalCommit(session.ownerAccountId)
        return database.commitForAccount(
            ownerAccountId = session.ownerAccountId,
            generation = session.generation,
            isLocallyActive = {
                activeAccountId.value == session.ownerAccountId && activeGeneration == session.generation
            },
            block = block,
        )
    }

    @OptIn(ExperimentalPagingApi::class)
    fun pagedCases(
        bucket: String? = "today",
        query: String? = null,
        assignedTo: String? = null,
        scopeContext: String? = null,
        categories: List<String> = emptyList(),
        subcategories: List<String> = emptyList(),
    ): Flow<PagingData<PatientCase>> {
        val session = activeSession()
        val cacheKey = caseListCacheKey(bucket, query, assignedTo, scopeContext, categories, subcategories)
        activeCaseListKey = cacheKey
        return Pager(
            config = PagingConfig(
                pageSize = CASE_PAGE_SIZE,
                prefetchDistance = 6,
                enablePlaceholders = false,
            ),
            remoteMediator = CaseRemoteMediator(
                ownerAccountId = session.ownerAccountId,
                accountGeneration = session.generation,
                api = session.api,
                database = database,
                cacheKey = cacheKey,
                bucket = bucket,
                query = query,
                assignedTo = assignedTo,
                scopeContext = scopeContext,
                categories = categories,
                subcategories = subcategories,
                onStats = { stats -> _stats.value = stats },
                isAccountActive = { activeAccountId.value == session.ownerAccountId },
            ),
            pagingSourceFactory = { database.caseDao().pagingSource(session.ownerAccountId) },
        ).flow.map { pagingData -> pagingData.map { entity -> entity.toDomain() } }
    }

    val notifications: Flow<List<NotificationItem>> =
        activeAccountId.flatMapLatest { ownerAccountId ->
            if (ownerAccountId == null) flowOf(emptyList())
            else database.notificationDao().observeNotifications(ownerAccountId)
                .map { entities -> entities.map { it.toDomain() } }
        }

    val pendingWriteCount: Flow<Int> =
        activeAccountId.flatMapLatest { ownerAccountId ->
            if (ownerAccountId == null) flowOf(0)
            else database.pendingWriteDao().observePendingWriteCount(ownerAccountId)
        }

    val syncConflicts: Flow<List<SyncConflict>> =
        activeAccountId.flatMapLatest { ownerAccountId ->
            if (ownerAccountId == null) flowOf(emptyList())
            else database.syncConflictDao().observeConflicts(ownerAccountId)
                .map { entities ->
                    entities.map { it.toDomain() }
                        .filter { it.resolutionState == SyncResolutionStates.OPEN }
                }
        }

    val syncConflictCount: Flow<Int> = syncConflicts.map { it.size }

    fun observeCase(caseId: String): Flow<PatientCase?> =
        activeAccountId.flatMapLatest { ownerAccountId ->
            if (ownerAccountId == null) flowOf(null)
            else database.caseDao().observeCase(ownerAccountId, caseId).map { it?.toDomain() }
        }

    fun observeTasks(caseId: String): Flow<List<PatientTask>> =
        activeAccountId.flatMapLatest { ownerAccountId ->
            if (ownerAccountId == null) flowOf(emptyList())
            else database.taskDao().observeTasksForCase(ownerAccountId, caseId)
                .map { entities -> entities.map { it.toDomain() } }
        }

    fun observeVitals(caseId: String): Flow<List<PatientVital>> =
        activeAccountId.flatMapLatest { ownerAccountId ->
            if (ownerAccountId == null) flowOf(emptyList())
            else database.vitalDao().observeVitalsForCase(ownerAccountId, caseId)
                .map { entities -> entities.map { it.toDomain() } }
        }

    suspend fun refreshCases(
        bucket: String? = "today",
        query: String? = null,
        assignedTo: String? = null,
        scopeContext: String? = null,
        categories: List<String> = emptyList(),
        subcategories: List<String> = emptyList(),
    ) {
        val session = activeSession()
        activeCaseListKey = caseListCacheKey(bucket, query, assignedTo, scopeContext, categories, subcategories)
        database.caseStatsDao().statsForKey(session.ownerAccountId, activeCaseListKey)?.let { cachedStats ->
            _stats.value = cachedStats.toDomain()
        }
        val response = session.api.listCases(
            bucket = bucket ?: "all",
            query = query?.takeIf { it.isNotBlank() },
            assignedTo = assignedTo,
            scopeContext = scopeContext,
            categories = categories.takeIf { it.isNotEmpty() },
            subcategories = subcategories.takeIf { it.isNotEmpty() },
            page = 1,
        )
        commitAccountMutation(session) {
            database.caseDao().clearCases(session.ownerAccountId)
            database.caseDao().upsertCases(response.results.map { it.toEntity(session.ownerAccountId) })
            database.caseStatsDao().upsertStats(response.stats.toEntity(session.ownerAccountId, activeCaseListKey))
            markCacheFresh(session.ownerAccountId, caseListCacheKey(bucket, query, assignedTo, scopeContext, categories, subcategories))
        }
        requireStillActive(session)
        _stats.value = response.stats.toDomain()
        nextCasePage = response.nextPageAfter(1)
        _hasMoreCases.value = nextCasePage != null
    }

    suspend fun loadNextCases(
        bucket: String? = "today",
        query: String? = null,
        assignedTo: String? = null,
        scopeContext: String? = null,
        categories: List<String> = emptyList(),
        subcategories: List<String> = emptyList(),
    ) {
        val session = activeSession()
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
        val response = session.api.listCases(
            bucket = bucket ?: "all",
            query = query?.takeIf { it.isNotBlank() },
            assignedTo = assignedTo,
            scopeContext = scopeContext,
            categories = categories.takeIf { it.isNotEmpty() },
            subcategories = subcategories.takeIf { it.isNotEmpty() },
            page = page,
        )
        commitAccountMutation(session) {
            database.caseDao().upsertCases(response.results.map { it.toEntity(session.ownerAccountId) })
            database.caseStatsDao().upsertStats(response.stats.toEntity(session.ownerAccountId, requestedKey))
        }
        requireStillActive(session)
        _stats.value = response.stats.toDomain()
        nextCasePage = response.nextPageAfter(page)
        _hasMoreCases.value = nextCasePage != null
    }

    suspend fun loadCaseFormMetadata(): CaseFormMetadata {
        val session = activeSession()
        val response = session.api.caseFormMetadata()
        requireStillActive(session)
        return response.toDomain()
    }

    suspend fun searchPatients(query: String): List<PatientLookup> {
        val session = activeSession()
        val normalizedQuery = query.trim()
        require(normalizedQuery.length in 3..80) { "Patient search requires 3 to 80 characters." }
        val response = session.api.searchPatients(PatientSearchRequestDto(query = normalizedQuery))
        requireStillActive(session)
        return response.results.map { it.toDomain() }
    }

    suspend fun createCase(input: NewCaseInput): CaseCreateOutcome {
        val session = activeSession()
        val request = input.toRequestDto(newClientWriteId("case"))
        return runCatching {
            val response = session.api.createCase(request)
            commitAccountMutation(session) {
                database.caseDao().upsertCase(response.case.toEntity(session.ownerAccountId))
            }
            CaseCreateOutcome.Success(caseId = response.caseId, message = response.message)
        }.getOrElse { throwable ->
            requireStillActive(session)
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

    suspend fun loadCaseEditForm(caseId: String): CaseEditPrefill {
        val session = activeSession()
        val response = session.api.caseEditForm(caseId)
        requireStillActive(session)
        caseEditBaselines[caseId] = response.case
        return response.toDomain()
    }

    suspend fun updateCase(caseId: String, input: NewCaseInput): CaseEditOutcome {
        val session = activeSession()
        val baseline = caseEditBaselines[caseId]
            ?: return CaseEditOutcome.Failure(
                "Case edit must be reloaded before saving. No changes were sent.",
            )
        if (input.categoryName.equals("Surgery", ignoreCase = true) && input.surgeryDone == null) {
            return CaseEditOutcome.Failure(
                "Case edit is temporarily unavailable because the server did not return the existing surgery completion value. No changes were sent.",
            )
        }
        val request = input.toUpdateRequestDto(
            clientWriteId = newClientWriteId("case-edit"),
            baseline = baseline,
        )
        return runCatching {
            val response = session.api.updateCase(caseId, request)
            commitAccountMutation(session) {
                database.caseDao().upsertCase(response.case.toEntity(session.ownerAccountId))
                caseEditBaselines.remove(caseId)
            }
            CaseEditOutcome.Success(caseId = response.caseId, message = response.message)
        }.getOrElse { throwable ->
            requireStillActive(session)
            parseFormErrors(throwable)?.let {
                CaseEditOutcome.ValidationError(errors = it.errors, message = it.message ?: "Please fix the highlighted fields.")
            } ?: CaseEditOutcome.Failure(throwable.message ?: "Could not save the case. Try again.")
        }
    }

    suspend fun loadTaskFormMetadata(): TaskFormMetadata {
        val session = activeSession()
        val response = session.api.taskFormMetadata()
        requireStillActive(session)
        return response.toDomain()
    }

    suspend fun createTask(caseId: String, input: NewTaskInput): TaskWriteOutcome {
        val session = activeSession()
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
            val response = session.api.createTask(caseId, request)
            commitAccountMutation(session) {
                database.caseDao().upsertCase(response.case.toEntity(session.ownerAccountId))
                database.taskDao().upsertTask(response.task.toEntity(session.ownerAccountId, caseId))
            }
            TaskWriteOutcome.Success(response.message)
        }.getOrElse { throwable ->
            requireStillActive(session)
            throwable.toTaskOutcome()
        }
    }

    suspend fun updateTask(taskId: String, caseId: String, input: TaskEditInput): TaskWriteOutcome {
        val session = activeSession()
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
            val response = session.api.updateTask(taskId, request)
            commitAccountMutation(session) {
                database.caseDao().upsertCase(response.case.toEntity(session.ownerAccountId))
                database.taskDao().upsertTask(response.task.toEntity(session.ownerAccountId, caseId))
            }
            TaskWriteOutcome.Success(response.message)
        }.getOrElse { throwable ->
            requireStillActive(session)
            throwable.toTaskOutcome()
        }
    }

    suspend fun addTaskNote(taskId: String, caseId: String, note: String): TaskWriteOutcome {
        val session = activeSession()
        return runCatching {
            val response = session.api.addTaskNote(taskId, TaskNoteRequestDto(note = note))
            commitAccountMutation(session) {
                database.caseDao().upsertCase(response.case.toEntity(session.ownerAccountId))
                database.taskDao().upsertTask(response.task.toEntity(session.ownerAccountId, caseId))
            }
            TaskWriteOutcome.Success(response.message)
        }.getOrElse { throwable ->
            requireStillActive(session)
            throwable.toTaskOutcome()
        }
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
        val session = activeSession()
        val request = VitalsUpdateRequestDto(
            bpSystolic = bpSystolic,
            bpDiastolic = bpDiastolic,
            pr = pulse,
            spo2 = spo2,
            weightKg = weightKg,
            hemoglobin = hemoglobin,
        )
        return runCatching {
            val response = session.api.updateVitals(vitalId, request)
            commitAccountMutation(session) {
                database.caseDao().upsertCase(response.case.toEntity(session.ownerAccountId))
                database.vitalDao().upsertVital(response.vital.toEntity(session.ownerAccountId, caseId))
            }
            VitalsWriteOutcome.Success(response.message)
        }.getOrElse { throwable ->
            requireStillActive(session)
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
        val ownerAccountId = activeSession().ownerAccountId
        val cached = database.categoryOptionsDao().currentOptions(ownerAccountId) ?: return
        _categoryOptions.value = cached.toDomain()
    }

    suspend fun refreshCategoryOptions() {
        val session = activeSession()
        val response = session.api.categories()
        commitAccountMutation(session) {
            database.categoryOptionsDao().upsertOptions(response.toEntity(session.ownerAccountId))
            markCacheFresh(session.ownerAccountId, CACHE_KEY_CATEGORY_OPTIONS)
        }
        requireStillActive(session)
        _categoryOptions.value = response.categories.map { it.toFilterOption() }
    }

    suspend fun loadCachedVitalsThresholds() {
        val ownerAccountId = activeSession().ownerAccountId
        val cached = database.vitalsThresholdDao().currentThresholds(ownerAccountId) ?: return
        _vitalsThresholds.value = cached.toDomain()
    }

    suspend fun refreshVitalsThresholds() {
        val session = activeSession()
        val response = session.api.vitalsThresholds()
        commitAccountMutation(session) {
            database.vitalsThresholdDao().upsertThresholds(response.toEntity(session.ownerAccountId))
            markCacheFresh(session.ownerAccountId, CACHE_KEY_VITALS_THRESHOLDS)
        }
        requireStillActive(session)
        _vitalsThresholds.value = response.toDomain()
    }

    suspend fun refreshCaseDetail(caseId: String) {
        refreshCaseDetailForSession(activeSession(), caseId)
    }

    private suspend fun refreshCaseDetailForSession(session: AccountSession, caseId: String) {
        val response = session.api.caseDetail(caseId)
        commitAccountMutation(session) {
            database.caseDao().upsertCase(response.case.toEntity(session.ownerAccountId))
            database.taskDao().clearTasksForCase(session.ownerAccountId, caseId)
            database.taskDao().upsertTasks(response.tasks.map { it.toEntity(session.ownerAccountId, caseId) })
            database.vitalDao().clearVitalsForCase(session.ownerAccountId, caseId)
            database.vitalDao().upsertVitals(response.vitals.map { it.toEntity(session.ownerAccountId, caseId) })
            markCacheFresh(session.ownerAccountId, caseDetailCacheKey(caseId))
        }
    }

    suspend fun refreshNotifications(type: String? = null) {
        val session = activeSession()
        // When a Me-page category is open, fetch that type server-side so paginated
        // matches beyond the untyped first page aren't missed by client-side filtering.
        val snapshot = fetchAllNotifications(api = session.api, type = type)
        commitAccountMutation(session) {
            replaceNotificationSnapshot(
                database = database,
                ownerAccountId = session.ownerAccountId,
                type = type,
                snapshot = com.naveenhospital.medtrack.core.data.sync.NotificationSnapshot(
                    datasetEpoch = snapshot.datasetEpoch,
                    notifications = snapshot.notifications.map { it.toEntity(session.ownerAccountId) },
                ),
            )
            // Only a full (untyped) refresh covers every category, so only it may mark the
            // shared cache fresh. A typed refresh must not suppress the global sync, or the
            // Me badge/counts could miss other categories until "All" is opened.
            if (type == null) {
                markCacheFresh(session.ownerAccountId, CACHE_KEY_NOTIFICATIONS)
            }
        }
    }

    suspend fun markNotificationRead(notificationId: String) {
        val session = activeSession()
        val clientWriteId = newClientWriteId("notification")
        val payload = NotificationReadPayload(
            notificationId = notificationId,
            clientWriteId = clientWriteId,
        )
        commitAccountMutation(session) {
            database.notificationDao().markRead(session.ownerAccountId, notificationId)
        }
        runCatching {
            session.api.markNotificationRead(notificationId)
        }.getOrElse { throwable ->
            requireStillActive(session)
            if (!throwable.shouldQueue()) {
                throw throwable
            }
            commitAccountMutation(session) {
                queuePendingWrite(
                    ownerAccountId = session.ownerAccountId,
                    clientWriteId = clientWriteId,
                    writeType = PendingWriteTypes.NOTIFICATION_READ,
                    caseId = null,
                    taskId = notificationId,
                    payloadJson = PendingWriteJson.encodeNotificationRead(payload),
                    lastError = throwable.message,
                )
            }
            onPendingWriteQueued(session.ownerAccountId)
        }
    }

    suspend fun registerPushToken(token: String, deviceLabel: String) {
        val session = activeSession()
        commitAccountMutation(session) {
            database.pushTokenDao().upsertToken(
                PushTokenEntity(
                    ownerAccountId = session.ownerAccountId,
                    token = token,
                    deviceLabel = deviceLabel,
                    syncedAtMillis = 0L,
                ),
            )
        }
        session.api.registerPushToken(RegisterPushTokenRequestDto(token = token, deviceLabel = deviceLabel))
        commitAccountMutation(session) {
            database.pushTokenDao().markTokenSynced(session.ownerAccountId, token, System.currentTimeMillis())
        }
    }

    suspend fun currentPushTokenForLogout(): String? {
        val ownerAccountId = activeSession().ownerAccountId
        val dao = database.pushTokenDao()
        return (dao.latestSyncedToken(ownerAccountId) ?: dao.latestToken(ownerAccountId))
            ?.token
            ?.takeIf { it.isNotBlank() }
    }

    suspend fun completeTask(taskId: String, caseId: String): WriteResult {
        val session = activeSession()
        val clientWriteId = newClientWriteId("task")
        val payload = ClientWriteRequestDto(clientWriteId = clientWriteId)
        return runCatching {
            val response = session.api.completeTask(taskId = taskId, request = payload)
            commitAccountMutation(session) {
                database.caseDao().upsertCase(response.case.toEntity(session.ownerAccountId))
                database.taskDao().upsertTask(response.task.toEntity(session.ownerAccountId, caseId))
            }
            WriteResult(clientWriteId = clientWriteId, queued = false, message = response.message)
        }.getOrElse { throwable ->
            requireStillActive(session)
            when {
                throwable.isConflict() -> {
                    recordConflict(
                        session = session,
                        clientWriteId = clientWriteId,
                        writeType = PendingWriteTypes.TASK_COMPLETE,
                        caseId = caseId,
                        taskId = taskId,
                        payloadJson = PendingWriteJson.encodeTaskComplete(payload),
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
                    commitAccountMutation(session) {
                        queuePendingWrite(
                            ownerAccountId = session.ownerAccountId,
                            clientWriteId = clientWriteId,
                            writeType = PendingWriteTypes.TASK_COMPLETE,
                            caseId = caseId,
                            taskId = taskId,
                            payloadJson = PendingWriteJson.encodeTaskComplete(payload),
                            lastError = throwable.message,
                        )
                        database.taskDao().markTaskCompletedLocally(session.ownerAccountId, taskId, System.currentTimeMillis())
                    }
                    onPendingWriteQueued(session.ownerAccountId)
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
        val session = activeSession()
        val clientWriteId = newClientWriteId("call")
        val payload = LogCallRequestDto(
            outcome = outcome,
            note = note,
            taskId = taskId?.toLongOrNull(),
            attemptedAt = attemptedAt?.takeIf { it.isNotBlank() } ?: currentUtcTimestamp(),
            clientWriteId = clientWriteId,
        )
        return runCatching {
            val response = session.api.logCall(caseId = caseId, request = payload)
            commitAccountMutation(session) {
                database.caseDao().upsertCase(response.case.toEntity(session.ownerAccountId))
            }
            WriteResult(clientWriteId = clientWriteId, queued = false, message = response.message)
        }.getOrElse { throwable ->
            requireStillActive(session)
            when {
                throwable.isConflict() -> {
                    recordConflict(
                        session = session,
                        clientWriteId = clientWriteId,
                        writeType = PendingWriteTypes.CALL_OUTCOME,
                        caseId = caseId,
                        taskId = taskId,
                        payloadJson = PendingWriteJson.encodeCallOutcome(payload),
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
                    commitAccountMutation(session) {
                        queuePendingWrite(
                            ownerAccountId = session.ownerAccountId,
                            clientWriteId = clientWriteId,
                            writeType = PendingWriteTypes.CALL_OUTCOME,
                            caseId = caseId,
                            taskId = taskId,
                            payloadJson = PendingWriteJson.encodeCallOutcome(payload),
                            lastError = throwable.message,
                        )
                    }
                    onPendingWriteQueued(session.ownerAccountId)
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
        val session = activeSession()
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
            val response = session.api.addVitals(caseId = caseId, request = payload)
            commitAccountMutation(session) {
                database.caseDao().upsertCase(response.case.toEntity(session.ownerAccountId))
                database.vitalDao().upsertVital(response.vital.toEntity(session.ownerAccountId, caseId))
            }
            WriteResult(clientWriteId = clientWriteId, queued = false, message = response.message)
        }.getOrElse { throwable ->
            requireStillActive(session)
            when {
                throwable.isConflict() -> {
                    recordConflict(
                        session = session,
                        clientWriteId = clientWriteId,
                        writeType = PendingWriteTypes.VITALS_CREATE,
                        caseId = caseId,
                        taskId = null,
                        payloadJson = PendingWriteJson.encodeVitals(payload),
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
                    commitAccountMutation(session) {
                        queuePendingWrite(
                            ownerAccountId = session.ownerAccountId,
                            clientWriteId = clientWriteId,
                            writeType = PendingWriteTypes.VITALS_CREATE,
                            caseId = caseId,
                            taskId = null,
                            payloadJson = PendingWriteJson.encodeVitals(payload),
                            lastError = throwable.message,
                        )
                        database.vitalDao().upsertVital(
                            payload.toPendingVitalEntity(session.ownerAccountId, caseId, clientWriteId),
                        )
                    }
                    onPendingWriteQueued(session.ownerAccountId)
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

    suspend fun retrySyncConflict(clientWriteId: String) {
        val session = activeSession()
        val conflict = database.syncConflictDao()
            .conflictById(session.ownerAccountId, clientWriteId) ?: return
        val recovery = SyncRecoveryJson.decode(conflict.serverPayloadJson)
            ?: error("This sync issue predates durable recovery and cannot be retried.")
        val localPayload = recovery.localPayloadJson
            ?.takeIf { it.isNotBlank() }
            ?: error("The original change is unavailable and cannot be retried.")
        val now = System.currentTimeMillis()
        commitAccountMutation(session) {
            database.pendingWriteDao().upsertPendingWrite(
                PendingWriteEntity(
                    ownerAccountId = session.ownerAccountId,
                    clientWriteId = conflict.clientWriteId,
                    writeType = conflict.writeType,
                    caseId = conflict.caseId,
                    taskId = conflict.taskId,
                    payloadJson = localPayload,
                    retryCount = 0,
                    lastError = conflict.message,
                    createdAtMillis = conflict.createdAtMillis,
                    updatedAtMillis = now,
                ),
            )
            database.syncConflictDao().upsertConflict(
                conflict.copy(
                    serverPayloadJson = SyncRecoveryJson.encode(
                        recovery.copy(
                            resolutionState = SyncResolutionStates.RETRY_QUEUED,
                            resolutionAtMillis = now,
                        ),
                    ),
                ),
            )
        }
        onPendingWriteQueued(session.ownerAccountId)
    }

    suspend fun discardSyncConflict(clientWriteId: String) {
        val session = activeSession()
        val conflict = database.syncConflictDao()
            .conflictById(session.ownerAccountId, clientWriteId) ?: return
        val recovery = SyncRecoveryJson.decode(conflict.serverPayloadJson)
            ?: SyncRecoveryPayload(failureKind = SyncFailureKinds.CONFLICT)
        val now = System.currentTimeMillis()
        commitAccountMutation(session) {
            database.pendingWriteDao().deletePendingWrite(session.ownerAccountId, clientWriteId)
            if (conflict.writeType == PendingWriteTypes.VITALS_CREATE) {
                database.vitalDao().deleteVital(session.ownerAccountId, pendingVitalId(clientWriteId))
            }
            database.syncConflictDao().upsertConflict(
                conflict.copy(
                    serverPayloadJson = SyncRecoveryJson.encode(
                        recovery.copy(
                            resolutionState = SyncResolutionStates.DISCARDED,
                            resolutionAtMillis = now,
                        ),
                    ),
                ),
            )
        }
        conflict.caseId?.let { runCatching { refreshCaseDetailForSession(session, it) } }
    }

    private suspend fun recordConflict(
        session: AccountSession,
        clientWriteId: String,
        writeType: String,
        caseId: String?,
        taskId: String?,
        payloadJson: String,
        error: Throwable,
    ) {
        val serverPayload = error.httpErrorBody()
        val now = System.currentTimeMillis()
        commitAccountMutation(session) {
            database.syncConflictDao().upsertConflict(
                SyncConflictEntity(
                    ownerAccountId = session.ownerAccountId,
                    clientWriteId = clientWriteId,
                    writeType = writeType,
                    caseId = caseId,
                    taskId = taskId,
                    message = serverPayload ?: "The server version was kept.",
                    serverPayloadJson = SyncRecoveryJson.encode(
                        SyncRecoveryPayload(
                            failureKind = SyncFailureKinds.CONFLICT,
                            localPayloadJson = payloadJson,
                            serverPayloadJson = serverPayload,
                            httpStatus = (error as? HttpException)?.code(),
                        ),
                    ),
                    createdAtMillis = now,
                ),
            )
        }
        caseId?.let { runCatching { refreshCaseDetailForSession(session, it) } }
    }

    private suspend fun queuePendingWrite(
        ownerAccountId: String,
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
                ownerAccountId = ownerAccountId,
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

    private suspend fun markCacheFresh(ownerAccountId: String, cacheKey: String) {
        database.cacheMetadataDao().upsertMetadata(
            CacheMetadataEntity(
                ownerAccountId = ownerAccountId,
                cacheKey = cacheKey,
                updatedAtMillis = System.currentTimeMillis(),
            ),
        )
    }
}

@OptIn(ExperimentalPagingApi::class)
private class CaseRemoteMediator(
    private val ownerAccountId: String,
    private val accountGeneration: Long,
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
    private val isAccountActive: () -> Boolean,
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

            database.commitForAccount(
                ownerAccountId = ownerAccountId,
                generation = accountGeneration,
                isLocallyActive = isAccountActive,
            ) {
                if (loadType == LoadType.REFRESH) {
                    database.caseDao().clearCases(ownerAccountId)
                }
                database.caseDao().upsertCases(response.results.map { it.toEntity(ownerAccountId) })
                database.caseStatsDao().upsertStats(response.stats.toEntity(ownerAccountId, cacheKey))
                database.cacheMetadataDao().upsertMetadata(
                    CacheMetadataEntity(
                        ownerAccountId = ownerAccountId,
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
    name = name,
    prefix = "",
    firstName = "",
    lastName = "",
    gender = "",
    genderLabel = "",
    bloodGroup = "",
    dateOfBirth = null,
    age = null,
    place = "",
    phoneNumber = "",
    alternatePhoneNumber = "",
    isTemporaryId = false,
    activeCaseCount = null,
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
    surgeryDone = surgeryDone ?: false,
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

internal fun NewCaseInput.toUpdateRequestDto(
    clientWriteId: String,
    baseline: CaseEditCaseDto,
): UpdateCaseRequestDto = UpdateCaseRequestDto(
    patientMode = changed(patientMode, baseline.patientMode),
    selectedPatient = changed(selectedPatientId, baseline.selectedPatient),
    useTemporaryUhid = changed(useTemporaryUhid, baseline.useTemporaryUhid),
    uhid = changedText(uhid, baseline.uhid),
    prefix = changedText(prefix, baseline.prefix),
    firstName = changedText(firstName, baseline.firstName),
    lastName = changedText(lastName, baseline.lastName),
    gender = changedText(gender, baseline.gender),
    bloodGroup = changedText(bloodGroup, baseline.bloodGroup),
    dateOfBirth = changedText(dateOfBirth, baseline.dateOfBirth),
    place = changedText(place, baseline.place),
    age = changed(age, baseline.age),
    phoneNumber = changedText(phoneNumber, baseline.phoneNumber),
    alternatePhoneNumber = changedText(alternatePhoneNumber, baseline.alternatePhoneNumber),
    category = changed(categoryId, baseline.category),
    subcategory = changedText(subcategory, baseline.subcategory),
    status = changedText(status, baseline.status),
    diagnosis = changedText(diagnosis, baseline.diagnosis),
    referredBy = changedText(referredBy, baseline.referredBy),
    notes = changedText(notes, baseline.notes),
    highRisk = changed(highRisk, baseline.highRisk),
    ncdFlags = changed(ncdFlags, baseline.ncdFlags),
    ancHighRiskReasons = changed(ancHighRiskReasons, baseline.ancHighRiskReasons),
    rchNumber = changedText(rchNumber, baseline.rchNumber),
    rchBypass = changed(rchBypass, baseline.rchBypass),
    lmp = changedText(lmp, baseline.lmp),
    edd = changedText(edd, baseline.edd),
    usgEdd = changedText(usgEdd, baseline.usgEdd),
    surgicalPathway = changedText(surgicalPathway, baseline.surgicalPathway),
    surgeryDone = changed(surgeryDone, baseline.surgeryDone),
    surgeryDate = changedText(surgeryDate, baseline.surgeryDate),
    reviewFrequency = changedText(reviewFrequency, baseline.reviewFrequency),
    reviewDate = changedText(reviewDate, baseline.reviewDate),
    gravida = changed(gravida, baseline.gravida),
    para = changed(para, baseline.para),
    abortions = changed(abortions, baseline.abortions),
    living = changed(living, baseline.living),
    ftnd = changed(ftnd, baseline.ftnd),
    lscs = changed(lscs, baseline.lscs),
    clientWriteId = clientWriteId,
)

private fun <T> changed(current: T, baseline: T?): T? = current.takeIf { it != baseline }

private fun changedText(current: String?, baseline: String?): String? =
    if (current == baseline) null else current.orEmpty()

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
        dateOfBirth = case.dateOfBirth,
        place = case.place,
        age = case.age,
        phoneNumber = case.phoneNumber,
        alternatePhoneNumber = case.alternatePhoneNumber,
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
        surgeryDone = case.surgeryDone,
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

private fun Throwable.httpErrorBody(): String? =
    (this as? HttpException)
        ?.response()
        ?.errorBody()
        ?.string()
        ?.takeIf { it.isNotBlank() }

private fun VitalsRequestDto.toPendingVitalEntity(
    ownerAccountId: String,
    caseId: String,
    clientWriteId: String,
): VitalEntity =
    VitalEntity(
        ownerAccountId = ownerAccountId,
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

private fun CaseSummaryDto.toEntity(ownerAccountId: String): CaseEntity =
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

private fun TaskDto.toEntity(ownerAccountId: String, caseId: String): TaskEntity =
    TaskEntity(
        ownerAccountId = ownerAccountId,
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

private fun VitalDto.toEntity(ownerAccountId: String, caseId: String): VitalEntity =
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

private fun CaseStatsDto.toEntity(ownerAccountId: String, cacheKey: String): CaseStatsEntity =
    CaseStatsEntity(
        ownerAccountId = ownerAccountId,
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

private fun NotificationDto.toEntity(ownerAccountId: String): NotificationEntity =
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
    SyncRecoveryJson.decode(serverPayloadJson).let { recovery -> SyncConflict(
        clientWriteId = clientWriteId,
        writeType = writeType,
        caseId = caseId,
        taskId = taskId,
        message = message,
        createdAtMillis = createdAtMillis,
        failureKind = recovery?.failureKind ?: SyncFailureKinds.CONFLICT,
        localPayloadJson = recovery?.localPayloadJson,
        serverPayloadJson = recovery?.serverPayloadJson,
        httpStatus = recovery?.httpStatus,
        resolutionState = recovery?.resolutionState ?: SyncResolutionStates.OPEN,
    ) }

private val vitalsThresholdsJsonAdapter = Moshi.Builder()
    .add(KotlinJsonAdapterFactory())
    .build()
    .adapter(VitalsThresholdsDto::class.java)

private val categoryOptionsJsonAdapter = Moshi.Builder()
    .add(KotlinJsonAdapterFactory())
    .build()
    .adapter(CategoriesResponseDto::class.java)

private fun CategoriesResponseDto.toEntity(ownerAccountId: String): CategoryOptionsEntity =
    CategoryOptionsEntity(
        ownerAccountId = ownerAccountId,
        id = "current",
        payloadJson = categoryOptionsJsonAdapter.toJson(this),
        updatedAtMillis = System.currentTimeMillis(),
    )

private fun CategoryOptionsEntity.toDomain(): List<CategoryFilterOption> =
    categoryOptionsJsonAdapter.fromJson(payloadJson)
        ?.categories
        ?.map { it.toFilterOption() }
        .orEmpty()

private fun VitalsThresholdsDto.toEntity(ownerAccountId: String): VitalsThresholdEntity =
    VitalsThresholdEntity(
        ownerAccountId = ownerAccountId,
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
