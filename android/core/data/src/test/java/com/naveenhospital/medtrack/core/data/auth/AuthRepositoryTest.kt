package com.naveenhospital.medtrack.core.data.auth

import android.content.Context
import android.content.SharedPreferences
import androidx.test.core.app.ApplicationProvider
import com.naveenhospital.medtrack.core.network.api.MedtrackApi
import com.naveenhospital.medtrack.core.network.model.ApiMessageDto
import com.naveenhospital.medtrack.core.network.model.AuthSessionDto
import com.naveenhospital.medtrack.core.network.model.CallWriteResponseDto
import com.naveenhospital.medtrack.core.network.model.CaseDetailDto
import com.naveenhospital.medtrack.core.network.model.CaseListResponseDto
import com.naveenhospital.medtrack.core.network.model.CategoriesResponseDto
import com.naveenhospital.medtrack.core.network.model.ClientWriteRequestDto
import com.naveenhospital.medtrack.core.network.model.LogCallRequestDto
import com.naveenhospital.medtrack.core.network.model.LoginRequestDto
import com.naveenhospital.medtrack.core.network.model.NotificationsResponseDto
import com.naveenhospital.medtrack.core.network.model.RefreshTokenRequestDto
import com.naveenhospital.medtrack.core.network.model.RegisterPushTokenRequestDto
import com.naveenhospital.medtrack.core.network.model.TaskWriteResponseDto
import com.naveenhospital.medtrack.core.network.model.UserProfileDto
import com.naveenhospital.medtrack.core.network.model.VitalsRequestDto
import com.naveenhospital.medtrack.core.network.model.VitalsThresholdsDto
import com.naveenhospital.medtrack.core.network.model.VitalsWriteResponseDto
import java.io.IOException
import java.net.SocketTimeoutException
import kotlinx.coroutines.test.runTest
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.ResponseBody.Companion.toResponseBody
import retrofit2.HttpException
import retrofit2.Response

@RunWith(RobolectricTestRunner::class)
class AuthRepositoryTest {
    private lateinit var prefs: SharedPreferences
    private lateinit var tokenStore: TokenStore

    @Before
    fun setUp() {
        val context = ApplicationProvider.getApplicationContext<Context>()
        prefs = context.getSharedPreferences("test_medtrack_auth_repository", Context.MODE_PRIVATE)
        prefs.edit().clear().commit()
        tokenStore = TokenStore(prefs)
    }

    @After
    fun tearDown() {
        prefs.edit().clear().commit()
    }

    @Test
    fun loginSavesJwtSessionAndReturnsCurrentUser() = runTest {
        val api = FakeAuthApi()
        val repository = AuthRepository(api = api, tokenStore = tokenStore)

        val profile = repository.login(username = "admin", password = "pass")

        assertEquals("admin", api.lastLoginRequest?.username)
        assertEquals("pass", api.lastLoginRequest?.password)
        assertEquals("access-token", tokenStore.accessToken)
        assertEquals("refresh-token", tokenStore.refreshToken())
        assertEquals("1", tokenStore.accountId())
        assertEquals("admin", profile.username)
    }

    @Test
    fun currentUserReturnsProfileFromMeEndpoint() = runTest {
        val api = FakeAuthApi()
        val repository = AuthRepository(api = api, tokenStore = tokenStore)
        assertTrue(tokenStore.commitVerifiedSession("1", access = "access-token", refresh = "refresh-token"))

        val profile = repository.currentUser()

        assertEquals("Admin", profile.displayName)
        assertEquals(listOf("Admin"), profile.roles)
    }

    @Test
    fun restoreSessionRejectsDifferentAccountBeforeCommitOrNavigationCallback() = runTest {
        assertTrue(tokenStore.commitVerifiedSession("1", access = "old-access", refresh = "stored-refresh"))
        val api = FakeAuthApi(
            refreshSession = AuthSessionDto(access = "account-two-access", refresh = "account-two-refresh"),
            profile = userProfile(id = 2, username = "other"),
        )
        var committedAccountId: String? = null
        val repository = AuthRepository(
            anonymousApi = api,
            verificationApiForAccessToken = { api },
            apiForAccount = { api },
            tokenStore = tokenStore,
            onAccountCommitted = { committedAccountId = it },
        )

        val restored = repository.restoreSession()

        assertTrue(restored is SessionRestoreResult.NoSession)
        assertNull(committedAccountId)
        assertNull(tokenStore.accountId())
        assertNull(tokenStore.accessToken)
        assertNull(tokenStore.refreshToken())
    }

    @Test
    fun restoreSessionRefreshesAccessAndPreservesRefreshWhenNoRotatedRefreshIsReturned() = runTest {
        assertTrue(tokenStore.commitVerifiedSession("1", access = "old-access", refresh = "stored-refresh"))
        val api = FakeAuthApi(refreshSession = AuthSessionDto(access = "new-access", refresh = null))
        val repository = AuthRepository(api = api, tokenStore = tokenStore)

        val restored = repository.restoreSession()

        assertEquals("admin", (restored as SessionRestoreResult.Verified).profile.username)
        assertEquals("stored-refresh", api.lastRefreshRequest?.refresh)
        assertEquals("new-access", tokenStore.accessToken)
        assertEquals("stored-refresh", tokenStore.refreshToken())
    }

    @Test
    fun restoreSessionRetainsTrustedStateWhenRefreshHasIoFailure() = runTest {
        assertTrue(tokenStore.commitVerifiedSession("1", access = "old-access", refresh = "stored-refresh"))
        val api = FakeAuthApi(refreshError = IOException("offline"))
        var cleared = false
        val repository = AuthRepository(
            anonymousApi = api,
            verificationApiForAccessToken = { api },
            apiForAccount = { api },
            tokenStore = tokenStore,
            onSessionCleared = { cleared = true },
        )

        val restored = repository.restoreSession()

        assertTrue(restored is SessionRestoreResult.Retryable)
        assertFalse(cleared)
        assertEquals("1", tokenStore.accountId())
        assertEquals("old-access", tokenStore.accessToken)
        assertEquals("stored-refresh", tokenStore.refreshToken())
    }

    @Test
    fun restoreSessionRetainsTrustedStateOnTimeoutAndServerFailure() = runTest {
        listOf(
            SocketTimeoutException("timeout"),
            httpError(503),
        ).forEach { failure ->
            tokenStore.clear()
            assertTrue(tokenStore.commitVerifiedSession("1", access = "old-access", refresh = "stored-refresh"))
            var cleared = false
            val api = FakeAuthApi(refreshError = failure)
            val repository = AuthRepository(
                anonymousApi = api,
                verificationApiForAccessToken = { api },
                apiForAccount = { api },
                tokenStore = tokenStore,
                onSessionCleared = { cleared = true },
            )

            assertTrue(repository.restoreSession() is SessionRestoreResult.Retryable)
            assertFalse(cleared)
            assertEquals("1", tokenStore.accountId())
            assertEquals("stored-refresh", tokenStore.refreshToken())
        }
    }

    @Test
    fun restoreSessionPurges401And403() = runTest {
        listOf(401, 403).forEach { status ->
            tokenStore.clear()
            assertTrue(tokenStore.commitVerifiedSession("1", access = "old-access", refresh = "stored-refresh"))
            var clearedAccountId: String? = null
            val api = FakeAuthApi(refreshError = httpError(status))
            val repository = AuthRepository(
                anonymousApi = api,
                verificationApiForAccessToken = { api },
                apiForAccount = { api },
                tokenStore = tokenStore,
                onSessionCleared = { clearedAccountId = it },
            )

            assertTrue(repository.restoreSession() is SessionRestoreResult.NoSession)
            assertEquals("1", clearedAccountId)
            assertNull(tokenStore.accountId())
            assertNull(tokenStore.refreshToken())
        }
    }

    @Test
    fun currentUserRetainsSessionForIoAndServerFailureButPurgesUnauthorized() = runTest {
        listOf(IOException("offline"), httpError(500)).forEach { failure ->
            tokenStore.clear()
            assertTrue(tokenStore.commitVerifiedSession("1", access = "access", refresh = "refresh"))
            val api = FakeAuthApi(meError = failure)
            val repository = AuthRepository(api = api, tokenStore = tokenStore)

            assertTrue(runCatching { repository.currentUser() }.isFailure)
            assertEquals("1", tokenStore.accountId())
            assertEquals("refresh", tokenStore.refreshToken())
        }

        tokenStore.clear()
        assertTrue(tokenStore.commitVerifiedSession("1", access = "access", refresh = "refresh"))
        val unauthorized = AuthRepository(api = FakeAuthApi(meError = httpError(401)), tokenStore = tokenStore)
        assertTrue(runCatching { unauthorized.currentUser() }.isFailure)
        assertNull(tokenStore.accountId())
    }

    @Test
    fun logoutBlacklistsStoredRefreshAndClearsTokens() = runTest {
        assertTrue(tokenStore.commitVerifiedSession("1", access = "access-token", refresh = "refresh-token"))
        val api = FakeAuthApi()
        val repository = AuthRepository(api = api, tokenStore = tokenStore)

        repository.logout()

        assertEquals("refresh-token", api.lastLogoutRequest?.refresh)
        assertNull(api.lastLogoutRequest?.deviceToken)
        assertNull(tokenStore.accessToken)
        assertNull(tokenStore.refreshToken())
    }

    @Test
    fun logoutIncludesDeviceTokenWhenAvailable() = runTest {
        assertTrue(tokenStore.commitVerifiedSession("1", access = "access-token", refresh = "refresh-token"))
        val api = FakeAuthApi()
        val repository = AuthRepository(api = api, tokenStore = tokenStore)

        repository.logout(deviceToken = "fcm-token")

        assertEquals("refresh-token", api.lastLogoutRequest?.refresh)
        assertEquals("fcm-token", api.lastLogoutRequest?.deviceToken)
        assertNull(tokenStore.accessToken)
        assertNull(tokenStore.refreshToken())
    }
}

private class FakeAuthApi(
    private val loginSession: AuthSessionDto = AuthSessionDto(access = "access-token", refresh = "refresh-token"),
    private val refreshSession: AuthSessionDto = AuthSessionDto(access = "refreshed-access", refresh = "rotated-refresh"),
    private val refreshError: Throwable? = null,
    private val meError: Throwable? = null,
    private val profile: UserProfileDto = userProfile(),
) : MedtrackApi {
    var lastLoginRequest: LoginRequestDto? = null
        private set
    var lastRefreshRequest: RefreshTokenRequestDto? = null
        private set
    var lastLogoutRequest: RefreshTokenRequestDto? = null
        private set

    override suspend fun login(request: LoginRequestDto): AuthSessionDto {
        lastLoginRequest = request
        return loginSession
    }

    override suspend fun refresh(request: RefreshTokenRequestDto): AuthSessionDto {
        lastRefreshRequest = request
        refreshError?.let { throw it }
        return refreshSession
    }

    override suspend fun logout(request: RefreshTokenRequestDto): ApiMessageDto {
        lastLogoutRequest = request
        return ApiMessageDto(message = "Logged out.")
    }

    override suspend fun me(): UserProfileDto {
        meError?.let { throw it }
        return profile
    }

    override suspend fun listCases(
        bucket: String?,
        assignedTo: String?,
        scopeContext: String?,
        categories: List<String>?,
        subcategories: List<String>?,
        query: String?,
        page: Int?,
    ): CaseListResponseDto = unused()

    override suspend fun caseDetail(caseId: String): CaseDetailDto = unused()

    override suspend fun createCase(request: com.naveenhospital.medtrack.core.network.model.CreateCaseRequestDto): com.naveenhospital.medtrack.core.network.model.CaseCreateResponseDto = unused()

    override suspend fun searchPatients(query: String?, page: Int?): com.naveenhospital.medtrack.core.network.model.PatientSearchResponseDto = unused()

    override suspend fun caseFormMetadata(): com.naveenhospital.medtrack.core.network.model.CaseFormMetadataDto = unused()
    override suspend fun taskFormMetadata(): com.naveenhospital.medtrack.core.network.model.TaskFormMetadataDto = unused()
    override suspend fun caseEditForm(caseId: String): com.naveenhospital.medtrack.core.network.model.CaseEditFormDto = unused()
    override suspend fun updateCase(caseId: String, request: com.naveenhospital.medtrack.core.network.model.CreateCaseRequestDto): com.naveenhospital.medtrack.core.network.model.CaseCreateResponseDto = unused()
    override suspend fun createTask(caseId: String, request: com.naveenhospital.medtrack.core.network.model.CreateTaskRequestDto): TaskWriteResponseDto = unused()
    override suspend fun updateTask(taskId: String, request: com.naveenhospital.medtrack.core.network.model.UpdateTaskRequestDto): TaskWriteResponseDto = unused()
    override suspend fun addTaskNote(taskId: String, request: com.naveenhospital.medtrack.core.network.model.TaskNoteRequestDto): TaskWriteResponseDto = unused()
    override suspend fun updateVitals(vitalId: String, request: com.naveenhospital.medtrack.core.network.model.VitalsUpdateRequestDto): VitalsWriteResponseDto = unused()

    override suspend fun completeTask(taskId: String, request: ClientWriteRequestDto): TaskWriteResponseDto = unused()

    override suspend fun logCall(caseId: String, request: LogCallRequestDto): CallWriteResponseDto = unused()

    override suspend fun addVitals(caseId: String, request: VitalsRequestDto): VitalsWriteResponseDto = unused()

    override suspend fun vitalsThresholds(): VitalsThresholdsDto = unused()

    override suspend fun notifications(type: String?, unreadOnly: Boolean?, page: Int?): NotificationsResponseDto = unused()

    override suspend fun markNotificationRead(notificationId: String): ApiMessageDto = unused()

    override suspend fun registerPushToken(request: RegisterPushTokenRequestDto): ApiMessageDto = unused()

    override suspend fun categories(): CategoriesResponseDto = unused()

    private fun unused(): Nothing = error("Not used by this test")
}

private fun userProfile(
    id: Long = 1,
    username: String = "admin",
): UserProfileDto =
    UserProfileDto(
        id = id,
        username = username,
        displayName = if (id == 1L) "Admin" else "Other",
        roles = listOf("Admin"),
        capabilities = emptyMap(),
    )

private fun httpError(status: Int): HttpException =
    HttpException(
        Response.error<Any>(
            status,
            "error".toResponseBody("text/plain".toMediaType()),
        ),
    )
