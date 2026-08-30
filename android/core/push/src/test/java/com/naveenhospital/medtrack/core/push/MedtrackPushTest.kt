package com.naveenhospital.medtrack.core.push

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
        runCatching { TokenStore(context).clear() }
        runCatching { LockStore(context).clearAccount(ACCOUNT_ID) }
        database = Room.inMemoryDatabaseBuilder(context, MedtrackDatabase::class.java)
            .allowMainThreadQueries()
            .build()
        runBlocking { database.activateAccount(ACCOUNT_ID) }
    }

    @After
    fun tearDown() {
        database.close()
        runCatching { TokenStore(context).clear() }
        runCatching { LockStore(context).clearAccount(ACCOUNT_ID) }
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
            val tokenStore = TokenStore(context)
            val invalidator = testInvalidator(tokenStore, lockStore)

            val registered = registerPushTokenForAccountSession(
                ownerAccountId = ACCOUNT_ID,
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
        val tokenStore = TokenStore(context)
        val invalidator = testInvalidator(tokenStore, lockStore)

        val registered = registerPushTokenForAccountSession(
            ownerAccountId = ACCOUNT_ID,
            token = "push-new",
            deviceLabel = "device",
            tokenStore = tokenStore,
            database = database,
            invalidateIfCurrent = invalidator::invalidateIfCurrent,
            refreshSession = { AuthSessionDto("candidate", "rotated") },
            verifyProfile = { UserProfileDto(2, "other", "Other", emptyList(), emptyMap()) },
            registerRemote = { error("must not register") },
        )

        assertFalse(registered)
        assertPurged(tokenStore, lockStore)
    }

    @Test
    fun pushRegistration401And403PurgesAlreadyAuthenticatedOwner() = runTest {
        listOf(401, 403).forEach { status ->
            database.activateAccount(ACCOUNT_ID)
            val lockStore = seedTrustedState()
            val tokenStore = TokenStore(context)
            assertTrue(tokenStore.commitVerifiedSession(ACCOUNT_ID, "active-access", "refresh-a"))
            val invalidator = testInvalidator(tokenStore, lockStore)

            val registered = registerPushTokenForAccountSession(
                ownerAccountId = ACCOUNT_ID,
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
            val tokenStore = TokenStore(context)
            val invalidator = testInvalidator(tokenStore, lockStore)

            val registered = registerPushTokenForAccountSession(
                ownerAccountId = ACCOUNT_ID,
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
            invalidator.invalidate(ACCOUNT_ID)
        }
    }

    private suspend fun seedTrustedState(): LockStore {
        val seedStore = TokenStore(context)
        assertTrue(seedStore.commitVerifiedSession(ACCOUNT_ID, "access-a", "refresh-a"))
        val lockStore = LockStore(context)
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

    private companion object {
        const val ACCOUNT_ID = "1"
    }
}
