package com.naveenhospital.medtrack.core.network.api

import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.async
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
    fun concurrentClinicalAndStaff401UseOneRotatingRefresh() = runBlocking {
        val access = java.util.concurrent.atomic.AtomicReference("expired")
        val refresh = java.util.concurrent.atomic.AtomicReference("original-refresh")
        val expiredRequests = java.util.concurrent.CountDownLatch(2)
        val refreshCount = java.util.concurrent.atomic.AtomicInteger()
        val verified = java.util.concurrent.atomic.AtomicInteger()
        server.dispatcher = object : okhttp3.mockwebserver.Dispatcher() {
            override fun dispatch(request: okhttp3.mockwebserver.RecordedRequest): MockResponse {
                fun json(body: String) = MockResponse().setHeader("Content-Type", "application/json").setBody(body)
                if (request.path == "/api/auth/token/refresh/") {
                    if (refreshCount.incrementAndGet() != 1) return MockResponse().setResponseCode(401)
                    assertEquals("original-refresh", MedtrackNetwork.contractMoshi()
                        .adapter(com.naveenhospital.medtrack.core.network.model.RefreshTokenRequestDto::class.java)
                        .fromJson(request.body.readUtf8())!!.refresh)
                    return json(sessionBody("1", "renewed", "rotated"))
                }
                if (request.getHeader("Authorization") == "Bearer expired") {
                    expiredRequests.countDown()
                    check(expiredRequests.await(5, java.util.concurrent.TimeUnit.SECONDS))
                    return MockResponse().setResponseCode(401)
                }
                return when (request.requestUrl!!.encodedPath) {
                    "/api/me/" -> json("""{"id":1,"username":"synthetic","display_name":"Synthetic","roles":[],"capabilities":{"staff_operations":false},"data_scope":{"case_data_scope":"ALL","call_queue":true,"intake_patient_lookup":true}}""")
                    "/api/metadata/categories/" -> json("""{"categories":[]}""")
                    "/api/staff/announcements/" -> json("""{"count":0,"results":[]}""")
                    else -> MockResponse().setResponseCode(404)
                }
            }
        }
        val api = MedtrackNetwork.create(
            server.url("/").toString(), accessTokenProvider = access::get,
            refreshTokenProvider = refresh::get, expectedAccountIdProvider = { "1" },
            sessionIncarnationProvider = { "session" },
            sessionUpdater = { newAccess, newRefresh -> access.set(newAccess); refresh.set(newRefresh); true },
            onProfileVerified = { profile ->
                assertFalse(profile.capabilities["staff_operations"] ?: true)
                verified.incrementAndGet()
            },
        )
        val staff: StaffOperationsApi = api
        val clinicalRequest = async { api.categories() }
        val staffRequest = async { staff.staffAnnouncements() }
        assertTrue(clinicalRequest.await().categories.isEmpty())
        assertTrue(staffRequest.await().results.isEmpty())
        assertEquals(1, refreshCount.get())
        assertEquals(1, verified.get())
        assertEquals(jwt("1", "rotated"), refresh.get())
        assertEquals(6, server.requestCount)
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
            sessionIncarnationProvider = { "session-a" },
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
                .setBody(sessionBody("1", "new-access", "new-refresh")),
        )
        server.enqueue(
            MockResponse()
                .setHeader("Content-Type", "application/json")
                .setBody("""{"id":1,"username":"admin","display_name":"Admin","roles":[],"capabilities":{},"data_scope":{"case_data_scope":"ALL","call_queue":true,"intake_patient_lookup":true}}"""),
        )
        server.enqueue(
            MockResponse()
                .setHeader("Content-Type", "application/json")
                .setBody("""{"categories":[]}"""),
        )

        val response = api.categories()

        assertTrue(response.categories.isEmpty())
        assertEquals(
            listOf(jwt("1", "new-access") to jwt("1", "new-refresh")),
            updatedSessions,
        )

        val original = server.takeRequest()
        assertEquals("/api/metadata/categories/", original.path)
        assertEquals("Bearer old-access", original.getHeader("Authorization"))

        val refresh = server.takeRequest()
        assertEquals("/api/auth/token/refresh/", refresh.path)
        assertEquals("""{"refresh":"refresh-token"}""", refresh.body.readUtf8())

        val retry = server.takeRequest()
        assertEquals("/api/me/", retry.path)
        assertEquals("Bearer ${jwt("1", "new-access")}", retry.getHeader("Authorization"))

        val originalRetry = server.takeRequest()
        assertEquals("/api/metadata/categories/", originalRetry.path)
        assertEquals("Bearer ${jwt("1", "new-access")}", originalRetry.getHeader("Authorization"))
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
            sessionIncarnationProvider = { "session-a" },
            sessionUpdater = { _, _ -> committed = true; true },
        )
        server.enqueue(MockResponse().setResponseCode(401))
        server.enqueue(
            MockResponse()
                .setHeader("Content-Type", "application/json")
                .setBody(sessionBody("1", "candidate", "rotated")),
        )
        server.enqueue(
            MockResponse()
                .setHeader("Content-Type", "application/json")
                .setBody("""{"id":2,"username":"other","display_name":"Other","roles":[],"capabilities":{},"data_scope":{"case_data_scope":"ASSIGNED","call_queue":false,"intake_patient_lookup":false}}"""),
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
            sessionIncarnationProvider = { "session-a" },
            sessionUpdater = { _, _ -> commitCalls += 1; false },
        )
        server.enqueue(MockResponse().setResponseCode(401))
        server.enqueue(
            MockResponse()
                .setHeader("Content-Type", "application/json")
                .setBody(sessionBody("1", "candidate", "rotated")),
        )
        server.enqueue(
            MockResponse()
                .setHeader("Content-Type", "application/json")
                .setBody("""{"id":1,"username":"admin","display_name":"Admin","roles":[],"capabilities":{},"data_scope":{"case_data_scope":"ALL","call_queue":true,"intake_patient_lookup":true}}"""),
        )

        assertTrue(runCatching { api.categories() }.isFailure)
        assertEquals(1, commitCalls)
        assertEquals(3, server.requestCount)
    }
}

private fun sessionBody(accountId: String, accessMarker: String, refreshMarker: String): String =
    """{"access":"${jwt(accountId, accessMarker)}","refresh":"${jwt(accountId, refreshMarker)}"}"""

private fun jwt(accountId: String, marker: String): String {
    val payload = """{"user_id":$accountId,"marker":"$marker"}"""
    val encoded = java.util.Base64.getUrlEncoder().withoutPadding()
        .encodeToString(payload.toByteArray(Charsets.UTF_8))
    return "header.$encoded.signature"
}
