package com.naveenhospital.medtrack.core.network.api

import kotlinx.coroutines.runBlocking
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Assert.assertFalse
import org.junit.Before
import org.junit.Test

class MedtrackNetworkTest {
    private lateinit var server: MockWebServer

    @Before
    fun setUp() {
        server = MockWebServer()
        server.start()
    }

    @After
    fun tearDown() {
        server.shutdown()
    }

    @Test
    fun expiredAccessTokenRefreshesAndRetriesOriginalRequest() = runBlocking {
        var accessToken = "old-access"
        var refreshToken = "refresh-token"
        val updatedSessions = mutableListOf<Pair<String, String?>>()
        val api = MedtrackNetwork.create(
            baseUrl = server.url("/").toString(),
            accessTokenProvider = { accessToken },
            refreshTokenProvider = { refreshToken },
            expectedAccountIdProvider = { "1" },
            sessionUpdater = { access, refresh ->
                accessToken = access
                refreshToken = refresh.orEmpty()
                updatedSessions += access to refresh
                true
            },
        )
        server.enqueue(MockResponse().setResponseCode(401))
        server.enqueue(
            MockResponse()
                .setHeader("Content-Type", "application/json")
                .setBody("""{"access":"new-access","refresh":"new-refresh"}"""),
        )
        server.enqueue(
            MockResponse()
                .setHeader("Content-Type", "application/json")
                .setBody("""{"id":1,"username":"admin","display_name":"Admin","roles":[],"capabilities":{}}"""),
        )
        server.enqueue(
            MockResponse()
                .setHeader("Content-Type", "application/json")
                .setBody("""{"categories":[]}"""),
        )

        val response = api.categories()

        assertTrue(response.categories.isEmpty())
        assertEquals(listOf("new-access" to "new-refresh"), updatedSessions)

        val original = server.takeRequest()
        assertEquals("/api/metadata/categories/", original.path)
        assertEquals("Bearer old-access", original.getHeader("Authorization"))

        val refresh = server.takeRequest()
        assertEquals("/api/auth/token/refresh/", refresh.path)
        assertEquals("""{"refresh":"refresh-token"}""", refresh.body.readUtf8())

        val retry = server.takeRequest()
        assertEquals("/api/me/", retry.path)
        assertEquals("Bearer new-access", retry.getHeader("Authorization"))

        val originalRetry = server.takeRequest()
        assertEquals("/api/metadata/categories/", originalRetry.path)
        assertEquals("Bearer new-access", originalRetry.getHeader("Authorization"))
    }

    @Test
    fun refreshEndpoint401IsNotRetriedByAuthenticator() = runBlocking {
        val api = MedtrackNetwork.create(
            baseUrl = server.url("/").toString(),
            accessTokenProvider = { "expired-access" },
            refreshTokenProvider = { "refresh-token" },
            sessionUpdater = { _, _ -> error("Session should not update") },
        )
        server.enqueue(MockResponse().setResponseCode(401))

        val failure = runCatching {
            api.refresh(com.naveenhospital.medtrack.core.network.model.RefreshTokenRequestDto("refresh-token"))
        }.exceptionOrNull()

        assertNotNull(failure)
        assertEquals(1, server.requestCount)
        val refresh = server.takeRequest()
        assertEquals("/api/auth/token/refresh/", refresh.path)
    }

    @Test
    fun automaticRefreshDoesNotRetryWhenVerifiedIdentityMismatchesExpectedAccount() = runBlocking {
        var committed = false
        val api = MedtrackNetwork.create(
            baseUrl = server.url("/").toString(),
            accessTokenProvider = { "old-access" },
            refreshTokenProvider = { "refresh-token" },
            expectedAccountIdProvider = { "1" },
            sessionUpdater = { _, _ -> committed = true; true },
        )
        server.enqueue(MockResponse().setResponseCode(401))
        server.enqueue(
            MockResponse()
                .setHeader("Content-Type", "application/json")
                .setBody("""{"access":"candidate","refresh":"rotated"}"""),
        )
        server.enqueue(
            MockResponse()
                .setHeader("Content-Type", "application/json")
                .setBody("""{"id":2,"username":"other","display_name":"Other","roles":[],"capabilities":{}}"""),
        )

        assertTrue(runCatching { api.categories() }.isFailure)
        assertFalse(committed)
        assertEquals(3, server.requestCount)
    }

    @Test
    fun automaticRefreshDoesNotRetryWhenAccountBoundCommitFails() = runBlocking {
        var commitCalls = 0
        val api = MedtrackNetwork.create(
            baseUrl = server.url("/").toString(),
            accessTokenProvider = { "old-access" },
            refreshTokenProvider = { "refresh-token" },
            expectedAccountIdProvider = { "1" },
            sessionUpdater = { _, _ -> commitCalls += 1; false },
        )
        server.enqueue(MockResponse().setResponseCode(401))
        server.enqueue(
            MockResponse()
                .setHeader("Content-Type", "application/json")
                .setBody("""{"access":"candidate","refresh":"rotated"}"""),
        )
        server.enqueue(
            MockResponse()
                .setHeader("Content-Type", "application/json")
                .setBody("""{"id":1,"username":"admin","display_name":"Admin","roles":[],"capabilities":{}}"""),
        )

        assertTrue(runCatching { api.categories() }.isFailure)
        assertEquals(1, commitCalls)
        assertEquals(3, server.requestCount)
    }
}
