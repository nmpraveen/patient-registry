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
import com.naveenhospital.medtrack.core.network.model.LoginResponseDto
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
import java.util.UUID
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
    private lateinit var mobilePrefs: SharedPreferences
    private lateinit var tokenStore: TokenStore

    @Before
    fun setUp() {
        val context = ApplicationProvider.getApplicationContext<Context>()
        prefs = context.getSharedPreferences("test_medtrack_auth_repository", Context.MODE_PRIVATE)
        mobilePrefs = context.getSharedPreferences("test_medtrack_mobile_auth", Context.MODE_PRIVATE)
        prefs.edit().clear().commit()
        mobilePrefs.edit().clear().commit()
        tokenStore = TokenStore(prefs)
    }

    @After
    fun tearDown() {
        prefs.edit().clear().commit()
        mobilePrefs.edit().clear().commit()
    }

    @Test
    fun loginSavesJwtSessionAndReturnsCurrentUser() = runTest {
        val api = FakeAuthApi()
        val repository = AuthRepository(api = api, tokenStore = tokenStore)

        val profile = repository.login(username = "admin", password = "pass")

        assertEquals("admin", api.lastLoginRequest?.username)
        assertEquals("pass", api.lastLoginRequest?.password)
        assertEquals(jwt("1", "access"), tokenStore.accessToken)
        assertEquals(jwt("1", "refresh"), tokenStore.refreshToken())
        assertEquals("1", tokenStore.accountId())
        assertEquals("admin", profile.username)
    }

    @Test
    fun targetedFirstLoginStoresOneTimeSecretAndApprovedRetryBindsJwtToDevice() = runTest {
        val deviceId = UUID.randomUUID().toString()
        val credentialStore = MobileDeviceCredentialStore(mobilePrefs, "Ward Android")
        val pendingApi = FakeAuthApi(
            loginResponse = Response.success(
                202,
                LoginResponseDto(
                    deviceApprovalRequired = true,
                    status = "PENDING",
                    deviceId = deviceId,
                    deviceSecret = "one-time-secret",
                ),
            ),
        )
        val pendingRepository = AuthRepository(
            anonymousApi = pendingApi,
            verificationApiForAccessToken = { pendingApi },
            apiForAccount = { pendingApi },
            tokenStore = tokenStore,
            mobileDeviceCredentials = credentialStore,
        )

        val pendingFailure = runCatching { pendingRepository.login("admin", "pass") }.exceptionOrNull()

        assertTrue(pendingFailure is MobileDeviceApprovalPendingException)
        assertNull(tokenStore.accountId())
        assertNull(pendingApi.lastLoginRequest?.deviceId)
        assertNull(pendingApi.lastLoginRequest?.deviceSecret)
        assertEquals("Ward Android", pendingApi.lastLoginRequest?.deviceLabel)
        assertEquals(
            MobileDeviceCredential(deviceId, "one-time-secret"),
            credentialStore.credentialFor("admin"),
        )

        val approvedApi = FakeAuthApi(
            loginResponse = Response.success(
                LoginResponseDto(
                    access = jwt("1", "approved-access", deviceId),
                    refresh = jwt("1", "approved-refresh", deviceId),
                ),
            ),
        )
        val approvedRepository = AuthRepository(
            anonymousApi = approvedApi,
            verificationApiForAccessToken = { approvedApi },
            apiForAccount = { approvedApi },
            tokenStore = tokenStore,
            mobileDeviceCredentials = credentialStore,
        )

        val profile = approvedRepository.login("admin", "pass")

        assertEquals("admin", profile.username)
        assertEquals(deviceId, approvedApi.lastLoginRequest?.deviceId)
        assertEquals("one-time-secret", approvedApi.lastLoginRequest?.deviceSecret)
        assertEquals(deviceId, tokenStore.sessionIdentity()?.mobileDeviceId)
    }

    @Test
    fun pendingRevokedAndMalformedMobileResponsesNeverCommitSession() = runTest {
        val deviceId = UUID.randomUUID().toString()
        val credentialStore = MobileDeviceCredentialStore(mobilePrefs, "Ward Android")

        val malformedPending = FakeAuthApi(
            loginResponse = Response.success(
                202,
                LoginResponseDto(
                    deviceApprovalRequired = true,
                    status = "PENDING",
                    deviceId = deviceId,
                ),
            ),
        )
        val malformedRepository = AuthRepository(
            anonymousApi = malformedPending,
            verificationApiForAccessToken = { malformedPending },
            apiForAccount = { malformedPending },
            tokenStore = tokenStore,
            mobileDeviceCredentials = credentialStore,
        )
        assertTrue(runCatching { malformedRepository.login("admin", "pass") }.isFailure)
        assertNull(tokenStore.accountId())
        assertNull(credentialStore.credentialFor("admin"))

        assertTrue(credentialStore.save("admin", MobileDeviceCredential(deviceId, "stored-secret")))
        val revokedApi = FakeAuthApi(loginResponse = errorLoginResponse(403))
        val revokedRepository = AuthRepository(
            anonymousApi = revokedApi,
            verificationApiForAccessToken = { revokedApi },
            apiForAccount = { revokedApi },
            tokenStore = tokenStore,
            mobileDeviceCredentials = credentialStore,
        )
        assertTrue(runCatching { revokedRepository.login("admin", "pass") }.isFailure)
        assertNull(tokenStore.accountId())
        assertNull(credentialStore.credentialFor("admin"))

        assertTrue(credentialStore.save("admin", MobileDeviceCredential(deviceId, "stored-secret")))
        val missingClaimApi = FakeAuthApi(
            loginResponse = Response.success(
                LoginResponseDto(
                    access = jwt("1", "missing-claim-access"),
                    refresh = jwt("1", "missing-claim-refresh"),
                ),
            ),
        )
        val missingClaimRepository = AuthRepository(
            anonymousApi = missingClaimApi,
            verificationApiForAccessToken = { missingClaimApi },
            apiForAccount = { missingClaimApi },
            tokenStore = tokenStore,
            mobileDeviceCredentials = credentialStore,
        )
        assertTrue(runCatching { missingClaimRepository.login("admin", "pass") }.isFailure)
        assertNull(tokenStore.accountId())
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
            refreshSession = AuthSessionDto(
                access = jwt("2", "account-two-access"),
                refresh = jwt("2", "account-two-refresh"),
            ),
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
    fun restoreSessionFailsClosedWhenRotatedRefreshIsMissing() = runTest {
        assertTrue(tokenStore.commitVerifiedSession("1", access = "old-access", refresh = "stored-refresh"))
        val api = FakeAuthApi(refreshSession = AuthSessionDto(access = jwt("1", "new-access"), refresh = null))
        val repository = AuthRepository(api = api, tokenStore = tokenStore)

        val restored = repository.restoreSession()

        assertTrue(restored is SessionRestoreResult.NoSession)
        assertEquals("stored-refresh", api.lastRefreshRequest?.refresh)
        assertNull(tokenStore.accessToken)
        assertNull(tokenStore.refreshToken())
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
                onSessionCleared = { clearedAccountId = it?.accountId },
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
    private val loginResponse: Response<LoginResponseDto> = Response.success(
        LoginResponseDto(access = jwt("1", "access"), refresh = jwt("1", "refresh")),
    ),
    private val refreshSession: AuthSessionDto = AuthSessionDto(
        access = jwt("1", "refreshed-access"),
        refresh = jwt("1", "rotated-refresh"),
    ),
    private val refreshError: Throwable? = null,
    private val meError: Throwable? = null,
    private val profile: UserProfileDto = userProfile(),
) : MedtrackApi {
    override suspend fun relatedCases(caseId: String, cursor: String?): com.naveenhospital.medtrack.core.network.model.RelatedCasePageDto = error("Unused")

    override suspend fun upcoming(startDate: String?, cursor: String?, categories: List<String>?, subcategories: List<String>?, assignedTo: String?, scopeContext: String?): com.naveenhospital.medtrack.core.network.model.UpcomingPageDto = error("Unused")
    override suspend fun searchUpcoming(request: com.naveenhospital.medtrack.core.network.model.UpcomingSearchRequestDto): com.naveenhospital.medtrack.core.network.model.UpcomingPageDto = error("Unused")
    override suspend fun caseTimeline(caseId: String, filter: String, cursor: String?): com.naveenhospital.medtrack.core.network.model.CaseTimelinePageDto = error("Unused")

    var lastLoginRequest: LoginRequestDto? = null
        private set
    var lastRefreshRequest: RefreshTokenRequestDto? = null
        private set
    var lastLogoutRequest: RefreshTokenRequestDto? = null
        private set

    override suspend fun login(request: LoginRequestDto): Response<LoginResponseDto> {
        lastLoginRequest = request
        return loginResponse
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
        page: Int?,
    ): CaseListResponseDto = unused()

    override suspend fun searchCases(
        request: com.naveenhospital.medtrack.core.network.model.CaseSearchRequestDto,
    ): com.naveenhospital.medtrack.core.network.model.CaseSearchResponseDto = unused()

    override suspend fun caseDetail(caseId: String): CaseDetailDto = unused()

    override suspend fun createCase(request: com.naveenhospital.medtrack.core.network.model.CreateCaseRequestDto): com.naveenhospital.medtrack.core.network.model.CaseCreateResponseDto = unused()

    override suspend fun searchPatients(request: com.naveenhospital.medtrack.core.network.model.PatientSearchRequestDto): com.naveenhospital.medtrack.core.network.model.PatientSearchResponseDto = unused()

    override suspend fun caseFormMetadata(): com.naveenhospital.medtrack.core.network.model.CaseFormMetadataDto = unused()
    override suspend fun taskFormMetadata(): com.naveenhospital.medtrack.core.network.model.TaskFormMetadataDto = unused()
    override suspend fun caseEditForm(caseId: String): com.naveenhospital.medtrack.core.network.model.CaseEditFormDto = unused()
    override suspend fun ancAction(caseId: String, request: Map<String, Any>): com.naveenhospital.medtrack.core.network.model.CaseUpdateResponseDto = unused()

    override suspend fun updateCase(caseId: String, request: com.naveenhospital.medtrack.core.network.model.UpdateCaseRequestDto): com.naveenhospital.medtrack.core.network.model.CaseUpdateResponseDto = unused()
    override suspend fun createTask(caseId: String, request: com.naveenhospital.medtrack.core.network.model.CreateTaskRequestDto): TaskWriteResponseDto = unused()
    override suspend fun updateTask(taskId: String, request: com.naveenhospital.medtrack.core.network.model.UpdateTaskRequestDto): TaskWriteResponseDto = unused()
    override suspend fun addTaskNote(taskId: String, request: com.naveenhospital.medtrack.core.network.model.TaskNoteRequestDto): TaskWriteResponseDto = unused()
    override suspend fun updateVitals(vitalId: String, request: com.naveenhospital.medtrack.core.network.model.VitalsUpdateRequestDto): VitalsWriteResponseDto = unused()

    override suspend fun completeTask(taskId: String, request: ClientWriteRequestDto): TaskWriteResponseDto = unused()

    override suspend fun logCall(caseId: String, request: LogCallRequestDto): CallWriteResponseDto = unused()

    override suspend fun addVitals(caseId: String, request: VitalsRequestDto): VitalsWriteResponseDto = unused()

    override suspend fun vitalsThresholds(): VitalsThresholdsDto = unused()

    override suspend fun notifications(type: String?, unreadOnly: Boolean?, cursor: String?, pageSize: Int?): NotificationsResponseDto = unused()

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
        dataScope = com.naveenhospital.medtrack.core.network.model.DataScopeDto(
            caseDataScope = "ALL",
            callQueue = true,
            intakePatientLookup = true,
        ),
    )

private fun httpError(status: Int): HttpException =
    HttpException(
        errorLoginResponse<Any>(status),
    )

private fun <T> errorLoginResponse(status: Int): Response<T> =
    Response.error(
        status,
        "error".toResponseBody("text/plain".toMediaType()),
    )

private fun jwt(
    accountId: String,
    marker: String,
    mobileDeviceId: String? = null,
): String {
    val mobileClaim = mobileDeviceId?.let { ",\"mobile_device_id\":\"$it\"" }.orEmpty()
    val payload = """{"user_id":$accountId,"marker":"$marker"$mobileClaim}"""
    val encoded = java.util.Base64.getUrlEncoder().withoutPadding()
        .encodeToString(payload.toByteArray(Charsets.UTF_8))
    return "header.$encoded.signature"
}
