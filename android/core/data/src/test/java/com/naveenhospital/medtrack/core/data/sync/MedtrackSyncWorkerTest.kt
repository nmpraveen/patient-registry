package com.naveenhospital.medtrack.core.data.sync

import androidx.room.Room
import androidx.test.core.app.ApplicationProvider
import com.naveenhospital.medtrack.core.data.local.MedtrackDatabase
import com.naveenhospital.medtrack.core.data.local.PendingWriteEntity
import com.naveenhospital.medtrack.core.data.local.VitalEntity
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
import com.naveenhospital.medtrack.core.network.model.CategoriesResponseDto
import com.naveenhospital.medtrack.core.network.model.ClientWriteRequestDto
import com.naveenhospital.medtrack.core.network.model.LogCallRequestDto
import com.naveenhospital.medtrack.core.network.model.LoginRequestDto
import com.naveenhospital.medtrack.core.network.model.NotificationsResponseDto
import com.naveenhospital.medtrack.core.network.model.RefreshTokenRequestDto
import com.naveenhospital.medtrack.core.network.model.RegisterPushTokenRequestDto
import com.naveenhospital.medtrack.core.network.model.TaskDto
import com.naveenhospital.medtrack.core.network.model.TaskWriteResponseDto
import com.naveenhospital.medtrack.core.network.model.UserProfileDto
import com.naveenhospital.medtrack.core.network.model.VitalDto
import com.naveenhospital.medtrack.core.network.model.VitalsRequestDto
import com.naveenhospital.medtrack.core.network.model.VitalsThresholdsDto
import com.naveenhospital.medtrack.core.network.model.VitalsWriteResponseDto
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.test.runTest
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.ResponseBody.Companion.toResponseBody
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import retrofit2.HttpException
import retrofit2.Response
import org.robolectric.RobolectricTestRunner

@RunWith(RobolectricTestRunner::class)
class MedtrackSyncWorkerTest {
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
    fun queuedTaskComplete409RecordsConflictAndRefreshesServerCase() = runTest {
        val api = FakeSyncApi(completeTaskError = conflictError("Task already changed on the server."))
        database.pendingWriteDao().upsertPendingWrite(
            pendingWrite(
                clientWriteId = "task-write-1",
                writeType = PendingWriteTypes.TASK_COMPLETE,
                caseId = "42",
                taskId = "7",
                payloadJson = PendingWriteJson.encodeTaskComplete(ClientWriteRequestDto("task-write-1")),
            ),
        )

        val canContinue = drainPendingWritesForSync(api = api, database = database)

        assertTrue(canContinue)
        assertTrue(database.pendingWriteDao().pendingWrites().isEmpty())
        val conflict = database.syncConflictDao().observeConflicts().first().single()
        assertEquals("task-write-1", conflict.clientWriteId)
        assertEquals(PendingWriteTypes.TASK_COMPLETE, conflict.writeType)
        assertEquals("42", conflict.caseId)
        assertEquals("7", conflict.taskId)
        assertEquals("Task already changed on the server.", conflict.message)
        assertServerVersionRefreshed()
    }

    @Test
    fun queuedCallOutcome409RecordsConflictAndRefreshesServerCase() = runTest {
        val api = FakeSyncApi(logCallError = conflictError("Call log belongs to the server version."))
        database.pendingWriteDao().upsertPendingWrite(
            pendingWrite(
                clientWriteId = "call-write-1",
                writeType = PendingWriteTypes.CALL_OUTCOME,
                caseId = "42",
                taskId = "7",
                payloadJson = PendingWriteJson.encodeCallOutcome(
                    LogCallRequestDto(
                        outcome = "no-answer",
                        note = "Dialer returned",
                        taskId = 7,
                        attemptedAt = "2026-05-18T11:11:36Z",
                        clientWriteId = "call-write-1",
                    ),
                ),
            ),
        )

        val canContinue = drainPendingWritesForSync(api = api, database = database)

        assertTrue(canContinue)
        assertTrue(database.pendingWriteDao().pendingWrites().isEmpty())
        val conflict = database.syncConflictDao().observeConflicts().first().single()
        assertEquals(PendingWriteTypes.CALL_OUTCOME, conflict.writeType)
        assertEquals("42", conflict.caseId)
        assertEquals("7", conflict.taskId)
        assertEquals("Call log belongs to the server version.", conflict.message)
        assertServerVersionRefreshed()
    }

    @Test
    fun queuedVitals409RecordsConflictAndRemovesPendingVitalAfterServerRefresh() = runTest {
        val api = FakeSyncApi(addVitalsError = conflictError("Vitals already updated on the server."))
        database.vitalDao().upsertVital(
            VitalEntity(
                id = "pending-vitals-write-1",
                caseId = "42",
                recordedAt = "2026-05-18T11:11:36Z",
                bpSystolic = 121,
                bpDiastolic = 79,
                pulse = 82,
                spo2 = 97,
                weightKg = null,
                hemoglobin = null,
                summary = "Pending local vital",
                updatedAtMillis = 1L,
            ),
        )
        database.pendingWriteDao().upsertPendingWrite(
            pendingWrite(
                clientWriteId = "vitals-write-1",
                writeType = PendingWriteTypes.VITALS_CREATE,
                caseId = "42",
                payloadJson = PendingWriteJson.encodeVitals(
                    VitalsRequestDto(
                        clientWriteId = "vitals-write-1",
                        bpSystolic = 121,
                        bpDiastolic = 79,
                        pr = 82,
                        spo2 = 97,
                    ),
                ),
            ),
        )

        val canContinue = drainPendingWritesForSync(api = api, database = database)

        assertTrue(canContinue)
        assertTrue(database.pendingWriteDao().pendingWrites().isEmpty())
        val conflict = database.syncConflictDao().observeConflicts().first().single()
        assertEquals(PendingWriteTypes.VITALS_CREATE, conflict.writeType)
        assertEquals("42", conflict.caseId)
        assertEquals(null, conflict.taskId)
        assertEquals("Vitals already updated on the server.", conflict.message)
        val vitals = database.vitalDao().observeVitalsForCase("42").first()
        assertFalse(vitals.any { it.id == "pending-vitals-write-1" })
        assertEquals("200", vitals.single().id)
        assertEquals("PR 76 | SpO2 98", vitals.single().summary)
    }

    private suspend fun assertServerVersionRefreshed() {
        val case = database.caseDao().caseById("42")
        assertEquals("Server Patient", case?.patientName)
        val tasks = database.taskDao().observeTasksForCase("42").first()
        assertEquals("Server review", tasks.single().title)
        val vitals = database.vitalDao().observeVitalsForCase("42").first()
        assertEquals("PR 76 | SpO2 98", vitals.single().summary)
    }

    private fun pendingWrite(
        clientWriteId: String,
        writeType: String,
        caseId: String? = "42",
        taskId: String? = null,
        payloadJson: String,
    ): PendingWriteEntity =
        PendingWriteEntity(
            clientWriteId = clientWriteId,
            writeType = writeType,
            caseId = caseId,
            taskId = taskId,
            payloadJson = payloadJson,
            retryCount = 0,
            lastError = null,
            createdAtMillis = 1L,
            updatedAtMillis = 1L,
        )

    private fun conflictError(message: String): HttpException =
        HttpException(
            Response.error<Any>(
                409,
                message.toResponseBody("text/plain".toMediaType()),
            ),
        )
}

private class FakeSyncApi(
    private val completeTaskError: Throwable? = null,
    private val logCallError: Throwable? = null,
    private val addVitalsError: Throwable? = null,
) : MedtrackApi {
    override suspend fun completeTask(taskId: String, request: ClientWriteRequestDto): TaskWriteResponseDto {
        completeTaskError?.let { throw it }
        return TaskWriteResponseDto("Task completed.", sampleTask(taskId.toLong()), sampleCase())
    }

    override suspend fun logCall(caseId: String, request: LogCallRequestDto): CallWriteResponseDto {
        logCallError?.let { throw it }
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
            case = sampleCase(),
        )
    }

    override suspend fun addVitals(caseId: String, request: VitalsRequestDto): VitalsWriteResponseDto {
        addVitalsError?.let { throw it }
        return VitalsWriteResponseDto("Vitals recorded.", 200, sampleVital(), sampleCase())
    }

    override suspend fun caseDetail(caseId: String): CaseDetailDto =
        CaseDetailDto(
            case = sampleCase(),
            tasks = listOf(sampleTask(700)),
            vitals = listOf(sampleVital()),
        )

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
    ): CaseListResponseDto = unused()
    override suspend fun vitalsThresholds(): VitalsThresholdsDto = unused()
    override suspend fun notifications(type: String?, unreadOnly: Boolean?, page: Int?): NotificationsResponseDto = unused()
    override suspend fun markNotificationRead(notificationId: String): ApiMessageDto = unused()
    override suspend fun registerPushToken(request: RegisterPushTokenRequestDto): ApiMessageDto = unused()
    override suspend fun categories(): CategoriesResponseDto = unused()
    override suspend fun createCase(request: com.naveenhospital.medtrack.core.network.model.CreateCaseRequestDto): com.naveenhospital.medtrack.core.network.model.CaseCreateResponseDto = unused()
    override suspend fun searchPatients(query: String?, page: Int?): com.naveenhospital.medtrack.core.network.model.PatientSearchResponseDto = unused()
    override suspend fun caseFormMetadata(): com.naveenhospital.medtrack.core.network.model.CaseFormMetadataDto = unused()

    private fun unused(): Nothing = error("Not used by this test")

    private fun sampleCase(): CaseSummaryDto =
        CaseSummaryDto(
            id = 42,
            uhid = "UH-SERVER-42",
            name = "Server Patient",
            age = 30,
            sex = "F",
            sexLabel = "Female",
            place = "Server Village",
            phoneNumber = "9876543210",
            category = CaseCategoryDto(id = 1, name = "ANC"),
            subcategory = null,
            status = "ACTIVE",
            diagnosis = "Server diagnosis",
            redFlag = false,
            redFlagReasons = emptyList(),
            nextTask = null,
            latestVital = null,
        )

    private fun sampleTask(id: Long): TaskDto =
        TaskDto(
            id = id,
            title = "Server review",
            dueDate = "2026-05-19",
            status = "SCHEDULED",
            statusLabel = "Scheduled",
            canComplete = true,
        )

    private fun sampleVital(): VitalDto =
        VitalDto(
            id = 200,
            recordedAt = "2026-05-18T12:00:00Z",
            bpSystolic = null,
            bpDiastolic = null,
            pr = 76,
            spo2 = 98,
            weightKg = null,
            hemoglobin = null,
        )
}
