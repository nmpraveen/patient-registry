package com.naveenhospital.medtrack.core.data.sync

import android.content.Context
import android.content.SharedPreferences
import androidx.room.Room
import androidx.test.core.app.ApplicationProvider
import com.naveenhospital.medtrack.core.data.local.MedtrackDatabase
import com.naveenhospital.medtrack.core.data.local.PendingWriteEntity
import com.naveenhospital.medtrack.core.data.local.CacheMetadataEntity
import com.naveenhospital.medtrack.core.data.local.NotificationEntity
import com.naveenhospital.medtrack.core.data.local.PushTokenEntity
import com.naveenhospital.medtrack.core.data.auth.AccountSessionInvalidator
import com.naveenhospital.medtrack.core.data.auth.AccountVisibilityInvalidations
import com.naveenhospital.medtrack.core.data.auth.LockStore
import com.naveenhospital.medtrack.core.data.auth.TokenStore
import com.naveenhospital.medtrack.core.data.repository.MedtrackRepository
import com.naveenhospital.medtrack.core.data.local.TaskEntity
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
import java.io.IOException
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.runBlocking
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.ResponseBody.Companion.toResponseBody
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertNull
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
    private var accountGeneration: Long = 0L
    private lateinit var context: Context
    private lateinit var authPrefs: SharedPreferences
    private lateinit var lockPrefs: SharedPreferences

    @Before
    fun setUp() {
        context = ApplicationProvider.getApplicationContext()
        authPrefs = context.getSharedPreferences("worker_auth_boundary", Context.MODE_PRIVATE)
        lockPrefs = context.getSharedPreferences("worker_lock_boundary", Context.MODE_PRIVATE)
        authPrefs.edit().clear().commit()
        lockPrefs.edit().clear().commit()
        database = Room.inMemoryDatabaseBuilder(
            context,
            MedtrackDatabase::class.java,
        )
            .allowMainThreadQueries()
            .build()
        accountGeneration = runBlocking { database.activateAccount(ACCOUNT_ID) }
    }

    @After
    fun tearDown() {
        database.close()
        authPrefs.edit().clear().commit()
        lockPrefs.edit().clear().commit()
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

        val outcome = drainPendingWritesForSync(
            api = api,
            database = database,
            ownerAccountId = ACCOUNT_ID,
            accountGeneration = accountGeneration,
        )

        assertEquals(SyncRunOutcome.COMPLETED, outcome)
        assertTrue(database.pendingWriteDao().pendingWrites(ACCOUNT_ID).isEmpty())
        val conflict = database.syncConflictDao().observeConflicts(ACCOUNT_ID).first().single()
        assertEquals("task-write-1", conflict.clientWriteId)
        assertEquals(PendingWriteTypes.TASK_COMPLETE, conflict.writeType)
        assertEquals("42", conflict.caseId)
        assertEquals("7", conflict.taskId)
        assertEquals("Task already changed on the server.", conflict.message)
        assertServerVersionRefreshed()
    }

    @Test
    fun postConflictRefresh401PropagatesToAccountInvalidationBoundary() = runTest {
        val unauthorized = authError(401)
        val api = FakeSyncApi(
            completeTaskError = conflictError("Task already changed on the server."),
            caseDetailError = unauthorized,
        )
        database.pendingWriteDao().upsertPendingWrite(
            pendingWrite(
                clientWriteId = "task-write-auth-revoked",
                writeType = PendingWriteTypes.TASK_COMPLETE,
                caseId = "42",
                taskId = "7",
                payloadJson = PendingWriteJson.encodeTaskComplete(
                    ClientWriteRequestDto("task-write-auth-revoked"),
                ),
            ),
        )

        val failure = runCatching {
            drainPendingWritesForSync(
                api = api,
                database = database,
                ownerAccountId = ACCOUNT_ID,
                accountGeneration = accountGeneration,
            )
        }.exceptionOrNull()

        assertTrue(failure is HttpException)
        assertEquals(401, (failure as HttpException).code())
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

        val outcome = drainPendingWritesForSync(
            api = api,
            database = database,
            ownerAccountId = ACCOUNT_ID,
            accountGeneration = accountGeneration,
        )

        assertEquals(SyncRunOutcome.COMPLETED, outcome)
        assertTrue(database.pendingWriteDao().pendingWrites(ACCOUNT_ID).isEmpty())
        val conflict = database.syncConflictDao().observeConflicts(ACCOUNT_ID).first().single()
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
                ownerAccountId = ACCOUNT_ID,
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

        val outcome = drainPendingWritesForSync(
            api = api,
            database = database,
            ownerAccountId = ACCOUNT_ID,
            accountGeneration = accountGeneration,
        )

        assertEquals(SyncRunOutcome.COMPLETED, outcome)
        assertTrue(database.pendingWriteDao().pendingWrites(ACCOUNT_ID).isEmpty())
        val conflict = database.syncConflictDao().observeConflicts(ACCOUNT_ID).first().single()
        assertEquals(PendingWriteTypes.VITALS_CREATE, conflict.writeType)
        assertEquals("42", conflict.caseId)
        assertEquals(null, conflict.taskId)
        assertEquals("Vitals already updated on the server.", conflict.message)
        val vitals = database.vitalDao().observeVitalsForCase(ACCOUNT_ID, "42").first()
        assertFalse(vitals.any { it.id == "pending-vitals-write-1" })
        assertEquals("200", vitals.single().id)
        assertEquals("PR 76 | SpO2 98", vitals.single().summary)
    }

    @Test
    fun accountSwitchNeverSendsFirstAccountsQueuedMutation() = runTest {
        val api = FakeSyncApi()
        database.pendingWriteDao().upsertPendingWrite(
            pendingWrite(
                clientWriteId = "account-a-write",
                writeType = PendingWriteTypes.TASK_COMPLETE,
                caseId = "42",
                taskId = "7",
                payloadJson = PendingWriteJson.encodeTaskComplete(ClientWriteRequestDto("account-a-write")),
            ),
        )

        val canContinue = drainPendingWritesForSync(
            api = api,
            database = database,
            ownerAccountId = ACCOUNT_ID,
            accountGeneration = accountGeneration,
            activeAccountId = { "account-b" },
        )

        assertTrue(canContinue)
        assertEquals(0, api.completeTaskCalls)
        assertEquals(
            listOf("account-a-write"),
            database.pendingWriteDao().pendingWrites(ACCOUNT_ID).map { it.clientWriteId },
        )
        assertTrue(database.pendingWriteDao().pendingWrites("account-b").isEmpty())
    }

    @Test
    fun workIdentityAndInputAreQualifiedByVerifiedAccount() {
        assertNotEquals(
            MedtrackSyncWorker.periodicWorkName("account-a"),
            MedtrackSyncWorker.periodicWorkName("account-b"),
        )
        assertNotEquals(
            MedtrackSyncWorker.oneTimeWorkName("account-a"),
            MedtrackSyncWorker.oneTimeWorkName("account-b"),
        )
        assertEquals(
            "account-a",
            MedtrackSyncWorker.oneTimeRequest("https://example.invalid/", "account-a")
                .workSpec.input.getString("account_id"),
        )
    }

    @Test
    fun worker401And403InvalidateTokenDataOutboxCacheAndLock() = runTest {
        listOf(401, 403).forEach { status ->
            val tokenStore = TokenStore(authPrefs)
            val lockStore = LockStore(lockPrefs)
            database.activateAccount(ACCOUNT_ID)
            seedTrustedOwnerState(tokenStore, lockStore)
            val expectedSession = requireNotNull(tokenStore.sessionIdentityFor(ACCOUNT_ID))
            val expectedGeneration = requireNotNull(database.activeAccountGeneration(ACCOUNT_ID))
            val invalidator = testInvalidator(tokenStore, lockStore)

            val result = authenticateWorkerAccount(
                expectedSession = expectedSession,
                expectedGeneration = expectedGeneration,
                tokenStore = tokenStore,
                invalidator = invalidator,
                refreshSession = { throw authError(status) },
                verifyProfile = { error("must not verify") },
            )

            assertEquals(WorkerAuthenticationResult.Invalidated, result)
            assertOwnerPurged(tokenStore, lockStore)
        }
    }

    @Test
    fun workerIdentityMismatchInvalidatesTrustedOwnerState() = runTest {
        val tokenStore = TokenStore(authPrefs)
        val lockStore = LockStore(lockPrefs)
        val repository = MedtrackRepository(api = FakeSyncApi(), database = database)
        repository.activateAccount(ACCOUNT_ID)
        val visibilityListener: (String) -> Unit = { accountId ->
            if (repository.activeAccountId() == accountId) repository.deactivateAccount()
        }
        AccountVisibilityInvalidations.register(visibilityListener)
        seedTrustedOwnerState(tokenStore, lockStore)
        val expectedSession = requireNotNull(tokenStore.sessionIdentityFor(ACCOUNT_ID))
        val expectedGeneration = requireNotNull(database.activeAccountGeneration(ACCOUNT_ID))

        val result = try {
            authenticateWorkerAccount(
                expectedSession = expectedSession,
                expectedGeneration = expectedGeneration,
                tokenStore = tokenStore,
                invalidator = testInvalidator(tokenStore, lockStore),
                refreshSession = {
                    AuthSessionDto(
                        jwt(ACCOUNT_ID, "candidate-access"),
                        jwt(ACCOUNT_ID, "rotated-refresh"),
                    )
                },
                verifyProfile = {
                    UserProfileDto(2, "other", "Other", emptyList(), emptyMap())
                },
            )
        } finally {
            AccountVisibilityInvalidations.unregister(visibilityListener)
        }

        assertEquals(WorkerAuthenticationResult.Invalidated, result)
        assertNull(repository.activeAccountId())
        assertTrue(repository.cases.first().isEmpty())
        assertOwnerPurged(tokenStore, lockStore)
    }

    @Test
    fun targetedWorkerRefreshWithoutApprovedMobileClaimInvalidatesSession() = runTest {
        val tokenStore = TokenStore(authPrefs)
        val lockStore = LockStore(lockPrefs)
        database.activateAccount(ACCOUNT_ID)
        seedTrustedOwnerState(tokenStore, lockStore)
        assertTrue(
            tokenStore.commitVerifiedSession(
                ACCOUNT_ID,
                "old-access",
                "old-refresh",
                MOBILE_DEVICE_ID,
            ),
        )
        val expectedSession = requireNotNull(tokenStore.sessionIdentityFor(ACCOUNT_ID))
        val expectedGeneration = requireNotNull(database.activeAccountGeneration(ACCOUNT_ID))
        var verifyCalls = 0

        val result = authenticateWorkerAccount(
            expectedSession = expectedSession,
            expectedGeneration = expectedGeneration,
            tokenStore = tokenStore,
            invalidator = testInvalidator(tokenStore, lockStore),
            refreshSession = {
                AuthSessionDto(
                    jwt(ACCOUNT_ID, "access-without-device"),
                    jwt(ACCOUNT_ID, "refresh-without-device"),
                )
            },
            verifyProfile = {
                verifyCalls += 1
                UserProfileDto(1, "same", "Same", emptyList(), emptyMap())
            },
        )

        assertEquals(WorkerAuthenticationResult.Invalidated, result)
        assertEquals(0, verifyCalls)
        assertOwnerPurged(tokenStore, lockStore)
    }

    @Test
    fun workerTransportAndServerFailuresRetainTrustedOwnerStateForRetry() = runTest {
        listOf(java.io.IOException("offline"), authError(503)).forEach { failure ->
            val tokenStore = TokenStore(authPrefs)
            val lockStore = LockStore(lockPrefs)
            database.activateAccount(ACCOUNT_ID)
            seedTrustedOwnerState(tokenStore, lockStore)
            val expectedSession = requireNotNull(tokenStore.sessionIdentityFor(ACCOUNT_ID))
            val expectedGeneration = requireNotNull(database.activeAccountGeneration(ACCOUNT_ID))

            val result = authenticateWorkerAccount(
                expectedSession = expectedSession,
                expectedGeneration = expectedGeneration,
                tokenStore = tokenStore,
                invalidator = testInvalidator(tokenStore, lockStore),
                refreshSession = { throw failure },
                verifyProfile = { error("must not verify") },
            )

            assertEquals(WorkerAuthenticationResult.Retry, result)
            assertEquals(ACCOUNT_ID, tokenStore.accountId())
            assertEquals("refresh-a", tokenStore.refreshToken())
            assertEquals(listOf("write-a"), database.pendingWriteDao().pendingWrites(ACCOUNT_ID).map { it.clientWriteId })
            assertEquals(1L, database.cacheMetadataDao().updatedAtMillis(ACCOUNT_ID, "cache-a"))
            lockStore.activateAccount(ACCOUNT_ID)
            assertTrue(lockStore.hasPattern())
            testInvalidator(tokenStore, lockStore).invalidate(expectedSession, expectedGeneration)
        }
    }

    @Test
    fun capturedWorkerNeverInvalidatesNewlyCommittedDifferentAccount() = runTest {
        val tokenStore = TokenStore(authPrefs)
        val lockStore = LockStore(lockPrefs)
        seedTrustedOwnerState(tokenStore, lockStore)
        val expectedSession = requireNotNull(tokenStore.sessionIdentityFor(ACCOUNT_ID))
        val expectedGeneration = requireNotNull(database.activeAccountGeneration(ACCOUNT_ID))

        val result = authenticateWorkerAccount(
            expectedSession = expectedSession,
            expectedGeneration = expectedGeneration,
            tokenStore = tokenStore,
            invalidator = testInvalidator(tokenStore, lockStore),
            refreshSession = {
                assertTrue(tokenStore.commitVerifiedSession("account-b", "access-b", "refresh-b"))
                throw authError(401)
            },
            verifyProfile = { error("must not verify") },
        )

        assertEquals(WorkerAuthenticationResult.StaleAccount, result)
        assertEquals("account-b", tokenStore.accountId())
        assertEquals("access-b", tokenStore.accessToken)
        assertEquals("refresh-b", tokenStore.refreshToken())
    }

    @Test
    fun staleWorker401CannotInvalidateReloggedSameAccountSession() = runTest {
        val tokenStore = TokenStore(authPrefs)
        val lockStore = LockStore(lockPrefs)
        seedTrustedOwnerState(tokenStore, lockStore)
        val expectedSession = requireNotNull(tokenStore.sessionIdentityFor(ACCOUNT_ID))
        val expectedGeneration = requireNotNull(database.activeAccountGeneration(ACCOUNT_ID))

        val result = authenticateWorkerAccount(
            expectedSession = expectedSession,
            expectedGeneration = expectedGeneration,
            tokenStore = tokenStore,
            invalidator = testInvalidator(tokenStore, lockStore),
            refreshSession = {
                replaceWithNewSameAccountSession(
                    expectedSession,
                    expectedGeneration,
                    tokenStore,
                    lockStore,
                )
                throw authError(401)
            },
            verifyProfile = { error("stale failure must not verify") },
        )

        assertEquals(WorkerAuthenticationResult.StaleAccount, result)
        assertEquals("new-access", tokenStore.accessTokenFor(ACCOUNT_ID))
        assertEquals("new-refresh", tokenStore.refreshTokenFor(ACCOUNT_ID))
        assertEquals(2L, database.cacheMetadataDao().updatedAtMillis(ACCOUNT_ID, "new-cache"))
        lockStore.activateAccount(ACCOUNT_ID)
        assertTrue(lockStore.hasPattern())
    }

    @Test
    fun staleWorkerRefreshSuccessCannotOverwriteReloggedSameAccountSession() = runTest {
        val tokenStore = TokenStore(authPrefs)
        val lockStore = LockStore(lockPrefs)
        seedTrustedOwnerState(tokenStore, lockStore)
        val expectedSession = requireNotNull(tokenStore.sessionIdentityFor(ACCOUNT_ID))
        val expectedGeneration = requireNotNull(database.activeAccountGeneration(ACCOUNT_ID))
        var verifyCalls = 0

        val result = authenticateWorkerAccount(
            expectedSession = expectedSession,
            expectedGeneration = expectedGeneration,
            tokenStore = tokenStore,
            invalidator = testInvalidator(tokenStore, lockStore),
            refreshSession = {
                replaceWithNewSameAccountSession(
                    expectedSession,
                    expectedGeneration,
                    tokenStore,
                    lockStore,
                )
                AuthSessionDto(
                    jwt(ACCOUNT_ID, "stale-candidate"),
                    jwt(ACCOUNT_ID, "stale-rotated"),
                )
            },
            verifyProfile = {
                verifyCalls += 1
                UserProfileDto(1, "same", "Same", emptyList(), emptyMap())
            },
        )

        assertEquals(WorkerAuthenticationResult.StaleAccount, result)
        assertEquals(0, verifyCalls)
        assertEquals("new-access", tokenStore.accessTokenFor(ACCOUNT_ID))
        assertEquals("new-refresh", tokenStore.refreshTokenFor(ACCOUNT_ID))
        assertEquals(2L, database.cacheMetadataDao().updatedAtMillis(ACCOUNT_ID, "new-cache"))
    }

    private suspend fun replaceWithNewSameAccountSession(
        expectedSession: com.naveenhospital.medtrack.core.data.auth.AccountSessionIdentity,
        expectedGeneration: Long,
        tokenStore: TokenStore,
        lockStore: LockStore,
    ) {
        assertTrue(database.invalidateAndClearAccountData(ACCOUNT_ID, expectedGeneration))
        assertTrue(tokenStore.clearForIdentity(expectedSession))
        lockStore.clearAccount(ACCOUNT_ID)
        assertTrue(tokenStore.commitVerifiedSession(ACCOUNT_ID, "new-access", "new-refresh"))
        database.activateAccount(ACCOUNT_ID)
        database.cacheMetadataDao().upsertMetadata(CacheMetadataEntity(ACCOUNT_ID, "new-cache", 2L))
        lockStore.activateAccount(ACCOUNT_ID)
        lockStore.savePattern(listOf(0, 1, 4, 8))
    }

    private suspend fun seedTrustedOwnerState(tokenStore: TokenStore, lockStore: LockStore) {
        assertTrue(tokenStore.commitVerifiedSession(ACCOUNT_ID, "access-a", "refresh-a"))
        lockStore.activateAccount(ACCOUNT_ID)
        lockStore.savePattern(listOf(1, 2, 3, 6))
        database.pendingWriteDao().upsertPendingWrite(
            pendingWrite(
                clientWriteId = "write-a",
                writeType = PendingWriteTypes.TASK_COMPLETE,
                payloadJson = PendingWriteJson.encodeTaskComplete(ClientWriteRequestDto("write-a")),
            ),
        )
        database.cacheMetadataDao().upsertMetadata(CacheMetadataEntity(ACCOUNT_ID, "cache-a", 1L))
        database.pushTokenDao().upsertToken(PushTokenEntity(ACCOUNT_ID, "push-a", "device", 0L))
        database.notificationDao().upsertNotifications(
            listOf(
                NotificationEntity(
                    ACCOUNT_ID,
                    "notification-a",
                    "assignment",
                    "PHI",
                    "body",
                    "42",
                    "7",
                    "2026-08-29T12:00:00Z",
                    false,
                ),
            ),
        )
    }

    private fun testInvalidator(tokenStore: TokenStore, lockStore: LockStore): AccountSessionInvalidator =
        AccountSessionInvalidator(database, tokenStore, lockStore, cancelAccountWork = {})

    private suspend fun assertOwnerPurged(tokenStore: TokenStore, lockStore: LockStore) {
        assertNull(tokenStore.accountId())
        assertNull(tokenStore.refreshToken())
        assertTrue(database.pendingWriteDao().pendingWrites(ACCOUNT_ID).isEmpty())
        assertNull(database.cacheMetadataDao().updatedAtMillis(ACCOUNT_ID, "cache-a"))
        assertNull(database.pushTokenDao().latestToken(ACCOUNT_ID))
        assertTrue(database.notificationDao().observeNotifications(ACCOUNT_ID).first().isEmpty())
        lockStore.activateAccount(ACCOUNT_ID)
        assertFalse(lockStore.hasPattern())
    }

    private fun authError(status: Int): HttpException =
        HttpException(
            Response.error<Any>(
                status,
                "auth".toResponseBody("text/plain".toMediaType()),
            ),
        )

    @Test
    fun notificationPaginationExhaustsAllPagesAndReconcilesStaleRows() = runTest {
        database.notificationDao().upsertNotifications(
            listOf(notificationEntity(id = "stale", type = "assignment")),
        )
        val api = FakeSyncApi(
            notificationPages = mapOf(
                null to notificationPage(
                    nextCursor = "opaque-page-2",
                    notification = notificationDto(101, "assignment"),
                ),
                "opaque-page-2" to notificationPage(nextCursor = null, notification = notificationDto(100, "red_flag")),
            ),
        )

        val snapshot = fetchAllNotifications(api)
        replaceNotificationSnapshot(
            database,
            type = null,
            snapshot = NotificationSnapshot(
                datasetEpoch = snapshot.datasetEpoch,
                notifications = snapshot.notifications.map { it.toTestEntity() },
            ),
        )

        assertEquals(listOf(null, "opaque-page-2"), api.notificationCursorsRequested)
        assertEquals("11111111-1111-4111-8111-111111111111", snapshot.datasetEpoch)
        assertEquals(listOf("101", "100"), database.notificationDao().observeNotifications().first().map { it.id })
    }

    @Test
    fun notificationCursorFailureIsFailClosedAndDoesNotReconcileBeforeTerminalPage() = runTest {
        database.notificationDao().upsertNotifications(
            listOf(notificationEntity(id = "authorized-prior-snapshot", type = "assignment")),
        )
        val api = FakeSyncApi(
            notificationPages = mapOf(
                null to notificationPage(
                    nextCursor = "tampered-or-stale-cursor",
                    notification = notificationDto(101, "assignment"),
                ),
            ),
            notificationErrors = mapOf(
                "tampered-or-stale-cursor" to httpError(400, "Invalid cursor"),
            ),
        )

        val result = runCatching { fetchAllNotifications(api) }

        assertTrue(result.isFailure)
        assertEquals(listOf(null, "tampered-or-stale-cursor"), api.notificationCursorsRequested)
        assertEquals(
            listOf("authorized-prior-snapshot"),
            database.notificationDao().observeNotifications().first().map { it.id },
        )
    }

    @Test
    fun rowsRevokedBetweenPagesAreAbsentFromTerminalSnapshotAndPurged() = runTest {
        database.notificationDao().upsertNotifications(
            listOf(notificationEntity(id = "revoked-after-page-one", type = "red_flag")),
        )
        val api = FakeSyncApi(
            notificationPages = mapOf(
                null to notificationPage(
                    nextCursor = "authorized-page-two",
                    notification = notificationDto(101, "assignment"),
                ),
                "authorized-page-two" to NotificationsResponseDto(
                    datasetEpoch = "11111111-1111-4111-8111-111111111111",
                    nextCursor = null,
                    results = emptyList(),
                ),
            ),
        )

        val snapshot = fetchAllNotifications(api)
        replaceNotificationSnapshot(
            database = database,
            type = null,
            snapshot = NotificationSnapshot(
                datasetEpoch = snapshot.datasetEpoch,
                notifications = snapshot.notifications.map { it.toTestEntity() },
            ),
        )

        assertEquals(listOf("101"), database.notificationDao().observeNotifications().first().map { it.id })
    }

    @Test
    fun changedDatasetEpochDiscardsNotificationReadOutboxButLeavesClinicalWriteForSecurityLane() = runTest {
        val epochPrefix = com.naveenhospital.medtrack.core.data.repository.CACHE_KEY_NOTIFICATION_DATASET_EPOCH_PREFIX
        database.cacheMetadataDao().upsertMetadata(
            CacheMetadataEntity(
                cacheKey = epochPrefix + "22222222-2222-4222-8222-222222222222",
                updatedAtMillis = 1,
            ),
        )
        database.pendingWriteDao().upsertPendingWrite(
            pendingWrite(
                clientWriteId = "notification-read",
                writeType = PendingWriteTypes.NOTIFICATION_READ,
                caseId = null,
                payloadJson = PendingWriteJson.encodeNotificationRead(
                    NotificationReadPayload(notificationId = "7", clientWriteId = "notification-read"),
                ),
            ),
        )
        database.pendingWriteDao().upsertPendingWrite(
            pendingWrite(
                clientWriteId = "clinical-write",
                writeType = PendingWriteTypes.TASK_COMPLETE,
                payloadJson = PendingWriteJson.encodeTaskComplete(ClientWriteRequestDto("clinical-write")),
            ),
        )

        replaceNotificationSnapshot(
            database = database,
            type = null,
            snapshot = NotificationSnapshot(
                datasetEpoch = "11111111-1111-4111-8111-111111111111",
                notifications = emptyList(),
            ),
        )

        assertEquals(listOf("clinical-write"), database.pendingWriteDao().pendingWrites().map { it.clientWriteId })
        assertEquals(
            listOf(epochPrefix + "11111111-1111-4111-8111-111111111111"),
            database.cacheMetadataDao().cacheKeysStartingWith(epochPrefix),
        )
    }

    @Test
    fun validationFailureRetainsStructuredRecoveryAndDoesNotPoisonQueue() = runTest {
        val payload = PendingWriteJson.encodeTaskComplete(ClientWriteRequestDto("validation-write"))
        val api = FakeSyncApi(completeTaskError = httpError(400, "{\"status\":[\"Invalid transition\"]}"))
        database.pendingWriteDao().upsertPendingWrite(
            pendingWrite(
                clientWriteId = "validation-write",
                writeType = PendingWriteTypes.TASK_COMPLETE,
                caseId = "42",
                taskId = "7",
                payloadJson = payload,
            ),
        )

        val outcome = drainPendingWritesForSync(api, database)

        assertEquals(SyncRunOutcome.COMPLETED, outcome)
        assertTrue(database.pendingWriteDao().pendingWrites().isEmpty())
        val issue = database.syncConflictDao().conflictById("validation-write")
        val recovery = SyncRecoveryJson.decode(issue?.serverPayloadJson)
        assertEquals(SyncFailureKinds.VALIDATION, recovery?.failureKind)
        assertEquals(payload, recovery?.localPayloadJson)
        assertEquals("{\"status\":[\"Invalid transition\"]}", recovery?.serverPayloadJson)
        assertEquals(400, recovery?.httpStatus)
    }

    @Test
    fun authFailureStopsAndRetainsPendingWriteForReauthentication() = runTest {
        val api = FakeSyncApi(completeTaskError = httpError(401, "token_not_valid"))
        database.pendingWriteDao().upsertPendingWrite(
            pendingWrite(
                clientWriteId = "auth-write",
                writeType = PendingWriteTypes.TASK_COMPLETE,
                caseId = "42",
                taskId = "7",
                payloadJson = PendingWriteJson.encodeTaskComplete(ClientWriteRequestDto("auth-write")),
            ),
        )

        val outcome = drainPendingWritesForSync(api, database)

        assertEquals(SyncRunOutcome.AUTH_REQUIRED, outcome)
        assertEquals("auth-write", database.pendingWriteDao().pendingWrites().single().clientWriteId)
        val recovery = SyncRecoveryJson.decode(
            database.syncConflictDao().conflictById("auth-write")?.serverPayloadJson,
        )
        assertEquals(SyncFailureKinds.AUTHENTICATION, recovery?.failureKind)
    }

    @Test
    fun authorizationFailureIsTerminalForOnlyThatWriteAndRetainsSessionClassification() = runTest {
        val api = FakeSyncApi(completeTaskError = httpError(403, "scope_revoked"))
        database.pendingWriteDao().upsertPendingWrite(
            pendingWrite(
                clientWriteId = "forbidden-write",
                writeType = PendingWriteTypes.TASK_COMPLETE,
                caseId = "42",
                taskId = "7",
                payloadJson = PendingWriteJson.encodeTaskComplete(ClientWriteRequestDto("forbidden-write")),
            ),
        )

        val outcome = drainPendingWritesForSync(api, database)

        assertEquals(SyncRunOutcome.COMPLETED, outcome)
        assertTrue(database.pendingWriteDao().pendingWrites().isEmpty())
        val recovery = SyncRecoveryJson.decode(
            database.syncConflictDao().conflictById("forbidden-write")?.serverPayloadJson,
        )
        assertEquals(SyncFailureKinds.AUTHORIZATION, recovery?.failureKind)
        assertEquals(403, recovery?.httpStatus)
    }

    @Test
    fun protocolFailureAtRetryCeilingRollsBackTaskAndDoesNotBlockLaterWrite() = runTest {
        val originalTask = TaskEntity(
            id = "7",
            caseId = "42",
            title = "Local review",
            dueDate = "2026-08-30",
            status = "PENDING",
            statusLabel = "Pending",
            canComplete = true,
            updatedAtMillis = 10L,
        )
        database.taskDao().upsertTask(originalTask.copy(status = "COMPLETED", statusLabel = "Completed", canComplete = false))
        database.pendingWriteDao().upsertPendingWrite(
            pendingWrite(
                clientWriteId = "protocol-write",
                writeType = PendingWriteTypes.TASK_COMPLETE,
                caseId = "42",
                taskId = "7",
                payloadJson = PendingWriteJson.encodeTaskComplete(
                    ClientWriteRequestDto("protocol-write"),
                    originalTask,
                ),
                retryCount = MAX_PENDING_WRITE_ATTEMPTS - 1,
            ),
        )
        database.pendingWriteDao().upsertPendingWrite(
            pendingWrite(
                clientWriteId = "later-call-write",
                writeType = PendingWriteTypes.CALL_OUTCOME,
                caseId = "42",
                payloadJson = PendingWriteJson.encodeCallOutcome(
                    LogCallRequestDto(outcome = "NO_ANSWER", clientWriteId = "later-call-write"),
                ),
            ),
        )
        val api = FakeSyncApi(completeTaskError = IllegalStateException("schema drift"))

        val outcome = drainPendingWritesForSync(api, database)

        assertEquals(SyncRunOutcome.COMPLETED, outcome)
        assertTrue(database.pendingWriteDao().pendingWrites().isEmpty())
        val recovery = SyncRecoveryJson.decode(
            database.syncConflictDao().conflictById("protocol-write")?.serverPayloadJson,
        )
        assertEquals(SyncFailureKinds.PROTOCOL, recovery?.failureKind)
        assertEquals(MAX_PENDING_WRITE_ATTEMPTS, recovery?.attemptCount)
        assertEquals("SCHEDULED", database.taskDao().observeTasksForCase("42").first().single().status)
    }

    @Test
    fun malformedOptimisticTaskIsRemovedWhenAuthoritativeRefreshCannotRun() = runTest {
        database.taskDao().upsertTask(
            TaskEntity(
                id = "7",
                caseId = "42",
                title = "Optimistic",
                dueDate = null,
                status = "COMPLETED",
                statusLabel = "Completed",
                canComplete = false,
                updatedAtMillis = 1L,
            ),
        )
        database.pendingWriteDao().upsertPendingWrite(
            pendingWrite(
                clientWriteId = "malformed-task",
                writeType = PendingWriteTypes.TASK_COMPLETE,
                caseId = "42",
                taskId = "7",
                payloadJson = "{not-json",
            ),
        )

        val outcome = drainPendingWritesForSync(
            FakeSyncApi(caseDetailError = IOException("offline")),
            database,
        )

        assertEquals(SyncRunOutcome.COMPLETED, outcome)
        assertTrue(database.taskDao().observeTasksForCase("42").first().isEmpty())
    }

    private suspend fun assertServerVersionRefreshed() {
        val case = database.caseDao().caseById(ACCOUNT_ID, "42")
        assertEquals("Server Patient", case?.patientName)
        val tasks = database.taskDao().observeTasksForCase(ACCOUNT_ID, "42").first()
        assertEquals("Server review", tasks.single().title)
        val vitals = database.vitalDao().observeVitalsForCase(ACCOUNT_ID, "42").first()
        assertEquals("PR 76 | SpO2 98", vitals.single().summary)
    }

    private fun pendingWrite(
        clientWriteId: String,
        writeType: String,
        caseId: String? = "42",
        taskId: String? = null,
        payloadJson: String,
        retryCount: Int = 0,
    ): PendingWriteEntity =
        PendingWriteEntity(
            ownerAccountId = ACCOUNT_ID,
            clientWriteId = clientWriteId,
            writeType = writeType,
            caseId = caseId,
            taskId = taskId,
            payloadJson = payloadJson,
            retryCount = retryCount,
            lastError = null,
            createdAtMillis = 1L,
            updatedAtMillis = 1L,
        )

    private companion object {
        const val ACCOUNT_ID = "1"
        const val MOBILE_DEVICE_ID = "11111111-1111-4111-8111-111111111111"
    }

    private fun conflictError(message: String): HttpException =
        httpError(409, message)

    private fun httpError(code: Int, message: String): HttpException = HttpException(
        Response.error<Any>(code, message.toResponseBody("application/json".toMediaType())),
    )

    private fun notificationDto(id: Long, type: String) =
        com.naveenhospital.medtrack.core.network.model.NotificationDto(
            id = id,
            eventId = "event-$id",
            type = type,
            title = "Test alert",
            body = "Open MEDTRACK",
            caseId = 42,
            taskId = null,
            readAt = null,
            createdAt = "2026-08-29T18:00:0${id % 10}Z",
        )

    private fun notificationPage(
        nextCursor: String?,
        notification: com.naveenhospital.medtrack.core.network.model.NotificationDto,
    ) = NotificationsResponseDto(
        datasetEpoch = "11111111-1111-4111-8111-111111111111",
        nextCursor = nextCursor,
        results = listOf(notification),
    )

    private fun notificationEntity(id: String, type: String) = NotificationEntity(
        id = id,
        type = type,
        title = "Stale",
        body = "Stale",
        caseId = null,
        taskId = null,
        createdAt = "2026-01-01T00:00:00Z",
        isRead = false,
    )

    private fun com.naveenhospital.medtrack.core.network.model.NotificationDto.toTestEntity() = NotificationEntity(
        id = id.toString(),
        type = type,
        title = title,
        body = body,
        caseId = caseId?.toString(),
        taskId = taskId?.toString(),
        createdAt = createdAt,
        isRead = readAt != null,
    )
}

private fun jwt(accountId: String, marker: String, mobileDeviceId: String? = null): String {
    val mobileClaim = mobileDeviceId?.let { ",\"mobile_device_id\":\"$it\"" }.orEmpty()
    val payload = """{"user_id":"$accountId","marker":"$marker"$mobileClaim}"""
    val encoded = java.util.Base64.getUrlEncoder().withoutPadding()
        .encodeToString(payload.toByteArray(Charsets.UTF_8))
    return "header.$encoded.signature"
}

private class FakeSyncApi(
    private val completeTaskError: Throwable? = null,
    private val logCallError: Throwable? = null,
    private val addVitalsError: Throwable? = null,
    private val caseDetailError: Throwable? = null,
    private val notificationPages: Map<String?, NotificationsResponseDto> = emptyMap(),
    private val notificationErrors: Map<String?, Throwable> = emptyMap(),
) : MedtrackApi {
    var completeTaskCalls: Int = 0
        private set
    val notificationCursorsRequested = mutableListOf<String?>()
    override suspend fun completeTask(taskId: String, request: ClientWriteRequestDto): TaskWriteResponseDto {
        completeTaskCalls += 1
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

    override suspend fun caseDetail(caseId: String): CaseDetailDto {
        caseDetailError?.let { throw it }
        return CaseDetailDto(
            case = sampleCase(),
            tasks = listOf(sampleTask(700)),
            vitals = listOf(sampleVital()),
        )
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
        query: String?,
        page: Int?,
    ): CaseListResponseDto = unused()
    override suspend fun vitalsThresholds(): VitalsThresholdsDto = unused()
    override suspend fun notifications(type: String?, unreadOnly: Boolean?, cursor: String?, pageSize: Int?): NotificationsResponseDto {
        notificationCursorsRequested += cursor
        assertEquals(100, pageSize)
        notificationErrors[cursor]?.let { throw it }
        return notificationPages[cursor] ?: unused()
    }
    override suspend fun markNotificationRead(notificationId: String): ApiMessageDto = unused()
    override suspend fun registerPushToken(request: RegisterPushTokenRequestDto): ApiMessageDto = unused()
    override suspend fun categories(): CategoriesResponseDto = unused()
    override suspend fun createCase(request: com.naveenhospital.medtrack.core.network.model.CreateCaseRequestDto): com.naveenhospital.medtrack.core.network.model.CaseCreateResponseDto = unused()
    override suspend fun searchPatients(request: com.naveenhospital.medtrack.core.network.model.PatientSearchRequestDto): com.naveenhospital.medtrack.core.network.model.PatientSearchResponseDto = unused()
    override suspend fun caseFormMetadata(): com.naveenhospital.medtrack.core.network.model.CaseFormMetadataDto = unused()
    override suspend fun taskFormMetadata(): com.naveenhospital.medtrack.core.network.model.TaskFormMetadataDto = unused()
    override suspend fun caseEditForm(caseId: String): com.naveenhospital.medtrack.core.network.model.CaseEditFormDto = unused()
    override suspend fun updateCase(caseId: String, request: com.naveenhospital.medtrack.core.network.model.UpdateCaseRequestDto): com.naveenhospital.medtrack.core.network.model.CaseUpdateResponseDto = unused()
    override suspend fun createTask(caseId: String, request: com.naveenhospital.medtrack.core.network.model.CreateTaskRequestDto): TaskWriteResponseDto = unused()
    override suspend fun updateTask(taskId: String, request: com.naveenhospital.medtrack.core.network.model.UpdateTaskRequestDto): TaskWriteResponseDto = unused()
    override suspend fun addTaskNote(taskId: String, request: com.naveenhospital.medtrack.core.network.model.TaskNoteRequestDto): TaskWriteResponseDto = unused()
    override suspend fun updateVitals(vitalId: String, request: com.naveenhospital.medtrack.core.network.model.VitalsUpdateRequestDto): VitalsWriteResponseDto = unused()

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
