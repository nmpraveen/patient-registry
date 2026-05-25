package com.naveenhospital.medtrack.core.network.api

import kotlinx.coroutines.runBlocking
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
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
            sessionUpdater = { access, refresh ->
                accessToken = access
                refreshToken = refresh.orEmpty()
                updatedSessions += access to refresh
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
        assertEquals("/api/metadata/categories/", retry.path)
        assertEquals("Bearer new-access", retry.getHeader("Authorization"))
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
}
