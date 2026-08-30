package com.naveenhospital.medtrack.core.data.auth

import android.content.Context
import androidx.test.core.app.ApplicationProvider
import com.naveenhospital.medtrack.core.network.api.MedtrackNetwork
import okhttp3.mockwebserver.Dispatcher
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import okhttp3.mockwebserver.RecordedRequest
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner

@RunWith(RobolectricTestRunner::class)
class AutomaticRefreshSessionRaceTest {
    private lateinit var tokenStore: TokenStore
    private lateinit var server: MockWebServer

    @Before
    fun setUp() {
        val context = ApplicationProvider.getApplicationContext<Context>()
        val prefs = context.getSharedPreferences("automatic_refresh_session_race", Context.MODE_PRIVATE)
        prefs.edit().clear().commit()
        tokenStore = TokenStore(prefs)
        server = MockWebServer()
        server.start()
    }

    @After
    fun tearDown() {
        server.shutdown()
    }

    @Test
    fun staleAutomatic401CannotUseOrInvalidateReloggedSameAccountSession() {
        assertTrue(tokenStore.commitVerifiedSession(ACCOUNT_ID, "old-access", "old-refresh"))
        val expectedSession = requireNotNull(tokenStore.sessionIdentityFor(ACCOUNT_ID))
        val api = boundApi(expectedSession)
        server.dispatcher = object : Dispatcher() {
            override fun dispatch(request: RecordedRequest): MockResponse {
                assertEquals("/api/metadata/categories/", request.path)
                assertTrue(tokenStore.commitVerifiedSession(ACCOUNT_ID, "new-access", "new-refresh"))
                return MockResponse().setResponseCode(401)
            }
        }

        assertTrue(kotlinx.coroutines.runBlocking { runCatching { api.categories() }.isFailure })

        assertEquals(1, server.requestCount)
        assertEquals("new-access", tokenStore.accessTokenFor(ACCOUNT_ID))
        assertEquals("new-refresh", tokenStore.refreshTokenFor(ACCOUNT_ID))
        assertNotEquals(expectedSession, tokenStore.sessionIdentityFor(ACCOUNT_ID))
    }

    @Test
    fun staleAutomaticRefreshSuccessCannotCommitOverReloggedSameAccountSession() {
        assertTrue(tokenStore.commitVerifiedSession(ACCOUNT_ID, "old-access", "old-refresh"))
        val expectedSession = requireNotNull(tokenStore.sessionIdentityFor(ACCOUNT_ID))
        var sessionUpdateCalls = 0
        val api = boundApi(expectedSession) { access, refresh ->
            sessionUpdateCalls += 1
            tokenStore.updateSessionForIdentity(expectedSession, access, refresh)
        }
        server.dispatcher = object : Dispatcher() {
            override fun dispatch(request: RecordedRequest): MockResponse = when (request.path) {
                "/api/metadata/categories/" -> MockResponse().setResponseCode(401)
                "/api/auth/token/refresh/" -> MockResponse()
                    .setHeader("Content-Type", "application/json")
                    .setBody("""{"access":"stale-candidate","refresh":"stale-rotated"}""")
                "/api/me/" -> {
                    assertTrue(tokenStore.commitVerifiedSession(ACCOUNT_ID, "new-access", "new-refresh"))
                    MockResponse()
                        .setHeader("Content-Type", "application/json")
                        .setBody(
                            """{"id":1,"username":"same","display_name":"Same","roles":[],"capabilities":{}}""",
                        )
                }
                else -> MockResponse().setResponseCode(500)
            }
        }

        assertTrue(kotlinx.coroutines.runBlocking { runCatching { api.categories() }.isFailure })

        assertEquals(3, server.requestCount)
        assertEquals(0, sessionUpdateCalls)
        assertEquals("new-access", tokenStore.accessTokenFor(ACCOUNT_ID))
        assertEquals("new-refresh", tokenStore.refreshTokenFor(ACCOUNT_ID))
        assertNotEquals(expectedSession, tokenStore.sessionIdentityFor(ACCOUNT_ID))
    }

    private fun boundApi(
        expectedSession: AccountSessionIdentity,
        sessionUpdater: (String, String?) -> Boolean = { access, refresh ->
            tokenStore.updateSessionForIdentity(expectedSession, access, refresh)
        },
    ) = MedtrackNetwork.create(
        baseUrl = server.url("/").toString(),
        accessTokenProvider = { tokenStore.accessTokenFor(expectedSession) },
        refreshTokenProvider = { tokenStore.refreshTokenFor(expectedSession) },
        expectedAccountIdProvider = {
            ACCOUNT_ID.takeIf { tokenStore.accountId() == ACCOUNT_ID }
        },
        sessionIncarnationProvider = {
            tokenStore.sessionIdentityFor(ACCOUNT_ID)?.incarnation
        },
        sessionUpdater = sessionUpdater,
    )

    private companion object {
        const val ACCOUNT_ID = "1"
    }
}
