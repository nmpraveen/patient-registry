package com.naveenhospital.medtrack.core.push

import com.naveenhospital.medtrack.core.data.auth.testTokenStore
import com.naveenhospital.medtrack.core.data.auth.testLockStore
import android.content.Context
import androidx.room.Room
import androidx.test.core.app.ApplicationProvider
import com.naveenhospital.medtrack.core.data.auth.AccountSessionInvalidator
import com.naveenhospital.medtrack.core.data.auth.LockStore
import com.naveenhospital.medtrack.core.data.auth.TokenStore
import com.naveenhospital.medtrack.core.data.local.CacheMetadataEntity
import com.naveenhospital.medtrack.core.data.local.MedtrackDatabase
import com.naveenhospital.medtrack.core.data.local.PendingWriteEntity
import com.naveenhospital.medtrack.core.data.sync.PendingWriteTypes
import com.naveenhospital.medtrack.core.network.model.AuthSessionDto
import com.naveenhospital.medtrack.core.network.model.DataScopeDto
import com.naveenhospital.medtrack.core.network.model.UserProfileDto
import java.io.IOException
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.test.runTest
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.ResponseBody.Companion.toResponseBody
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import retrofit2.HttpException
import retrofit2.Response

@RunWith(RobolectricTestRunner::class)
class MedtrackPushTest {
    private lateinit var context: Context
    private lateinit var database: MedtrackDatabase

    @Before
    fun setUp() {
        context = ApplicationProvider.getApplicationContext()
        runCatching { testTokenStore(context).clear() }
        runCatching { testLockStore(context).clearAccount(ACCOUNT_ID) }
        database = Room.inMemoryDatabaseBuilder(context, MedtrackDatabase::class.java)
            .allowMainThreadQueries()
            .build()
        runBlocking { database.activateAccount(ACCOUNT_ID) }
    }

    @After
    fun tearDown() {
        database.close()
        runCatching { testTokenStore(context).clear() }
        runCatching { testLockStore(context).clearAccount(ACCOUNT_ID) }
    }

    @Test
    fun channelForTypeMapsServerNotificationTypesToV1Channels() {
        assertEquals(MedtrackPush.CHANNEL_ASSIGNMENTS, MedtrackPush.channelForType("assignment"))
        assertEquals(MedtrackPush.CHANNEL_RED_FLAGS, MedtrackPush.channelForType("red_flag"))
        assertEquals(MedtrackPush.CHANNEL_OVERDUE, MedtrackPush.channelForType("overdue"))
    }

    @Test
    fun channelForTypeAcceptsChannelAliasesFromPayloads() {
        assertEquals(MedtrackPush.CHANNEL_ASSIGNMENTS, MedtrackPush.channelForType("assignments"))
        assertEquals(MedtrackPush.CHANNEL_RED_FLAGS, MedtrackPush.channelForType("red_flags"))
    }

    @Test
    fun channelForTypeFallsBackToOverdueForUnknownOrMissingType() {
        assertEquals(MedtrackPush.CHANNEL_OVERDUE, MedtrackPush.channelForType(null))
        assertEquals(MedtrackPush.CHANNEL_OVERDUE, MedtrackPush.channelForType(""))
        assertEquals(MedtrackPush.CHANNEL_OVERDUE, MedtrackPush.channelForType("unexpected"))
    }

    @Test
    fun pushRefresh401And403PurgesTokenOutboxCacheAndLock() = runTest {
        listOf(401, 403).forEach { status ->
            database.activateAccount(ACCOUNT_ID)
            val lockStore = seedTrustedState()
            val tokenStore = testTokenStore(context)
            val expectedSession = requireNotNull(tokenStore.sessionIdentityFor(ACCOUNT_ID))
            val accountGeneration = requireNotNull(database.activeAccountGeneration(ACCOUNT_ID))
            val invalidator = testInvalidator(tokenStore, lockStore)

            val registered = registerPushTokenForAccountSession(
                expectedSession = expectedSession,
                accountGeneration = accountGeneration,
                token = "push-new",
                deviceLabel = "device",
                tokenStore = tokenStore,
                database = database,
                invalidateIfCurrent = invalidator::invalidateIfCurrent,
                refreshSession = { throw httpError(status) },
                verifyProfile = { error("must not verify") },
                registerRemote = { error("must not register") },
            )

            assertFalse(registered)
            assertPurged(tokenStore, lockStore)
        }
    }

    @Test
    fun pushIdentityMismatchPurgesTrustedOwnerState() = runTest {
        val lockStore = seedTrustedState()
        val tokenStore = testTokenStore(context)
        val expectedSession = requireNotNull(tokenStore.sessionIdentityFor(ACCOUNT_ID))
        val accountGeneration = requireNotNull(database.activeAccountGeneration(ACCOUNT_ID))
        val invalidator = testInvalidator(tokenStore, lockStore)

        val registered = registerPushTokenForAccountSession(
            expectedSession = expectedSession,
            accountGeneration = accountGeneration,
            token = "push-new",
            deviceLabel = "device",
            tokenStore = tokenStore,
            database = database,
            invalidateIfCurrent = invalidator::invalidateIfCurrent,
            refreshSession = {
                AuthSessionDto(
                    jwt(ACCOUNT_ID, "candidate"),
                    jwt(ACCOUNT_ID, "rotated"),
                )
            },
            verifyProfile = { UserProfileDto(2, "other", "Other", emptyList(), emptyMap(), DATA_SCOPE) },
            registerRemote = { error("must not register") },
        )

        assertFalse(registered)
        assertPurged(tokenStore, lockStore)
    }

    @Test
    fun targetedPushRefreshWithoutApprovedMobileClaimInvalidatesSession() = runTest {
        val lockStore = seedTrustedState()
        val sessionWriter = testTokenStore(context)
        assertTrue(
            sessionWriter.commitVerifiedSession(
                ACCOUNT_ID,
                "old-access",
                "old-refresh",
                MOBILE_DEVICE_ID,
            ),
        )
        val tokenStore = testTokenStore(context)
        val expectedSession = requireNotNull(tokenStore.sessionIdentityFor(ACCOUNT_ID))
        val accountGeneration = requireNotNull(database.activeAccountGeneration(ACCOUNT_ID))
        var verifyCalls = 0

        val registered = registerPushTokenForAccountSession(
            expectedSession = expectedSession,
            accountGeneration = accountGeneration,
            token = "push-mobile-bound",
            deviceLabel = "device",
            tokenStore = tokenStore,
            database = database,
            invalidateIfCurrent = testInvalidator(tokenStore, lockStore)::invalidateIfCurrent,
            refreshSession = {
                AuthSessionDto(
                    jwt(ACCOUNT_ID, "access-without-device"),
                    jwt(ACCOUNT_ID, "refresh-without-device"),
                )
            },
            verifyProfile = {
                verifyCalls += 1
                UserProfileDto(1, "same", "Same", emptyList(), emptyMap(), DATA_SCOPE)
            },
            registerRemote = { error("must not register") },
        )

        assertFalse(registered)
        assertEquals(0, verifyCalls)
        assertPurged(tokenStore, lockStore)
    }

    @Test
    fun pushRegistration401And403PurgesAlreadyAuthenticatedOwner() = runTest {
        listOf(401, 403).forEach { status ->
            database.activateAccount(ACCOUNT_ID)
            val lockStore = seedTrustedState()
            val tokenStore = testTokenStore(context)
            assertTrue(tokenStore.commitVerifiedSession(ACCOUNT_ID, "active-access", "refresh-a"))
            val expectedSession = requireNotNull(tokenStore.sessionIdentityFor(ACCOUNT_ID))
            val accountGeneration = requireNotNull(database.activeAccountGeneration(ACCOUNT_ID))
            val invalidator = testInvalidator(tokenStore, lockStore)

            val registered = registerPushTokenForAccountSession(
                expectedSession = expectedSession,
                accountGeneration = accountGeneration,
                token = "push-new",
                deviceLabel = "device",
                tokenStore = tokenStore,
                database = database,
                invalidateIfCurrent = invalidator::invalidateIfCurrent,
                refreshSession = { error("must not refresh") },
                verifyProfile = { error("must not verify") },
                registerRemote = { throw httpError(status) },
            )

            assertFalse(registered)
            assertPurged(tokenStore, lockStore)
        }
    }

    @Test
    fun pushTransportAndServerFailuresRetainTrustedStateForRetry() = runTest {
        listOf(IOException("offline"), httpError(503)).forEach { failure ->
            database.activateAccount(ACCOUNT_ID)
            val lockStore = seedTrustedState()
            val tokenStore = testTokenStore(context)
            val expectedSession = requireNotNull(tokenStore.sessionIdentityFor(ACCOUNT_ID))
            val accountGeneration = requireNotNull(database.activeAccountGeneration(ACCOUNT_ID))
            val invalidator = testInvalidator(tokenStore, lockStore)

            val registered = registerPushTokenForAccountSession(
                expectedSession = expectedSession,
                accountGeneration = accountGeneration,
                token = "push-new",
                deviceLabel = "device",
                tokenStore = tokenStore,
                database = database,
                invalidateIfCurrent = invalidator::invalidateIfCurrent,
                refreshSession = { throw failure },
                verifyProfile = { error("must not verify") },
                registerRemote = { error("must not register") },
            )

            assertFalse(registered)
            assertEquals(ACCOUNT_ID, tokenStore.accountId())
            assertEquals("refresh-a", tokenStore.refreshToken())
            assertEquals(listOf("write-a"), database.pendingWriteDao().pendingWrites(ACCOUNT_ID).map { it.clientWriteId })
            assertEquals(1L, database.cacheMetadataDao().updatedAtMillis(ACCOUNT_ID, "cache-a"))
            lockStore.activateAccount(ACCOUNT_ID)
            assertTrue(lockStore.hasPattern())
            invalidator.invalidate(expectedSession, accountGeneration)
        }
    }

    @Test
    fun stalePush401CannotInvalidateReloggedSameAccountSession() = runTest {
        val lockStore = seedTrustedState()
        val tokenStore = testTokenStore(context)
        val expectedSession = requireNotNull(tokenStore.sessionIdentityFor(ACCOUNT_ID))
        val accountGeneration = requireNotNull(database.activeAccountGeneration(ACCOUNT_ID))
        val invalidator = testInvalidator(tokenStore, lockStore)

        val registered = registerPushTokenForAccountSession(
            expectedSession = expectedSession,
            accountGeneration = accountGeneration,
            token = "stale-push",
            deviceLabel = "old-session",
            tokenStore = tokenStore,
            database = database,
            invalidateIfCurrent = invalidator::invalidateIfCurrent,
            refreshSession = {
                replaceWithNewSameAccountSession(expectedSession, accountGeneration, tokenStore, lockStore)
                throw httpError(401)
            },
            verifyProfile = { error("stale failure must not verify") },
            registerRemote = { error("stale failure must not register") },
        )

        assertFalse(registered)
        assertEquals("new-access", tokenStore.accessTokenFor(ACCOUNT_ID))
        assertEquals("new-refresh", tokenStore.refreshTokenFor(ACCOUNT_ID))
        lockStore.activateAccount(ACCOUNT_ID)
        assertTrue(lockStore.hasPattern())
    }

    @Test
    fun stalePushRefreshSuccessCannotOverwriteReloggedSameAccountSession() = runTest {
        val lockStore = seedTrustedState()
        val tokenStore = testTokenStore(context)
        val expectedSession = requireNotNull(tokenStore.sessionIdentityFor(ACCOUNT_ID))
        val accountGeneration = requireNotNull(database.activeAccountGeneration(ACCOUNT_ID))
        val invalidator = testInvalidator(tokenStore, lockStore)
        var verifyCalls = 0

        val registered = registerPushTokenForAccountSession(
            expectedSession = expectedSession,
            accountGeneration = accountGeneration,
            token = "stale-push",
            deviceLabel = "old-session",
            tokenStore = tokenStore,
            database = database,
            invalidateIfCurrent = invalidator::invalidateIfCurrent,
            refreshSession = {
                replaceWithNewSameAccountSession(expectedSession, accountGeneration, tokenStore, lockStore)
                AuthSessionDto(
                    jwt(ACCOUNT_ID, "stale-candidate"),
                    jwt(ACCOUNT_ID, "stale-rotated"),
                )
            },
            verifyProfile = {
                verifyCalls += 1
                UserProfileDto(1, "same", "Same", emptyList(), emptyMap(), DATA_SCOPE)
            },
            registerRemote = { error("stale success must not register") },
        )

        assertFalse(registered)
        assertEquals(0, verifyCalls)
        assertEquals("new-access", tokenStore.accessTokenFor(ACCOUNT_ID))
        assertEquals("new-refresh", tokenStore.refreshTokenFor(ACCOUNT_ID))
    }

    private suspend fun replaceWithNewSameAccountSession(
        expectedSession: com.naveenhospital.medtrack.core.data.auth.AccountSessionIdentity,
        accountGeneration: Long,
        tokenStore: TokenStore,
        lockStore: LockStore,
    ) {
        assertTrue(database.invalidateAndClearAccountData(ACCOUNT_ID, accountGeneration))
        assertTrue(tokenStore.clearForIdentity(expectedSession))
        lockStore.clearAccount(ACCOUNT_ID)
        assertTrue(tokenStore.commitVerifiedSession(ACCOUNT_ID, "new-access", "new-refresh"))
        database.activateAccount(ACCOUNT_ID)
        lockStore.activateAccount(ACCOUNT_ID)
        lockStore.savePattern(listOf(0, 1, 4, 8))
    }

    private suspend fun seedTrustedState(): LockStore {
        val seedStore = testTokenStore(context)
        assertTrue(seedStore.commitVerifiedSession(ACCOUNT_ID, "access-a", "refresh-a"))
        val lockStore = testLockStore(context)
        lockStore.activateAccount(ACCOUNT_ID)
        lockStore.savePattern(listOf(1, 2, 3, 6))
        database.pendingWriteDao().upsertPendingWrite(
            PendingWriteEntity(
                ownerAccountId = ACCOUNT_ID,
                clientWriteId = "write-a",
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
        database.cacheMetadataDao().upsertMetadata(CacheMetadataEntity(ACCOUNT_ID, "cache-a", 1L))
        return lockStore
    }

    private fun testInvalidator(tokenStore: TokenStore, lockStore: LockStore): AccountSessionInvalidator =
        AccountSessionInvalidator(database, tokenStore, lockStore, cancelAccountWork = {})

    private suspend fun assertPurged(tokenStore: TokenStore, lockStore: LockStore) {
        assertNull(tokenStore.accountId())
        assertNull(tokenStore.refreshToken())
        assertTrue(database.pendingWriteDao().pendingWrites(ACCOUNT_ID).isEmpty())
        assertNull(database.cacheMetadataDao().updatedAtMillis(ACCOUNT_ID, "cache-a"))
        assertNull(database.pushTokenDao().latestToken(ACCOUNT_ID))
        lockStore.activateAccount(ACCOUNT_ID)
        assertFalse(lockStore.hasPattern())
    }

    private fun httpError(status: Int): HttpException =
        HttpException(
            Response.error<Any>(
                status,
                "error".toResponseBody("text/plain".toMediaType()),
            ),
        )

    private fun jwt(accountId: String, marker: String, mobileDeviceId: String? = null): String {
        val mobileClaim = mobileDeviceId?.let { ",\"mobile_device_id\":\"$it\"" }.orEmpty()
        val payload = """{"user_id":"$accountId","marker":"$marker"$mobileClaim}"""
        val encoded = java.util.Base64.getUrlEncoder().withoutPadding()
            .encodeToString(payload.toByteArray(Charsets.UTF_8))
        return "header.$encoded.signature"
    }

    private companion object {
        val DATA_SCOPE = DataScopeDto("ALL", callQueue = true, intakePatientLookup = true)
        const val ACCOUNT_ID = "1"
        const val MOBILE_DEVICE_ID = "11111111-1111-4111-8111-111111111111"
    }
}
