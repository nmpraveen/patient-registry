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
import com.naveenhospital.medtrack.core.data.sync.SyncRecoveryJson
import com.naveenhospital.medtrack.core.data.sync.SyncResolutionStates
import com.naveenhospital.medtrack.core.domain.model.CaseCategory
import com.naveenhospital.medtrack.core.domain.model.NewCaseInput
import com.naveenhospital.medtrack.core.domain.model.NotificationPayload
import com.naveenhospital.medtrack.core.network.api.MedtrackApi
import com.naveenhospital.medtrack.core.network.model.ApiMessageDto
import com.naveenhospital.medtrack.core.network.model.AuthSessionDto
import com.naveenhospital.medtrack.core.network.model.CallLogDto
import com.naveenhospital.medtrack.core.network.model.CallWriteResponseDto
import com.naveenhospital.medtrack.core.network.model.CaseCategoryDto
import com.naveenhospital.medtrack.core.network.model.CaseDetailDto
import com.naveenhospital.medtrack.core.network.model.CaseEditCaseDto
import com.naveenhospital.medtrack.core.network.model.CaseListResponseDto
import com.naveenhospital.medtrack.core.network.model.CaseSearchRequestDto
import com.naveenhospital.medtrack.core.network.model.CaseSearchResponseDto
import com.naveenhospital.medtrack.core.network.model.CaseStatsDto
import com.naveenhospital.medtrack.core.network.model.CaseSummaryDto
import com.naveenhospital.medtrack.core.network.model.CaseSubcategoryDto
import com.naveenhospital.medtrack.core.network.model.CategoriesResponseDto
import com.naveenhospital.medtrack.core.network.model.ClientWriteRequestDto
import com.naveenhospital.medtrack.core.network.model.LogCallRequestDto
import com.naveenhospital.medtrack.core.network.model.LoginRequestDto
import com.naveenhospital.medtrack.core.network.model.NotificationDto
import com.naveenhospital.medtrack.core.network.model.NotificationsResponseDto
import com.naveenhospital.medtrack.core.network.model.PatientLookupDto
import com.naveenhospital.medtrack.core.network.model.PatientSearchRequestDto
import com.naveenhospital.medtrack.core.network.model.PatientSearchResponseDto
import com.naveenhospital.medtrack.core.network.model.PatchField
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
import org.junit.Assert.assertFalse
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
    fun lateListRefreshPreservesLatestDetailHistoryEvenOutsideFilteredPage() = runTest {
        for (retainedInPage in listOf(true, false)) {
            val entered = CompletableDeferred<Unit>()
            val release = CompletableDeferred<Unit>()
            val detail = FakeMedtrackApi(beforeCaseDetail = {}).caseDetail("42")
            val api = FakeMedtrackApi(
                beforeListCases = { entered.complete(Unit); release.await() },
                caseListResponse = CaseListResponseDto(
                    count = if (retainedInPage) 1 else 0, next = null, previous = null,
                    stats = CaseStatsDto(today = 1, upcoming = 0, overdue = 0, awaiting = 0, red = 0),
                    results = if (retainedInPage) listOf(detail.case) else emptyList(),
                ),
            )
            val repository = repository(api)
            val listRefresh = async { repository.refreshCases(bucket = "today") }
            entered.await()
            api.detailResponse = detail.copy(callLogs = listOf(CallLogDto(
                id = 91L, taskId = null, reason = "Latest authoritative receipt", outcome = "REACHED",
                outcomeLabel = "Reached", notes = "", createdAt = "2026-09-07T00:00:00Z",
            )))
            repository.refreshCaseDetail("42")
            assertEquals(listOf(91L), repository.observeCallLogs("42").first().map { it.id })
            release.complete(Unit)
            listRefresh.await()
            assertEquals(listOf(91L), repository.observeCallLogs("42").first().map { it.id })
            assertEquals(retainedInPage, repository.observeCase("42").first() != null)
        }
    }

    @Test
    fun identityRefreshFollowsMergeAndUndoWithoutChangingCaseKey() = runTest {
        val api = FakeMedtrackApi(beforeCaseDetail = {})
        val initial = api.caseDetail("42")
        val repository = repository(api)
        for (mtno in listOf("MT-000042", "MT-000099", "MT-000042")) {
            api.detailResponse = initial.copy(case = initial.case.copy(mtno = mtno, uhid = ""))
            repository.refreshCaseDetail("42")
            val cached = database.caseDao().caseById(ACCOUNT_ID, "42")!!
            assertEquals(mtno, cached.mtno)
            assertEquals("", cached.uhid)
            assertEquals(mtno, repository.observeCase("42").first()!!.mtno)
            assertNull(database.caseDao().caseById("other", "42"))
        }
    }

    @Test
    fun invalidCursorResetStillPurgesOwnerHistory() = runTest {
        val detail = FakeMedtrackApi(beforeCaseDetail = {}).caseDetail("42")
        val api = FakeMedtrackApi(
            beforeSearchCases = { request ->
                if (request.cursor != null) throw HttpException(Response.error<Any>(400,
                    "{\"code\":\"invalid_cursor\"}".toResponseBody()))
            },
            caseSearchResponses = mapOf(null to CaseSearchResponseDto(
                nextCursor = "expired", results = listOf(detail.case),
                stats = CaseStatsDto(today = 1, upcoming = 0, overdue = 0, awaiting = 0, red = 0),
            )),
        )
        val repository = repository(api)
        repository.refreshCases(query = "Test")
        repository.logCallOutcome("42", null, "reached", null, reason = "Appointment")
        assertEquals(1, repository.observeCallLogs("42").first().size)
        repository.loadNextCases(query = "Test")
        assertTrue(repository.observeCallLogs("42").first().isEmpty())
        assertEquals(listOf(null, "expired", null), api.caseSearchRequests.map { it.cursor })
    }

    @Test
    fun addingUhidUsesOnlyOriginalUhidBaselineAndNeverMtno() {
        val baseline = CaseEditCaseDto(mtno = "MT-000042", id = 42, baseUpdatedAt = "v1", patientMode = "new", category = 2, uhid = "", surgeryDone = false)
        val input = NewCaseInput(patientMode = "new", categoryId = 2, categoryName = "Medicine", uhid = "UH-NEW", surgeryDone = false)
        val request = input.toUpdateRequestDto("identity-edit", baseline)
        assertEquals(PatchField.Value("UH-NEW"), request.uhid)
        assertEquals(mapOf("uhid" to ""), request.baseValues)
        val encoded = com.naveenhospital.medtrack.core.network.api.MedtrackNetwork.contractMoshi()
            .adapter(com.naveenhospital.medtrack.core.network.model.UpdateCaseRequestDto::class.java).toJson(request)
        assertFalse(encoded.contains("mtno"))
        assertEquals(PatchField.Omitted, request.useTemporaryUhid)
    }

    @Test
    fun taskPatchUsesEditorSnapshotAfterRefreshAndRetainsConflictDraft() = runTest {
        val api = FakeMedtrackApi(beforeCaseDetail = {})
        val initial = api.caseDetail("42")
        api.detailResponse = initial.copy(tasks = initial.tasks.map { it.copy(notes = "Original", frequencyLabel = "Monthly") })
        val repository = repository(api)
        repository.refreshCaseDetail("42")
        val snapshot = repository.observeTasks("42").first().single()
        api.detailResponse = initial.copy(tasks = initial.tasks.map { it.copy(notes = "Other editor", frequencyLabel = "Weekly", updatedAt = "2026-09-08T00:00:00Z") })
        repository.refreshCaseDetail("42")
        api.patchError = conflictError("Overlapping edit")
        val draft = com.naveenhospital.medtrack.core.domain.model.TaskEditInput(baseline = snapshot, notes = "", frequencyLabel = "Daily")
        val result = repository.updateTask(snapshot.id, "42", draft)
        assertTrue(result is com.naveenhospital.medtrack.core.domain.model.TaskWriteOutcome.Failure)
        assertEquals(snapshot.serverUpdatedAt, api.lastTaskPatch!!.baseUpdatedAt)
        assertEquals(mapOf("notes" to "Original", "frequency_label" to "Monthly"), api.lastTaskPatch!!.baseValues)
        assertEquals(PatchField.Value(""), api.lastTaskPatch!!.notes)
        assertEquals(PatchField.Omitted, api.lastTaskPatch!!.dueDate)
        assertEquals("Other editor", database.taskDao().taskById(ACCOUNT_ID, "7")!!.notes)
        assertEquals("", draft.notes)
        val foreign = snapshot.copy(ownerAccountId = "other")
        api.lastTaskPatch = null
        repository.updateTask(snapshot.id, "42", draft.copy(baseline = foreign))
        assertNull(api.lastTaskPatch)
    }

    @Test
    fun invalidGeneralCallsNeverSendOrQueueAndValidReasonSurvivesOffline() = runTest {
        val api = FakeMedtrackApi(logCallError = IOException("offline"))
        val repository = repository(api)
        for (reason in listOf(null, "", "  ", "x".repeat(501))) {
            assertTrue(runCatching { repository.logCallOutcome("42", null, "attempted", null, reason = reason) }.exceptionOrNull() is IllegalArgumentException)
        }
        assertTrue(runCatching { repository.logCallOutcome("42", "invalid", "reached", null, reason = "Test") }.exceptionOrNull() is IllegalArgumentException)
        assertTrue(database.pendingWriteDao().pendingWrites(ACCOUNT_ID).isEmpty())
        val result = repository.logCallOutcome("42", null, "attempted", "Note", "2026-09-07T00:00:00Z", "  Appointment  ")
        assertTrue(result.queued)
        val pending = database.pendingWriteDao().pendingWrites(ACCOUNT_ID).single()
        val payload = PendingWriteJson.decodeCallOutcome(pending.payloadJson)
        assertEquals("Appointment", payload.reason)
        assertNull(payload.taskId)
        assertEquals(result.clientWriteId, payload.clientWriteId)
        assertTrue(repository.observeCallLogs("42").first().isEmpty())
    }

    @Test
    fun boundedCallHistoryReplacesAndAccountInvalidationPurges() = runTest {
        val api = FakeMedtrackApi(beforeCaseDetail = {})
        val base = api.caseDetail("42")
        val calls = (30L downTo 1L).map { id -> CallLogDto(id = id, taskId = null, reason = "Reason $id", outcome = "REACHED", outcomeLabel = "Reached", notes = "", createdAt = "2026-09-07T00:00:00Z") }
        api.detailResponse = base.copy(callLogs = calls)
        val repository = repository(api)
        repository.refreshCaseDetail("42")
        assertEquals((30L downTo 11L).toList(), repository.observeCallLogs("42").first().map { it.id })
        api.detailResponse = base.copy(callLogs = calls.take(2))
        repository.refreshCaseDetail("42")
        assertEquals(2, repository.observeCallLogs("42").first().size)
        repository.logCallOutcome("42", null, "reached", null, reason = "Appointment")
        repository.logCallOutcome("42", null, "reached", null, reason = "Appointment")
        assertEquals(3, repository.observeCallLogs("42").first().size)
        assertTrue(database.callLogDao().observeForCase("other", "42").first().isEmpty())
        database.invalidateAndClearAccountData(ACCOUNT_ID)
        assertTrue(database.callLogDao().observeForCase(ACCOUNT_ID, "42").first().isEmpty())
    }

    @Test
    fun caseScopeLossClearsPreviouslyCachedCalls() = runTest {
        var revoked = false
        val api = FakeMedtrackApi(beforeCaseDetail = { if (revoked) throw HttpException(Response.error<Any>(403, "{}".toResponseBody())) })
        val repository = repository(api)
        repository.logCallOutcome("42", null, "reached", null, reason = "Appointment")
        assertEquals(1, repository.observeCallLogs("42").first().size)
        revoked = true
        assertTrue(runCatching { repository.refreshCaseDetail("42") }.isFailure)
        assertTrue(repository.observeCallLogs("42").first().isEmpty())
    }

    @Test
    fun revokedAccountRejectsLateCallCacheCommit() = runTest {
        val entered = CompletableDeferred<Unit>()
        val release = CompletableDeferred<Unit>()
        val api = FakeMedtrackApi(beforeLogCall = { entered.complete(Unit); release.await() })
        val repository = repository(api)
        val pending = async { runCatching { repository.logCallOutcome("42", null, "reached", null, reason = "Appointment") } }
        entered.await()
        database.invalidateAndClearAccountData(ACCOUNT_ID)
        release.complete(Unit)
        assertTrue(pending.await().isFailure)
        assertTrue(database.callLogDao().observeForCase(ACCOUNT_ID, "42").first().isEmpty())
    }

    @Test
    fun ancCancellationWaitsForAuthoritativeDetailBeforeReturning() = runTest {
        val entered = CompletableDeferred<Unit>()
        val release = CompletableDeferred<Unit>()
        val api = FakeMedtrackApi(beforeCaseDetail = { entered.complete(Unit); release.await() })
        val repository = repository(api)
        database.taskDao().upsertTask(TaskEntity(ownerAccountId = ACCOUNT_ID, id = "7", caseId = "42",
            title = "Original", dueDate = "2026-09-01", status = "SCHEDULED", statusLabel = "Scheduled",
            canComplete = true, updatedAtMillis = 1L))
        val result = async { repository.recordAncAction("42", mapOf("task_policy" to "cancel_selected",
            "cancel_task_ids" to listOf(7L))) }
        entered.await()
        assertFalse(result.isCompleted)
        assertEquals(false, database.taskDao().taskById(ACCOUNT_ID, "7")?.canComplete)
        release.complete(Unit)
        assertEquals("ANC action recorded.", result.await())
        assertEquals("CANCELLED", database.taskDao().taskById(ACCOUNT_ID, "7")?.status)
        assertEquals("Authoritative cancellation", database.taskDao().taskById(ACCOUNT_ID, "7")?.title)
    }

    @Test
    fun ancCancellationFailedRefreshCannotLeaveCancelledTasksActionable() = runTest {
        val repository = repository(FakeMedtrackApi(beforeCaseDetail = { throw IOException("offline") }))
        for (id in listOf("7", "8")) {
            database.taskDao().upsertTask(TaskEntity(ownerAccountId = ACCOUNT_ID, id = id, caseId = "42",
                title = "Original", dueDate = "2026-09-01", status = "SCHEDULED", statusLabel = "Scheduled",
                canComplete = true, updatedAtMillis = 1L))
        }
        val failure = runCatching { repository.recordAncAction("42", mapOf("task_policy" to "cancel_selected",
            "cancel_task_ids" to listOf(7L))) }.exceptionOrNull()
        assertTrue(failure is IOException)
        assertEquals("CANCELLED", database.taskDao().taskById(ACCOUNT_ID, "7")?.status)
        assertEquals(false, database.taskDao().taskById(ACCOUNT_ID, "7")?.canComplete)
        assertEquals("SCHEDULED", database.taskDao().taskById(ACCOUNT_ID, "8")?.status)
        assertEquals(true, database.taskDao().taskById(ACCOUNT_ID, "8")?.canComplete)
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
    fun ancSuccessRefreshesActiveBucketMembershipCountersAndEveryFilter() = runTest {
        for (query in listOf(null, "  SYNTH  ")) {
            val detailEntered = CompletableDeferred<Unit>()
            val releaseDetail = CompletableDeferred<Unit>()
            val api = FakeMedtrackApi(
                beforeCaseDetail = { detailEntered.complete(Unit); releaseDetail.await() },
                caseListResponse = CaseListResponseDto(count = 0, next = null, previous = null,
                    stats = CaseStatsDto(today = 0, upcoming = 0, overdue = 0, awaiting = 0, red = 0, dormant = 1),
                    results = emptyList()),
            )
            val repository = repository(api)
            repository.pagedCases(bucket = "overdue", query = query, assignedTo = "me", scopeContext = "calls",
                categories = listOf("ANC"), subcategories = listOf("anc_high_risk"))
            val result = async {
                val message = repository.recordAncAction("42", mapOf("outcome" to "referral",
                    "continue_follow_up" to "continue", "task_policy" to "retain"))
                assertNotNull(repository.observeCase("42").first())
                repository.refreshActiveCaseList()
                message
            }
            detailEntered.await()
            assertFalse(result.isCompleted)
            assertEquals(0, api.listCasesCalls)
            assertTrue(api.caseSearchRequests.isEmpty())
            releaseDetail.complete(Unit)
            assertEquals("ANC action recorded.", result.await())
            assertTrue(repository.cases.first().isEmpty())
            assertEquals(0, repository.stats.value.overdue)
            assertEquals(1, repository.stats.value.dormant)
            if (query == null) {
                assertEquals(1, api.listCasesCalls)
                assertEquals("overdue", api.lastListCasesBucket)
                assertEquals("me", api.lastListCasesAssignedTo)
                assertEquals("calls", api.lastListCasesScopeContext)
                assertEquals(listOf("ANC"), api.lastListCasesCategories)
                assertEquals(listOf("anc_high_risk"), api.lastListCasesSubcategories)
            } else {
                val request = api.caseSearchRequests.single()
                assertEquals("SYNTH", request.query)
                assertEquals("overdue", request.bucket)
                assertEquals("me", request.assignedTo)
                assertEquals("calls", request.scopeContext)
                assertEquals(listOf("ANC"), request.category)
                assertEquals(listOf("anc_high_risk"), request.subcategory)
            }
        }
    }

    @Test
    fun ancClosureRefreshesUnpagedWorklistAndAccountResetDropsOldFilters() = runTest {
        val api = FakeMedtrackApi(beforeCaseDetail = {})
        val repository = repository(api)
        repository.refreshCases(bucket = "all", assignedTo = "all")
        repository.recordAncAction("42", mapOf("outcome" to "delivery", "continue_follow_up" to "close",
            "task_policy" to "cancel_selected", "cancel_task_ids" to listOf(7L)))
        assertNotNull(repository.observeCase("42").first())
        repository.refreshActiveCaseList()
        assertEquals(2, api.listCasesCalls)
        assertEquals("all", api.lastListCasesBucket)
        assertEquals("all", api.lastListCasesAssignedTo)
        assertTrue(repository.cases.first().isEmpty())
        assertEquals(0, repository.stats.value.overdue)
        assertEquals(0, repository.stats.value.dormant)
        repository.deactivateAccount()
        repository.activateAccount("other-account")
        repository.refreshActiveCaseList()
        assertEquals(2, api.listCasesCalls)
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
    fun caseSearchRetainsOpaqueCursorAndEveryBoundFilterAcrossPages() = runTest {
        val stats = CaseStatsDto(today = 1, upcoming = 2, overdue = 3, awaiting = 4, red = 5)
        val api = FakeMedtrackApi(
            caseSearchResponses = mapOf(
                null to CaseSearchResponseDto(nextCursor = "opaque-case-page-two", stats = stats),
                "opaque-case-page-two" to CaseSearchResponseDto(nextCursor = null, stats = stats),
            ),
        )
        val repository = repository(api)

        repository.refreshCases(
            bucket = "overdue",
            query = "  TEST-00  ",
            assignedTo = "me",
            scopeContext = "calls",
            categories = listOf("Surgery"),
            subcategories = listOf("Review"),
        )
        repository.loadNextCases(
            bucket = "overdue",
            query = "  TEST-00  ",
            assignedTo = "me",
            scopeContext = "calls",
            categories = listOf("Surgery"),
            subcategories = listOf("Review"),
        )

        assertEquals(listOf(null, "opaque-case-page-two"), api.caseSearchRequests.map { it.cursor })
        assertTrue(api.caseSearchRequests.all { request ->
            request.query == "TEST-00" && request.pageSize == 20 &&
                request.bucket == "overdue" && request.assignedTo == "me" &&
                request.scopeContext == "calls" && request.category == listOf("Surgery") &&
                request.subcategory == listOf("Review")
        })
        assertEquals(false, repository.hasMoreCases.value)
    }

    @Test
    fun patientSearchTraversesEveryOpaqueCursorAndDeduplicatesByPatientId() = runTest {
        val api = FakeMedtrackApi(
            patientSearchResponses = mapOf(
                null to PatientSearchResponseDto(
                    nextCursor = "opaque-page-two",
                    results = listOf(PatientLookupDto(id = 1, uhid = "UH-001", name = "First")),
                ),
                "opaque-page-two" to PatientSearchResponseDto(
                    nextCursor = null,
                    results = listOf(
                        PatientLookupDto(id = 1, uhid = "UH-001", name = "First"),
                        PatientLookupDto(id = 2, mtno = "MT-000002", uhid = "", name = "Second"),
                    ),
                ),
            ),
        )
        val repository = repository(api)

        val results = repository.searchPatients("  UH-0  ")

        assertEquals(listOf(1L, 2L), results.map { it.id })
        assertEquals("MT-000002", results.last().mtno)
        assertEquals("", results.last().uhid)
        assertEquals(listOf(null, "opaque-page-two"), api.patientSearchRequests.map { it.cursor })
        assertTrue(api.patientSearchRequests.all { it.query == "UH-0" && it.pageSize == 20 })
    }

    @Test
    fun refreshNotificationsPreservesPayloadJsonAndParsedDomainPayload() = runTest {
        val api = FakeMedtrackApi(
            notificationsResponse = NotificationsResponseDto(
                datasetEpoch = "11111111-1111-4111-8111-111111111111",
                nextCursor = null,
                results = listOf(
                    NotificationDto(
                        id = 5543,
                        eventId = "event-red-5543",
                        type = "red_flag",
                        title = "MEDTRACK update",
                        body = "Open MEDTRACK to review this update.",
                        caseId = 6364,
                        taskId = null,
                        payload = mapOf("channel" to "red_flags", "type" to "red_flag"),
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
        assertEquals("event-red-5543", storedJson.getString("event_id"))
        val item = repository.notifications.first().single()
        assertEquals(NotificationPayload.RedFlag(emptyList()), item.payload)
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
        assertEquals(mapOf("status" to "PENDING", "due_date" to "2026-05-18"), PendingWriteJson.decodeTaskComplete(pending.payloadJson).baseValues)
        val localTask = database.taskDao().observeTasksForCase(ACCOUNT_ID, "42").first().single()
        assertEquals("COMPLETED", localTask.status)
        assertEquals(false, localTask.canComplete)
    }

    @Test
    fun completeTaskRecordsConflictWhenServerReturns409() = runTest {
        val api = FakeMedtrackApi(beforeCaseDetail = {}, completeTaskError = conflictError("Task was already changed on the server."))
        var queuedCallbacks = 0
        val repository = repository(
            api = api,
            onPendingWriteQueued = { queuedCallbacks += 1 },
        )

        val result = repository.completeTask(taskId = "7", caseId = "42")

        assertEquals(false, result.queued)
        assertTrue(result.conflict)
        assertEquals(emptyList<Any>(), database.pendingWriteDao().pendingWrites(ACCOUNT_ID))
        val conflict = database.syncConflictDao().observeConflicts(ACCOUNT_ID).first().single()
        assertEquals(PendingWriteTypes.TASK_COMPLETE, conflict.writeType)
        assertEquals("42", conflict.caseId)
        assertEquals("7", conflict.taskId)
        assertEquals("Task was already changed on the server.", conflict.message)
        val recovery = SyncRecoveryJson.decode(conflict.serverPayloadJson)
        assertNotNull(recovery?.localPayloadJson)
        assertEquals("Task was already changed on the server.", recovery?.serverPayloadJson)

        repository.retrySyncConflict(result.clientWriteId)

        assertEquals(1, queuedCallbacks)
        val replacementWrite = database.pendingWriteDao().pendingWrites(ACCOUNT_ID).single()
        assertTrue(result.clientWriteId != replacementWrite.clientWriteId)
        assertEquals(
            replacementWrite.clientWriteId,
            PendingWriteJson.decodeTaskComplete(replacementWrite.payloadJson).clientWriteId,
        )
        assertTrue(repository.syncConflicts.first().isEmpty())
        assertEquals(
            SyncResolutionStates.RETRY_QUEUED,
            SyncRecoveryJson.decode(
                database.syncConflictDao().conflictById(ACCOUNT_ID, result.clientWriteId)?.serverPayloadJson,
            )?.resolutionState,
        )
        assertEquals(
            replacementWrite.clientWriteId,
            SyncRecoveryJson.decode(
                database.syncConflictDao().conflictById(ACCOUNT_ID, result.clientWriteId)?.serverPayloadJson,
            )?.replacementClientWriteId,
        )
    }

    @Test
    fun casePatchContainsOnlyUserChangedFieldsAndPreservesSurgeryDone() {
        val baseline = CaseEditCaseDto(
            id = 42,
            baseUpdatedAt = "2026-08-29T18:00:00Z",
            patientMode = "existing",
            category = 2,
            diagnosis = "Original diagnosis",
            notes = "Clear this note",
            highRisk = true,
            surgeryDone = true,
        )
        val input = NewCaseInput(
            patientMode = "existing",
            categoryId = 2,
            categoryName = "Surgery",
            diagnosis = "Updated diagnosis",
            highRisk = true,
            surgeryDone = true,
        )

        val request = input.toUpdateRequestDto("case-edit-test", baseline)

        assertEquals(PatchField.Value("Updated diagnosis"), request.diagnosis)
        assertEquals("2026-08-29T18:00:00Z", request.baseUpdatedAt)
        assertEquals(mapOf("diagnosis" to "Original diagnosis", "notes" to "Clear this note"), request.baseValues)
        assertEquals(PatchField.Value("case-edit-test"), request.clientWriteId)
        assertEquals(PatchField.Omitted, request.surgeryDone)
        assertEquals(PatchField.Omitted, request.highRisk)
        assertEquals(PatchField.Omitted, request.category)
        assertEquals(PatchField.Omitted, request.patientMode)
        assertEquals(PatchField.Omitted, request.useTemporaryUhid)
        assertEquals(PatchField.Omitted, request.ncdFlags)
        assertEquals(PatchField.Omitted, request.phoneNumber)
        assertEquals(PatchField.Value(null), request.notes)
    }

    @Test
    fun discardSyncIssueKeepsLocalResolutionEvidence() = runTest {
        val api = FakeMedtrackApi(addVitalsError = conflictError("Vitals conflict."))
        val repository = repository(api)
        val result = repository.addVitals(
            caseId = "42",
            bpSystolic = 120,
            bpDiastolic = 80,
            pulse = null,
            spo2 = null,
            weightKg = null,
            hemoglobin = null,
        )

        repository.discardSyncConflict(result.clientWriteId)

        assertTrue(repository.syncConflicts.first().isEmpty())
        val retained = database.syncConflictDao().conflictById(ACCOUNT_ID, result.clientWriteId)
        assertNotNull(retained)
        assertEquals(
            SyncResolutionStates.DISCARDED,
            SyncRecoveryJson.decode(retained?.serverPayloadJson)?.resolutionState,
        )
    }

    @Test
    fun discardSyncIssueRestoresOptimisticTaskFromDurableRollbackPayload() = runTest {
        val originalTask = TaskEntity(
            ownerAccountId = ACCOUNT_ID,
            id = "7",
            caseId = "42",
            title = "Follow-up",
            dueDate = "2026-08-30",
            status = "PENDING",
            statusLabel = "Pending",
            canComplete = true,
            updatedAtMillis = 1L,
        )
        val payloadJson = PendingWriteJson.encodeTaskComplete(
            ClientWriteRequestDto("discard-task"),
            originalTask,
        )
        database.taskDao().upsertTask(
            originalTask.copy(status = "COMPLETED", statusLabel = "Completed", canComplete = false),
        )
        database.syncConflictDao().upsertConflict(
            com.naveenhospital.medtrack.core.data.local.SyncConflictEntity(
                ownerAccountId = ACCOUNT_ID,
                clientWriteId = "discard-task",
                writeType = PendingWriteTypes.TASK_COMPLETE,
                caseId = "42",
                taskId = "7",
                message = "Invalid transition",
                serverPayloadJson = SyncRecoveryJson.encode(
                    com.naveenhospital.medtrack.core.data.sync.SyncRecoveryPayload(
                        failureKind = com.naveenhospital.medtrack.core.data.sync.SyncFailureKinds.VALIDATION,
                        localPayloadJson = payloadJson,
                    ),
                ),
                createdAtMillis = 2L,
            ),
        )
        val repository = repository(FakeMedtrackApi())

        repository.discardSyncConflict("discard-task")

        val restored = database.taskDao().taskById(ACCOUNT_ID, "7")
        assertEquals("PENDING", restored?.status)
        assertEquals(true, restored?.canComplete)
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
    var beforeListCases: (suspend () -> Unit)? = null,
    var beforeSearchCases: (suspend (CaseSearchRequestDto) -> Unit)? = null,
    var detailResponse: CaseDetailDto? = null,
    var patchError: Throwable? = null,
    var beforeLogCall: (suspend () -> Unit)? = null,
    private val beforeCaseDetail: (suspend () -> Unit)? = null,
    private val categoriesResponse: CategoriesResponseDto = CategoriesResponseDto(emptyList()),
    private val caseListResponse: CaseListResponseDto = CaseListResponseDto(
        count = 0,
        next = null,
        previous = null,
        stats = CaseStatsDto(today = 0, upcoming = 0, overdue = 0, awaiting = 0, red = 0),
        results = emptyList(),
    ),
    private val notificationsResponse: NotificationsResponseDto = NotificationsResponseDto(
        datasetEpoch = "11111111-1111-4111-8111-111111111111",
        nextCursor = null,
        results = emptyList(),
    ),
    private val patientSearchResponses: Map<String?, PatientSearchResponseDto> = emptyMap(),
    private val caseSearchResponses: Map<String?, CaseSearchResponseDto> = emptyMap(),
    private val categoriesError: Throwable? = null,
    private val registerPushError: Throwable? = null,
    private val notificationReadError: Throwable? = null,
    private val completeTaskError: Throwable? = null,
    private val logCallError: Throwable? = null,
    private val addVitalsError: Throwable? = null,
) : MedtrackApi {
    var lastTaskPatch: com.naveenhospital.medtrack.core.network.model.UpdateTaskRequestDto? = null
    var lastCompletion: ClientWriteRequestDto? = null
    val patientSearchRequests = mutableListOf<PatientSearchRequestDto>()
    val caseSearchRequests = mutableListOf<CaseSearchRequestDto>()
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
    var listCasesCalls = 0
        private set
    var lastListCasesBucket: String? = null
        private set
    var lastListCasesCategories: List<String>? = null
        private set
    var lastListCasesSubcategories: List<String>? = null
        private set

    override suspend fun categories(): CategoriesResponseDto {
        categoryCalls += 1
        categoriesError?.let { throw it }
        return categoriesResponse
    }

    override suspend fun login(request: LoginRequestDto): retrofit2.Response<com.naveenhospital.medtrack.core.network.model.LoginResponseDto> = unused()
    override suspend fun refresh(request: RefreshTokenRequestDto): AuthSessionDto = unused()
    override suspend fun logout(request: RefreshTokenRequestDto): ApiMessageDto = unused()
    override suspend fun me(): UserProfileDto = unused()
    override suspend fun listCases(
        bucket: String?,
        assignedTo: String?,
        scopeContext: String?,
        categories: List<String>?,
        subcategories: List<String>?,
        page: Int?,
    ): CaseListResponseDto {
        beforeListCases?.invoke()
        listCasesCalls += 1
        lastListCasesBucket = bucket
        lastListCasesAssignedTo = assignedTo
        lastListCasesScopeContext = scopeContext
        lastListCasesCategories = categories
        lastListCasesSubcategories = subcategories
        return caseListResponse
    }

    override suspend fun searchCases(request: CaseSearchRequestDto): CaseSearchResponseDto {
        caseSearchRequests += request
        beforeSearchCases?.invoke(request)
        return caseSearchResponses[request.cursor] ?: CaseSearchResponseDto(
            nextCursor = null,
            stats = caseListResponse.stats,
            results = caseListResponse.results,
        )
    }

    override suspend fun caseDetail(caseId: String): CaseDetailDto {
        beforeCaseDetail?.invoke()
        detailResponse?.let { return it }
        if (beforeCaseDetail == null) unused()
        return CaseDetailDto(case = sampleCaseSummary(), tasks = listOf(sampleTask(7).copy(
            title = "Authoritative cancellation", status = "CANCELLED", statusLabel = "Cancelled", canComplete = false)))
    }
    override suspend fun createCase(request: com.naveenhospital.medtrack.core.network.model.CreateCaseRequestDto): com.naveenhospital.medtrack.core.network.model.CaseCreateResponseDto = unused()
    override suspend fun searchPatients(request: PatientSearchRequestDto): PatientSearchResponseDto {
        patientSearchRequests += request
        return patientSearchResponses[request.cursor] ?: unused()
    }
    override suspend fun caseFormMetadata(): com.naveenhospital.medtrack.core.network.model.CaseFormMetadataDto = unused()
    override suspend fun taskFormMetadata(): com.naveenhospital.medtrack.core.network.model.TaskFormMetadataDto = unused()
    override suspend fun caseEditForm(caseId: String): com.naveenhospital.medtrack.core.network.model.CaseEditFormDto = unused()
    override suspend fun ancAction(caseId: String, request: Map<String, Any>) =
        com.naveenhospital.medtrack.core.network.model.CaseUpdateResponseDto(
            message = "ANC action recorded.", caseId = 42, case = sampleCaseSummary(),
            editableCase = com.naveenhospital.medtrack.core.network.model.CaseEditCaseDto(
                id = 42, baseUpdatedAt = "2026-09-01T00:00:00Z", surgeryDone = false))

    override suspend fun updateCase(caseId: String, request: com.naveenhospital.medtrack.core.network.model.UpdateCaseRequestDto): com.naveenhospital.medtrack.core.network.model.CaseUpdateResponseDto = unused()
    override suspend fun createTask(caseId: String, request: com.naveenhospital.medtrack.core.network.model.CreateTaskRequestDto): TaskWriteResponseDto = unused()
    override suspend fun updateTask(taskId: String, request: com.naveenhospital.medtrack.core.network.model.UpdateTaskRequestDto): TaskWriteResponseDto {
        lastTaskPatch = request
        patchError?.let { throw it }
        return TaskWriteResponseDto("Task saved", sampleTask(taskId.toLong()), sampleCaseSummary())
    }
    override suspend fun addTaskNote(taskId: String, request: com.naveenhospital.medtrack.core.network.model.TaskNoteRequestDto): TaskWriteResponseDto = unused()
    override suspend fun updateVitals(vitalId: String, request: com.naveenhospital.medtrack.core.network.model.VitalsUpdateRequestDto): VitalsWriteResponseDto = unused()
    override suspend fun completeTask(taskId: String, request: ClientWriteRequestDto): TaskWriteResponseDto {
        lastCompletion = request
        completeTaskError?.let { throw it }
        return TaskWriteResponseDto(
            message = "Task completed.",
            task = sampleTask(taskId.toLong()),
            case = sampleCaseSummary(),
        )
    }
    override suspend fun logCall(caseId: String, request: LogCallRequestDto): CallWriteResponseDto {
        beforeLogCall?.invoke()
        logCallError?.let { throw it }
        lastLogCallCaseId = caseId
        lastLogCallRequest = request
        return CallWriteResponseDto(
            message = "Call outcome logged.",
            callLog = CallLogDto(
                id = 1,
                reason = request.reason.orEmpty(),
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
                updatedAt = "2026-08-29T18:00:00Z",
            ),
            case = sampleCaseSummary(),
        )
    }
    override suspend fun vitalsThresholds(): VitalsThresholdsDto = unused()
    override suspend fun notifications(type: String?, unreadOnly: Boolean?, cursor: String?, pageSize: Int?): NotificationsResponseDto =
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
            updatedAt = "2026-08-29T18:00:00Z",
        )
}
