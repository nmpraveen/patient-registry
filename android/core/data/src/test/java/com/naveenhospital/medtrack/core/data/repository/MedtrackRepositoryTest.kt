package com.naveenhospital.medtrack.core.data.repository

import androidx.room.Room
import androidx.test.core.app.ApplicationProvider
import com.naveenhospital.medtrack.core.data.local.MedtrackDatabase
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
        val repository = MedtrackRepository(api = api, database = database)

        repository.refreshCategoryOptions()

        assertEquals(1, api.categoryCalls)
        assertNotNull(database.cacheMetadataDao().updatedAtMillis(CACHE_KEY_CATEGORY_OPTIONS))

        val offlineApi = FakeMedtrackApi(categoriesError = IOException("offline"))
        val offlineRepository = MedtrackRepository(api = offlineApi, database = database)

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
        val repository = MedtrackRepository(api = api, database = database)

        repository.refreshCases()

        assertNull(api.lastListCasesAssignedTo)
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
        val repository = MedtrackRepository(api = api, database = database)

        repository.refreshNotifications()

        val entity = database.notificationDao().observeNotifications().first().single()
        val storedJson = JSONObject(entity.payloadJson)
        assertEquals("High risk", storedJson.getJSONArray("reasons").getString(0))
        val item = repository.notifications.first().single()
        assertEquals(NotificationPayload.RedFlag(listOf("High risk")), item.payload)
    }

    @Test
    fun logCallOutcomeSendsProvidedAttemptedAt() = runTest {
        val api = FakeMedtrackApi()
        val repository = MedtrackRepository(api = api, database = database)

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
                token = "pending-token",
                deviceLabel = "Redmi test",
                syncedAtMillis = 0L,
            ),
        )
        database.pushTokenDao().upsertToken(
            PushTokenEntity(
                token = "synced-token",
                deviceLabel = "Pixel test",
                syncedAtMillis = 123L,
            ),
        )

        assertEquals(listOf("pending-token"), database.pushTokenDao().pendingTokens().map { it.token })

        database.pushTokenDao().markTokenSynced("pending-token", 456L)

        assertEquals(emptyList<String>(), database.pushTokenDao().pendingTokens().map { it.token })
    }

    @Test
    fun registerPushTokenLeavesPendingTokenWhenNetworkFails() = runTest {
        val api = FakeMedtrackApi(registerPushError = IOException("offline"))
        val repository = MedtrackRepository(api = api, database = database)

        runCatching {
            repository.registerPushToken(token = "fcm-token", deviceLabel = "Redmi test")
        }

        val pending = database.pushTokenDao().pendingTokens()
        assertEquals(1, pending.size)
        assertEquals("fcm-token", pending.single().token)
        assertEquals("Redmi test", pending.single().deviceLabel)
    }

    @Test
    fun markNotificationReadQueuesWhenNetworkFails() = runTest {
        database.notificationDao().upsertNotifications(
            listOf(
                NotificationEntity(
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
        val repository = MedtrackRepository(
            api = api,
            database = database,
            onPendingWriteQueued = { queuedCallbacks += 1 },
        )

        repository.markNotificationRead("99")

        assertEquals(1, api.notificationReadCalls)
        assertEquals(1, queuedCallbacks)
        assertEquals(true, database.notificationDao().observeNotifications().first().single().isRead)
        val pending = database.pendingWriteDao().pendingWrites().single()
        assertEquals(PendingWriteTypes.NOTIFICATION_READ, pending.writeType)
        assertEquals("99", pending.taskId)
    }

    @Test
    fun completeTaskQueuesAndMarksLocalTaskDoneWhenOffline() = runTest {
        database.taskDao().upsertTask(
            TaskEntity(
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
        val repository = MedtrackRepository(
            api = api,
            database = database,
            onPendingWriteQueued = { queuedCallbacks += 1 },
        )

        val result = repository.completeTask(taskId = "7", caseId = "42")

        assertTrue(result.queued)
        assertEquals(1, queuedCallbacks)
        val pending = database.pendingWriteDao().pendingWrites().single()
        assertEquals(PendingWriteTypes.TASK_COMPLETE, pending.writeType)
        assertEquals("42", pending.caseId)
        assertEquals("7", pending.taskId)
        assertEquals(pending.clientWriteId, PendingWriteJson.decodeTaskComplete(pending.payloadJson).clientWriteId)
        val localTask = database.taskDao().observeTasksForCase("42").first().single()
        assertEquals("COMPLETED", localTask.status)
        assertEquals(false, localTask.canComplete)
    }

    @Test
    fun completeTaskRecordsConflictWhenServerReturns409() = runTest {
        val api = FakeMedtrackApi(completeTaskError = conflictError("Task was already changed on the server."))
        val repository = MedtrackRepository(api = api, database = database)

        val result = repository.completeTask(taskId = "7", caseId = "42")

        assertEquals(false, result.queued)
        assertTrue(result.conflict)
        assertEquals(emptyList<Any>(), database.pendingWriteDao().pendingWrites())
        val conflict = database.syncConflictDao().observeConflicts().first().single()
        assertEquals(PendingWriteTypes.TASK_COMPLETE, conflict.writeType)
        assertEquals("42", conflict.caseId)
        assertEquals("7", conflict.taskId)
        assertEquals("Task was already changed on the server.", conflict.message)
    }

    @Test
    fun logCallOutcomeQueuesPayloadWhenOffline() = runTest {
        val api = FakeMedtrackApi(logCallError = IOException("offline"))
        var queuedCallbacks = 0
        val repository = MedtrackRepository(
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
        val pending = database.pendingWriteDao().pendingWrites().single()
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
        val repository = MedtrackRepository(api = api, database = database)

        val result = repository.logCallOutcome(
            caseId = "42",
            taskId = "7",
            outcome = "no-answer",
            note = "Dialer returned",
            attemptedAt = "2026-05-18T11:11:36Z",
        )

        assertEquals(false, result.queued)
        assertTrue(result.conflict)
        assertEquals(emptyList<Any>(), database.pendingWriteDao().pendingWrites())
        val conflict = database.syncConflictDao().observeConflicts().first().single()
        assertEquals(PendingWriteTypes.CALL_OUTCOME, conflict.writeType)
        assertEquals("42", conflict.caseId)
        assertEquals("7", conflict.taskId)
        assertEquals("Server version kept for the call log.", conflict.message)
    }

    @Test
    fun addVitalsQueuesAndAddsPendingVitalWhenOffline() = runTest {
        val api = FakeMedtrackApi(addVitalsError = IOException("offline"))
        var queuedCallbacks = 0
        val repository = MedtrackRepository(
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
        val pending = database.pendingWriteDao().pendingWrites().single()
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
        val pendingVital = database.vitalDao().observeVitalsForCase("42").first().single()
        assertEquals("pending-${pending.clientWriteId}", pendingVital.id)
        assertEquals("BP 121/79 | PR 82 | SpO2 97 | Hb 11.2 | Wt 54.5 kg", pendingVital.summary)
    }

    @Test
    fun addVitalsRecordsConflictWhenServerReturns409() = runTest {
        val api = FakeMedtrackApi(addVitalsError = conflictError("Vitals were already updated on the server."))
        val repository = MedtrackRepository(api = api, database = database)

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
        assertEquals(emptyList<Any>(), database.pendingWriteDao().pendingWrites())
        assertEquals(emptyList<Any>(), database.vitalDao().observeVitalsForCase("42").first())
        val conflict = database.syncConflictDao().observeConflicts().first().single()
        assertEquals(PendingWriteTypes.VITALS_CREATE, conflict.writeType)
        assertEquals("42", conflict.caseId)
        assertEquals(null, conflict.taskId)
        assertEquals("Vitals were already updated on the server.", conflict.message)
    }

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
        categories: List<String>?,
        subcategories: List<String>?,
        query: String?,
        page: Int?,
    ): CaseListResponseDto {
        lastListCasesAssignedTo = assignedTo
        return caseListResponse
    }

    override suspend fun caseDetail(caseId: String): CaseDetailDto = unused()
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
