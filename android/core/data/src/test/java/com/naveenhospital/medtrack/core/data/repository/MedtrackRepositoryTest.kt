package com.naveenhospital.medtrack.core.data.repository

import androidx.room.Room
import androidx.test.core.app.ApplicationProvider
import com.naveenhospital.medtrack.core.data.local.MedtrackDatabase
import com.naveenhospital.medtrack.core.data.local.CacheMetadataEntity
import com.naveenhospital.medtrack.core.data.local.PendingWriteEntity
import com.naveenhospital.medtrack.core.data.local.SyncConflictEntity
import com.naveenhospital.medtrack.core.data.local.NotificationEntity
import com.naveenhospital.medtrack.core.data.local.PushTokenEntity
import com.naveenhospital.medtrack.core.data.local.TaskEntity
import com.naveenhospital.medtrack.core.data.sync.PendingWriteJson
import com.naveenhospital.medtrack.core.data.sync.PendingWriteTypes
import com.naveenhospital.medtrack.core.domain.model.CaseCategory
import com.naveenhospital.medtrack.core.domain.model.NotificationPayload
import com.naveenhospital.medtrack.core.network.api.MedtrackApi
import com.naveenhospital.medtrack.core.network.model.ApiMessageDto
import com.naveenhospital.medtrack.core.network.model.AuthSessionDto
import com.naveenhospital.medtrack.core.network.model.CallLogDto
import com.naveenhospital.medtrack.core.network.model.CallWriteResponseDto
import com.naveenhospital.medtrack.core.network.model.CaseCategoryDto
import com.naveenhospital.medtrack.core.network.model.CaseDetailDto
import com.naveenhospital.medtrack.core.network.model.CaseListResponseDto
import com.naveenhospital.medtrack.core.network.model.CaseStatsDto
import com.naveenhospital.medtrack.core.network.model.CaseSummaryDto
import com.naveenhospital.medtrack.core.network.model.CaseSubcategoryDto
import com.naveenhospital.medtrack.core.network.model.CategoriesResponseDto
import com.naveenhospital.medtrack.core.network.model.ClientWriteRequestDto
import com.naveenhospital.medtrack.core.network.model.LogCallRequestDto
import com.naveenhospital.medtrack.core.network.model.LoginRequestDto
import com.naveenhospital.medtrack.core.network.model.NotificationDto
import com.naveenhospital.medtrack.core.network.model.NotificationsResponseDto
import com.naveenhospital.medtrack.core.network.model.RefreshTokenRequestDto
import com.naveenhospital.medtrack.core.network.model.RegisterPushTokenRequestDto
import com.naveenhospital.medtrack.core.network.model.TaskWriteResponseDto
import com.naveenhospital.medtrack.core.network.model.UserProfileDto
import com.naveenhospital.medtrack.core.network.model.VitalsRequestDto
import com.naveenhospital.medtrack.core.network.model.VitalsThresholdsDto
import com.naveenhospital.medtrack.core.network.model.VitalsWriteResponseDto
import java.io.IOException
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.async
import kotlinx.coroutines.test.runTest
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.ResponseBody.Companion.toResponseBody
import org.json.JSONObject
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import retrofit2.HttpException
import retrofit2.Response
import org.robolectric.RobolectricTestRunner

@RunWith(RobolectricTestRunner::class)
class MedtrackRepositoryTest {
    private lateinit var database: MedtrackDatabase

    @Before
    fun setUp() {
        database = Room.inMemoryDatabaseBuilder(
            ApplicationProvider.getApplicationContext(),
            MedtrackDatabase::class.java,
        )
            .allowMainThreadQueries()
            .build()
    }

    @After
    fun tearDown() {
        database.close()
    }

    @Test
    fun categoryOptionsAreCachedAndLoadedWithoutNetwork() = runTest {
        val api = FakeMedtrackApi(categoriesResponse = categoryResponse())
        val repository = repository(api)

        repository.refreshCategoryOptions()

        assertEquals(1, api.categoryCalls)
        assertNotNull(database.cacheMetadataDao().updatedAtMillis(ACCOUNT_ID, CACHE_KEY_CATEGORY_OPTIONS))

        val offlineApi = FakeMedtrackApi(categoriesError = IOException("offline"))
        val offlineRepository = repository(offlineApi)

        offlineRepository.loadCachedCategoryOptions()

        val cached = offlineRepository.categoryOptions.value
        assertEquals(0, offlineApi.categoryCalls)
        assertEquals(1, cached.size)
        assertEquals("1", cached.single().value)
        assertEquals("ANC", cached.single().label)
        assertEquals(CaseCategory.ANC, cached.single().category)
        assertEquals("anc_high_risk", cached.single().subcategories.single().value)
        assertEquals("High-risk ANC", cached.single().subcategories.single().label)
    }

    @Test
    fun refreshCasesUsesServerDefaultAssignmentScopeWhenOmitted() = runTest {
        val api = FakeMedtrackApi()
        val repository = repository(api)

        repository.refreshCases()

        assertNull(api.lastListCasesAssignedTo)
    }

    @Test
    fun refreshCasesCanSendCallsScopeContext() = runTest {
        val api = FakeMedtrackApi()
        val repository = repository(api)

        repository.refreshCases(bucket = "all", assignedTo = "all", scopeContext = "calls")

        assertEquals("all", api.lastListCasesAssignedTo)
        assertEquals("calls", api.lastListCasesScopeContext)
    }

    @Test
    fun refreshNotificationsPreservesPayloadJsonAndParsedDomainPayload() = runTest {
        val api = FakeMedtrackApi(
            notificationsResponse = NotificationsResponseDto(
                count = 1,
                next = null,
                previous = null,
                results = listOf(
                    NotificationDto(
                        id = 5543,
                        type = "red_flag",
                        title = "Red flag patient",
                        body = "Ms. Harini Sivakumar: High risk",
                        caseId = 6364,
                        taskId = null,
                        payload = mapOf("channel" to "red_flags", "reasons" to listOf("High risk")),
                        readAt = null,
                        createdAt = "2026-06-01T10:00:00Z",
                    ),
                ),
            ),
        )
        val repository = repository(api)

        repository.refreshNotifications()

        val entity = database.notificationDao().observeNotifications(ACCOUNT_ID).first().single()
        val storedJson = JSONObject(entity.payloadJson)
        assertEquals("High risk", storedJson.getJSONArray("reasons").getString(0))
        val item = repository.notifications.first().single()
        assertEquals(NotificationPayload.RedFlag(listOf("High risk")), item.payload)
    }

    @Test
    fun logCallOutcomeSendsProvidedAttemptedAt() = runTest {
        val api = FakeMedtrackApi()
        val repository = repository(api)

        repository.logCallOutcome(
            caseId = "42",
            taskId = "7",
            outcome = "no-answer",
            note = "Returned from dialer",
            attemptedAt = "2026-05-18T09:37:57Z",
        )

        assertEquals("42", api.lastLogCallCaseId)
        assertEquals("no-answer", api.lastLogCallRequest?.outcome)
        assertEquals(7L, api.lastLogCallRequest?.taskId)
        assertEquals("Returned from dialer", api.lastLogCallRequest?.note)
        assertEquals("2026-05-18T09:37:57Z", api.lastLogCallRequest?.attemptedAt)
    }

    @Test
    fun pushTokenDaoTracksPendingAndSyncedTokens() = runTest {
        database.pushTokenDao().upsertToken(
            PushTokenEntity(
                ownerAccountId = ACCOUNT_ID,
                token = "pending-token",
                deviceLabel = "Redmi test",
                syncedAtMillis = 0L,
            ),
        )
        database.pushTokenDao().upsertToken(
            PushTokenEntity(
                ownerAccountId = ACCOUNT_ID,
                token = "synced-token",
                deviceLabel = "Pixel test",
                syncedAtMillis = 123L,
            ),
        )

        assertEquals(listOf("pending-token"), database.pushTokenDao().pendingTokens(ACCOUNT_ID).map { it.token })

        database.pushTokenDao().markTokenSynced(ACCOUNT_ID, "pending-token", 456L)

        assertEquals(emptyList<String>(), database.pushTokenDao().pendingTokens(ACCOUNT_ID).map { it.token })
    }

    @Test
    fun registerPushTokenLeavesPendingTokenWhenNetworkFails() = runTest {
        val api = FakeMedtrackApi(registerPushError = IOException("offline"))
        val repository = repository(api)

        runCatching {
            repository.registerPushToken(token = "fcm-token", deviceLabel = "Redmi test")
        }

        val pending = database.pushTokenDao().pendingTokens(ACCOUNT_ID)
        assertEquals(1, pending.size)
        assertEquals("fcm-token", pending.single().token)
        assertEquals("Redmi test", pending.single().deviceLabel)
    }

    @Test
    fun markNotificationReadQueuesWhenNetworkFails() = runTest {
        database.notificationDao().upsertNotifications(
            listOf(
                NotificationEntity(
                    ownerAccountId = ACCOUNT_ID,
                    id = "99",
                    type = "assignment",
                    title = "New task",
                    body = "Follow-up due",
                    caseId = "42",
                    taskId = "7",
                    createdAt = "2026-05-18T10:00:00Z",
                    isRead = false,
                ),
            ),
        )
        val api = FakeMedtrackApi(notificationReadError = IOException("offline"))
        var queuedCallbacks = 0
        val repository = repository(
            api = api,
            database = database,
            onPendingWriteQueued = { queuedCallbacks += 1 },
        )

        repository.markNotificationRead("99")

        assertEquals(1, api.notificationReadCalls)
        assertEquals(1, queuedCallbacks)
        assertEquals(true, database.notificationDao().observeNotifications(ACCOUNT_ID).first().single().isRead)
        val pending = database.pendingWriteDao().pendingWrites(ACCOUNT_ID).single()
        assertEquals(PendingWriteTypes.NOTIFICATION_READ, pending.writeType)
        assertEquals("99", pending.taskId)
    }

    @Test
    fun completeTaskQueuesAndMarksLocalTaskDoneWhenOffline() = runTest {
        database.taskDao().upsertTask(
            TaskEntity(
                ownerAccountId = ACCOUNT_ID,
                id = "7",
                caseId = "42",
                title = "Follow-up",
                dueDate = "2026-05-18",
                status = "PENDING",
                statusLabel = "Pending",
                canComplete = true,
                updatedAtMillis = 1L,
            ),
        )
        val api = FakeMedtrackApi(completeTaskError = IOException("offline"))
        var queuedCallbacks = 0
        val repository = repository(
            api = api,
            database = database,
            onPendingWriteQueued = { queuedCallbacks += 1 },
        )

        val result = repository.completeTask(taskId = "7", caseId = "42")

        assertTrue(result.queued)
        assertEquals(1, queuedCallbacks)
        val pending = database.pendingWriteDao().pendingWrites(ACCOUNT_ID).single()
        assertEquals(PendingWriteTypes.TASK_COMPLETE, pending.writeType)
        assertEquals("42", pending.caseId)
        assertEquals("7", pending.taskId)
        assertEquals(pending.clientWriteId, PendingWriteJson.decodeTaskComplete(pending.payloadJson).clientWriteId)
        val localTask = database.taskDao().observeTasksForCase(ACCOUNT_ID, "42").first().single()
        assertEquals("COMPLETED", localTask.status)
        assertEquals(false, localTask.canComplete)
    }

    @Test
    fun completeTaskRecordsConflictWhenServerReturns409() = runTest {
        val api = FakeMedtrackApi(completeTaskError = conflictError("Task was already changed on the server."))
        val repository = repository(api)

        val result = repository.completeTask(taskId = "7", caseId = "42")

        assertEquals(false, result.queued)
        assertTrue(result.conflict)
        assertEquals(emptyList<Any>(), database.pendingWriteDao().pendingWrites(ACCOUNT_ID))
        val conflict = database.syncConflictDao().observeConflicts(ACCOUNT_ID).first().single()
        assertEquals(PendingWriteTypes.TASK_COMPLETE, conflict.writeType)
        assertEquals("42", conflict.caseId)
        assertEquals("7", conflict.taskId)
        assertEquals("Task was already changed on the server.", conflict.message)
    }

    @Test
    fun logCallOutcomeQueuesPayloadWhenOffline() = runTest {
        val api = FakeMedtrackApi(logCallError = IOException("offline"))
        var queuedCallbacks = 0
        val repository = repository(
            api = api,
            database = database,
            onPendingWriteQueued = { queuedCallbacks += 1 },
        )

        val result = repository.logCallOutcome(
            caseId = "42",
            taskId = "7",
            outcome = "no-answer",
            note = "Dialer returned",
            attemptedAt = "2026-05-18T11:11:36Z",
        )

        assertTrue(result.queued)
        assertEquals(1, queuedCallbacks)
        val pending = database.pendingWriteDao().pendingWrites(ACCOUNT_ID).single()
        assertEquals(PendingWriteTypes.CALL_OUTCOME, pending.writeType)
        assertEquals("42", pending.caseId)
        assertEquals("7", pending.taskId)
        val payload = PendingWriteJson.decodeCallOutcome(pending.payloadJson)
        assertEquals(pending.clientWriteId, payload.clientWriteId)
        assertEquals("no-answer", payload.outcome)
        assertEquals(7L, payload.taskId)
        assertEquals("Dialer returned", payload.note)
        assertEquals("2026-05-18T11:11:36Z", payload.attemptedAt)
    }

    @Test
    fun logCallOutcomeRecordsConflictWhenServerReturns409() = runTest {
        val api = FakeMedtrackApi(logCallError = conflictError("Server version kept for the call log."))
        val repository = repository(api)

        val result = repository.logCallOutcome(
            caseId = "42",
            taskId = "7",
            outcome = "no-answer",
            note = "Dialer returned",
            attemptedAt = "2026-05-18T11:11:36Z",
        )

        assertEquals(false, result.queued)
        assertTrue(result.conflict)
        assertEquals(emptyList<Any>(), database.pendingWriteDao().pendingWrites(ACCOUNT_ID))
        val conflict = database.syncConflictDao().observeConflicts(ACCOUNT_ID).first().single()
        assertEquals(PendingWriteTypes.CALL_OUTCOME, conflict.writeType)
        assertEquals("42", conflict.caseId)
        assertEquals("7", conflict.taskId)
        assertEquals("Server version kept for the call log.", conflict.message)
    }

    @Test
    fun addVitalsQueuesAndAddsPendingVitalWhenOffline() = runTest {
        val api = FakeMedtrackApi(addVitalsError = IOException("offline"))
        var queuedCallbacks = 0
        val repository = repository(
            api = api,
            database = database,
            onPendingWriteQueued = { queuedCallbacks += 1 },
        )

        val result = repository.addVitals(
            caseId = "42",
            bpSystolic = 121,
            bpDiastolic = 79,
            pulse = 82,
            spo2 = 97,
            weightKg = "54.5",
            hemoglobin = "11.2",
        )

        assertTrue(result.queued)
        assertEquals(1, queuedCallbacks)
        val pending = database.pendingWriteDao().pendingWrites(ACCOUNT_ID).single()
        assertEquals(PendingWriteTypes.VITALS_CREATE, pending.writeType)
        assertEquals("42", pending.caseId)
        val payload = PendingWriteJson.decodeVitals(pending.payloadJson)
        assertEquals(pending.clientWriteId, payload.clientWriteId)
        assertEquals(121, payload.bpSystolic)
        assertEquals(79, payload.bpDiastolic)
        assertEquals(82, payload.pr)
        assertEquals(97, payload.spo2)
        assertEquals("54.5", payload.weightKg)
        assertEquals("11.2", payload.hemoglobin)
        val pendingVital = database.vitalDao().observeVitalsForCase(ACCOUNT_ID, "42").first().single()
        assertEquals("pending-${pending.clientWriteId}", pendingVital.id)
        assertEquals("BP 121/79 | PR 82 | SpO2 97 | Hb 11.2 | Wt 54.5 kg", pendingVital.summary)
    }

    @Test
    fun addVitalsRecordsConflictWhenServerReturns409() = runTest {
        val api = FakeMedtrackApi(addVitalsError = conflictError("Vitals were already updated on the server."))
        val repository = repository(api)

        val result = repository.addVitals(
            caseId = "42",
            bpSystolic = 121,
            bpDiastolic = 79,
            pulse = 82,
            spo2 = 97,
            weightKg = "54.5",
            hemoglobin = "11.2",
        )

        assertEquals(false, result.queued)
        assertTrue(result.conflict)
        assertEquals(emptyList<Any>(), database.pendingWriteDao().pendingWrites(ACCOUNT_ID))
        assertEquals(emptyList<Any>(), database.vitalDao().observeVitalsForCase(ACCOUNT_ID, "42").first())
        val conflict = database.syncConflictDao().observeConflicts(ACCOUNT_ID).first().single()
        assertEquals(PendingWriteTypes.VITALS_CREATE, conflict.writeType)
        assertEquals("42", conflict.caseId)
        assertEquals(null, conflict.taskId)
        assertEquals("Vitals were already updated on the server.", conflict.message)
    }

    @Test
    fun accountSwitchShowsOnlyNewOwnersCacheAndWipeCannotDeleteIt() = runTest {
        database.notificationDao().upsertNotifications(
            listOf(
                notification(ownerAccountId = "account-a", title = "Account A PHI"),
                notification(ownerAccountId = "account-b", title = "Account B PHI"),
            ),
        )
        val repository = MedtrackRepository(api = FakeMedtrackApi(), database = database)

        repository.activateAccount("account-a")
        assertEquals(listOf("Account A PHI"), repository.notifications.first().map { it.title })

        repository.activateAccount("account-b")
        assertEquals(listOf("Account B PHI"), repository.notifications.first().map { it.title })

        repository.wipeAccountData("account-a")
        assertTrue(database.notificationDao().observeNotifications("account-a").first().isEmpty())
        assertEquals(
            listOf("Account B PHI"),
            database.notificationDao().observeNotifications("account-b").first().map { it.title },
        )
        assertEquals(listOf("Account B PHI"), repository.notifications.first().map { it.title })
    }

    @Test
    fun staleNetworkCommitCannotResurrectPurgedOwnerAfterSwitch() = runTest {
        val commitReached = CompletableDeferred<Unit>()
        val allowCommit = CompletableDeferred<Unit>()
        val response = CaseListResponseDto(
            count = 0,
            next = null,
            previous = null,
            stats = CaseStatsDto(today = 1, upcoming = 0, overdue = 0, awaiting = 0, red = 0),
            results = emptyList(),
        )
        val repository = MedtrackRepository(
            apiForAccount = { FakeMedtrackApi(caseListResponse = response) },
            database = database,
            beforeLocalCommit = { accountId ->
                if (accountId == "account-a") {
                    commitReached.complete(Unit)
                    allowCommit.await()
                }
            },
        )
        repository.activateAccount("account-a")
        database.pendingWriteDao().upsertPendingWrite(
            PendingWriteEntity(
                ownerAccountId = "account-a",
                clientWriteId = "old-write",
                writeType = PendingWriteTypes.TASK_COMPLETE,
                caseId = "42",
                taskId = "7",
                payloadJson = "{}",
                retryCount = 0,
                lastError = null,
                createdAtMillis = 1L,
                updatedAtMillis = 1L,
            ),
        )
        database.syncConflictDao().upsertConflict(
            SyncConflictEntity(
                ownerAccountId = "account-a",
                clientWriteId = "old-conflict",
                writeType = PendingWriteTypes.TASK_COMPLETE,
                caseId = "42",
                taskId = "7",
                message = "old conflict",
                serverPayloadJson = null,
                createdAtMillis = 1L,
            ),
        )
        database.pushTokenDao().upsertToken(PushTokenEntity("account-a", "old-token", "device", 0L))
        database.notificationDao().upsertNotifications(listOf(notification("account-a", "Old PHI")))
        database.cacheMetadataDao().upsertMetadata(CacheMetadataEntity("account-a", "seed", 1L))

        val staleRefresh = async { runCatching { repository.refreshCases() } }
        commitReached.await()
        repository.deactivateAccount()
        repository.wipeAccountData("account-a")
        repository.activateAccount("account-b")
        allowCommit.complete(Unit)

        assertTrue(staleRefresh.await().isFailure)
        assertTrue(database.pendingWriteDao().pendingWrites("account-a").isEmpty())
        assertTrue(database.syncConflictDao().observeConflicts("account-a").first().isEmpty())
        assertNull(database.pushTokenDao().latestToken("account-a"))
        assertTrue(database.notificationDao().observeNotifications("account-a").first().isEmpty())
        assertNull(database.cacheMetadataDao().updatedAtMillis("account-a", "seed"))
        assertNull(database.caseStatsDao().statsForKey("account-a", caseListCacheKey("today", null, null, null, emptyList(), emptyList())))
        assertTrue(repository.cases.first().isEmpty())
        assertTrue(database.pendingWriteDao().pendingWrites("account-b").isEmpty())
        assertTrue(database.syncConflictDao().observeConflicts("account-b").first().isEmpty())
        assertNull(database.pushTokenDao().latestToken("account-b"))
    }

    private fun notification(ownerAccountId: String, title: String): NotificationEntity =
        NotificationEntity(
            ownerAccountId = ownerAccountId,
            id = "same-server-id",
            type = "assignment",
            title = title,
            body = "owner-specific body",
            caseId = "42",
            taskId = "7",
            createdAt = "2026-08-29T12:00:00Z",
            isRead = false,
        )

    private suspend fun repository(
        api: MedtrackApi,
        database: MedtrackDatabase = this.database,
        onPendingWriteQueued: (String) -> Unit = {},
    ): MedtrackRepository = MedtrackRepository(
        api = api,
        database = database,
        onPendingWriteQueued = onPendingWriteQueued,
    ).also { it.activateAccount(ACCOUNT_ID) }

    private fun categoryResponse(): CategoriesResponseDto =
        CategoriesResponseDto(
            categories = listOf(
                CaseCategoryDto(
                    id = 1,
                    name = "ANC",
                    iconPath = "/static/patients/icons/categories/anc.svg",
                    subcategories = listOf(
                        CaseSubcategoryDto(
                            value = "anc_high_risk",
                            label = "High-risk ANC",
                            iconPath = "/static/patients/icons/subcategories/high_risk.svg",
                        ),
                    ),
                ),
            ),
        )

    private fun conflictError(message: String): HttpException =
        HttpException(
            Response.error<Any>(
                409,
                message.toResponseBody("text/plain".toMediaType()),
            ),
        )

    private companion object {
        const val ACCOUNT_ID = "1"
    }
}

private class FakeMedtrackApi(
    private val categoriesResponse: CategoriesResponseDto = CategoriesResponseDto(emptyList()),
    private val caseListResponse: CaseListResponseDto = CaseListResponseDto(
        count = 0,
        next = null,
        previous = null,
        stats = CaseStatsDto(today = 0, upcoming = 0, overdue = 0, awaiting = 0, red = 0),
        results = emptyList(),
    ),
    private val notificationsResponse: NotificationsResponseDto = NotificationsResponseDto(
        count = 0,
        next = null,
        previous = null,
        results = emptyList(),
    ),
    private val categoriesError: Throwable? = null,
    private val registerPushError: Throwable? = null,
    private val notificationReadError: Throwable? = null,
    private val completeTaskError: Throwable? = null,
    private val logCallError: Throwable? = null,
    private val addVitalsError: Throwable? = null,
) : MedtrackApi {
    var categoryCalls = 0
        private set
    var notificationReadCalls = 0
        private set
    var lastLogCallCaseId: String? = null
        private set
    var lastLogCallRequest: LogCallRequestDto? = null
        private set
    var lastListCasesAssignedTo: String? = null
        private set
    var lastListCasesScopeContext: String? = null
        private set

    override suspend fun categories(): CategoriesResponseDto {
        categoryCalls += 1
        categoriesError?.let { throw it }
        return categoriesResponse
    }

    override suspend fun login(request: LoginRequestDto): AuthSessionDto = unused()
    override suspend fun refresh(request: RefreshTokenRequestDto): AuthSessionDto = unused()
    override suspend fun logout(request: RefreshTokenRequestDto): ApiMessageDto = unused()
    override suspend fun me(): UserProfileDto = unused()
    override suspend fun listCases(
        bucket: String?,
        assignedTo: String?,
        scopeContext: String?,
        categories: List<String>?,
        subcategories: List<String>?,
        query: String?,
        page: Int?,
    ): CaseListResponseDto {
        lastListCasesAssignedTo = assignedTo
        lastListCasesScopeContext = scopeContext
        return caseListResponse
    }

    override suspend fun caseDetail(caseId: String): CaseDetailDto = unused()
    override suspend fun createCase(request: com.naveenhospital.medtrack.core.network.model.CreateCaseRequestDto): com.naveenhospital.medtrack.core.network.model.CaseCreateResponseDto = unused()
    override suspend fun searchPatients(query: String?, page: Int?): com.naveenhospital.medtrack.core.network.model.PatientSearchResponseDto = unused()
    override suspend fun caseFormMetadata(): com.naveenhospital.medtrack.core.network.model.CaseFormMetadataDto = unused()
    override suspend fun taskFormMetadata(): com.naveenhospital.medtrack.core.network.model.TaskFormMetadataDto = unused()
    override suspend fun caseEditForm(caseId: String): com.naveenhospital.medtrack.core.network.model.CaseEditFormDto = unused()
    override suspend fun updateCase(caseId: String, request: com.naveenhospital.medtrack.core.network.model.CreateCaseRequestDto): com.naveenhospital.medtrack.core.network.model.CaseCreateResponseDto = unused()
    override suspend fun createTask(caseId: String, request: com.naveenhospital.medtrack.core.network.model.CreateTaskRequestDto): TaskWriteResponseDto = unused()
    override suspend fun updateTask(taskId: String, request: com.naveenhospital.medtrack.core.network.model.UpdateTaskRequestDto): TaskWriteResponseDto = unused()
    override suspend fun addTaskNote(taskId: String, request: com.naveenhospital.medtrack.core.network.model.TaskNoteRequestDto): TaskWriteResponseDto = unused()
    override suspend fun updateVitals(vitalId: String, request: com.naveenhospital.medtrack.core.network.model.VitalsUpdateRequestDto): VitalsWriteResponseDto = unused()
    override suspend fun completeTask(taskId: String, request: ClientWriteRequestDto): TaskWriteResponseDto {
        completeTaskError?.let { throw it }
        return TaskWriteResponseDto(
            message = "Task completed.",
            task = sampleTask(taskId.toLong()),
            case = sampleCaseSummary(),
        )
    }
    override suspend fun logCall(caseId: String, request: LogCallRequestDto): CallWriteResponseDto {
        logCallError?.let { throw it }
        lastLogCallCaseId = caseId
        lastLogCallRequest = request
        return CallWriteResponseDto(
            message = "Call outcome logged.",
            callLog = CallLogDto(
                id = 1,
                taskId = request.taskId,
                outcome = request.outcome,
                outcomeLabel = "No answer",
                notes = request.note,
                createdAt = request.attemptedAt.orEmpty(),
            ),
            case = sampleCaseSummary(),
        )
    }
    override suspend fun addVitals(caseId: String, request: VitalsRequestDto): VitalsWriteResponseDto {
        addVitalsError?.let { throw it }
        return VitalsWriteResponseDto(
            message = "Vitals added.",
            latestVitalId = 10,
            vital = com.naveenhospital.medtrack.core.network.model.VitalDto(
                id = 10,
                recordedAt = "2026-05-18T11:11:36Z",
                bpSystolic = request.bpSystolic,
                bpDiastolic = request.bpDiastolic,
                pr = request.pr,
                spo2 = request.spo2,
                weightKg = request.weightKg,
                hemoglobin = request.hemoglobin,
            ),
            case = sampleCaseSummary(),
        )
    }
    override suspend fun vitalsThresholds(): VitalsThresholdsDto = unused()
    override suspend fun notifications(type: String?, unreadOnly: Boolean?, page: Int?): NotificationsResponseDto =
        notificationsResponse
    override suspend fun markNotificationRead(notificationId: String): ApiMessageDto {
        notificationReadCalls += 1
        notificationReadError?.let { throw it }
        return ApiMessageDto(message = "Read")
    }
    override suspend fun registerPushToken(request: RegisterPushTokenRequestDto): ApiMessageDto {
        registerPushError?.let { throw it }
        return ApiMessageDto(message = "Registered")
    }

    private fun unused(): Nothing = error("Not used by this test")

    private fun sampleCaseSummary(): CaseSummaryDto =
        CaseSummaryDto(
            id = 42,
            uhid = "UH-TEST-42",
            name = "Test Patient",
            age = 30,
            sex = "F",
            sexLabel = "Female",
            place = "Test Village",
            phoneNumber = "9876543210",
            category = CaseCategoryDto(id = 1, name = "ANC"),
            subcategory = null,
            status = "ACTIVE",
            diagnosis = "Review",
            redFlag = false,
            redFlagReasons = emptyList(),
            nextTask = null,
            latestVital = null,
        )

    private fun sampleTask(id: Long): com.naveenhospital.medtrack.core.network.model.TaskDto =
        com.naveenhospital.medtrack.core.network.model.TaskDto(
            id = id,
            title = "Follow-up",
            dueDate = "2026-05-18",
            status = "COMPLETED",
            statusLabel = "Completed",
            canComplete = false,
        )
}
