package com.naveenhospital.medtrack.core.data.auth

import com.naveenhospital.medtrack.core.network.api.MedtrackApi
import com.naveenhospital.medtrack.core.network.model.AuthSessionDto
import com.naveenhospital.medtrack.core.network.model.LoginRequestDto
import com.naveenhospital.medtrack.core.network.model.LoginResponseDto
import com.naveenhospital.medtrack.core.network.model.RefreshTokenRequestDto
import com.naveenhospital.medtrack.core.network.model.UserProfileDto
import com.naveenhospital.medtrack.core.network.model.requireSessionBinding
import java.util.UUID
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import retrofit2.HttpException

class MobileDeviceApprovalPendingException(
    val deviceId: String,
) : IllegalStateException("This Android device is waiting for administrator approval. Try again after it is approved.")

/**
 * Commits a session only after a candidate token succeeds at /me and yields a stable
 * server account ID. Candidate credentials never enter the shared authenticated client.
 */
class AuthRepository(
    private val anonymousApi: MedtrackApi,
    private val verificationApiForAccessToken: (String) -> MedtrackApi,
    private val apiForAccount: (String) -> MedtrackApi,
    private val tokenStore: TokenStore,
    private val mobileDeviceCredentials: MobileDeviceCredentialStorage =
        UnavailableMobileDeviceCredentialStorage,
    private val onBeforeAccountCommit: suspend (
        previousSession: AccountSessionIdentity?,
        newAccountId: String,
    ) -> Unit = { _, _ -> },
    private val onAccountCommitted: suspend (accountId: String) -> Unit = {},
    private val onSessionCleared: suspend (session: AccountSessionIdentity?) -> Unit = {},
) {
    constructor(api: MedtrackApi, tokenStore: TokenStore) : this(
        anonymousApi = api,
        verificationApiForAccessToken = { api },
        apiForAccount = { api },
        tokenStore = tokenStore,
    )

    private val transitionMutex = Mutex()

    @Volatile
    private var verifiedProfile: UserProfileDto? = null

    fun hasRefreshToken(): Boolean = tokenStore.hasRefreshToken()

    fun accountId(): String? = tokenStore.accountId()

    suspend fun login(username: String, password: String): UserProfileDto = transitionMutex.withLock {
        val normalizedUsername = username.trim()
        val mobileCredential = mobileDeviceCredentials.credentialFor(normalizedUsername)
        val response = anonymousApi.login(
            LoginRequestDto(
                username = normalizedUsername,
                password = password,
                deviceId = mobileCredential?.deviceId,
                deviceSecret = mobileCredential?.deviceSecret,
                deviceLabel = mobileDeviceCredentials.deviceLabel,
            ),
        )
        if (response.code() == 202) {
            handlePendingMobileApproval(normalizedUsername, mobileCredential, response.body())
        }
        if (!response.isSuccessful) {
            if (response.code() == 403 && mobileCredential != null) {
                check(mobileDeviceCredentials.clear(normalizedUsername)) {
                    "Unable to clear the rejected mobile-device credential."
                }
            }
            throw HttpException(response)
        }
        if (response.code() != 200) {
            throw DefinitiveAccountIdentityException("Authentication returned an unsupported success status.")
        }
        val body = response.body()
            ?: throw DefinitiveAccountIdentityException("Authentication returned no response body.")
        if (
            body.deviceApprovalRequired == true ||
            body.status != null ||
            body.deviceId != null ||
            body.deviceSecret != null
        ) {
            throw DefinitiveAccountIdentityException("Authentication returned a malformed approval response.")
        }
        val session = AuthSessionDto(
            access = body.access?.takeIf { it.isNotBlank() }
                ?: throw DefinitiveAccountIdentityException("Authentication returned no access token."),
            refresh = body.refresh?.takeIf { it.isNotBlank() }
                ?: throw DefinitiveAccountIdentityException("Authentication returned no refresh token."),
        )
        verifyAndCommit(
            session = session,
            expectedAccountId = null,
            expectedMobileDeviceId = mobileCredential?.deviceId,
        )
    }

    suspend fun currentUser(): UserProfileDto {
        val sessionIdentity = tokenStore.sessionIdentity()
            ?: error("No verified MEDTRACK account is active.")
        val accountId = sessionIdentity.accountId
        verifiedProfile?.takeIf { it.id.toString() == accountId }?.let { return it }
        return transitionMutex.withLock {
            verifiedProfile?.takeIf { it.id.toString() == accountId } ?: run {
                val profile = runCatching { apiForAccount(accountId).me() }
                    .getOrElse { failure ->
                        if (
                            failure.isDefinitiveAccountAuthFailure() &&
                            tokenStore.isCurrent(sessionIdentity)
                        ) {
                            clearSessionLocked(sessionIdentity)
                        }
                        throw failure
                    }
                if (!tokenStore.isCurrent(sessionIdentity)) {
                    throw DefinitiveAccountIdentityException(
                        "Authenticated session changed while verifying account identity.",
                    )
                }
                if (profile.id.toString() != accountId) {
                    clearSessionLocked(sessionIdentity)
                    throw DefinitiveAccountIdentityException(
                        "Authenticated account identity changed unexpectedly.",
                    )
                }
                verifiedProfile = profile
                profile
            }
        }
    }

    suspend fun restoreSession(): SessionRestoreResult = transitionMutex.withLock {
        val expectedSession = tokenStore.sessionIdentity() ?: return@withLock SessionRestoreResult.NoSession
        val expectedAccountId = expectedSession.accountId
        verifiedProfile?.takeIf {
            it.id.toString() == expectedAccountId && tokenStore.accessTokenFor(expectedSession) != null
        }?.let { return@withLock SessionRestoreResult.Verified(it) }
        val refresh = tokenStore.refreshTokenFor(expectedSession) ?: run {
            clearSessionLocked(expectedSession)
            return@withLock SessionRestoreResult.NoSession
        }
        try {
            val session = anonymousApi.refresh(RefreshTokenRequestDto(refresh = refresh))
            SessionRestoreResult.Verified(
                verifyAndCommit(
                    session = session,
                    expectedAccountId = expectedAccountId,
                    expectedMobileDeviceId = expectedSession.mobileDeviceId,
                ),
            )
        } catch (failure: Throwable) {
            if (failure.isDefinitiveAccountAuthFailure()) {
                if (tokenStore.isCurrent(expectedSession)) {
                    clearSessionLocked(expectedSession)
                }
                SessionRestoreResult.NoSession
            } else {
                SessionRestoreResult.Retryable(failure)
            }
        }
    }

    suspend fun logout(deviceToken: String? = null) = transitionMutex.withLock {
        val sessionIdentity = tokenStore.sessionIdentity()
        val accountId = sessionIdentity?.accountId
        val refresh = sessionIdentity?.let(tokenStore::refreshTokenFor)
        if (accountId != null && !refresh.isNullOrBlank()) {
            runCatching {
                apiForAccount(accountId).logout(
                    RefreshTokenRequestDto(
                        refresh = refresh,
                        deviceToken = deviceToken?.takeIf { it.isNotBlank() },
                    ),
                )
            }
        }
        clearSessionLocked(sessionIdentity)
    }

    suspend fun abandonSession() = transitionMutex.withLock {
        clearSessionLocked(tokenStore.sessionIdentity())
    }

    private suspend fun verifyAndCommit(
        session: AuthSessionDto,
        expectedAccountId: String?,
        expectedMobileDeviceId: String? = null,
    ): UserProfileDto {
        val access = session.access.takeIf { it.isNotBlank() }
            ?: throw DefinitiveAccountIdentityException("Authentication returned no access token.")
        val binding = try {
            session.requireSessionBinding(expectedAccountId, expectedMobileDeviceId)
        } catch (failure: IllegalArgumentException) {
            throw DefinitiveAccountIdentityException("Authentication returned malformed account credentials.", failure)
        }
        val profile = verificationApiForAccessToken(access).me()
        val verifiedAccountId = profile.id.toString().takeIf { it.isNotBlank() }
            ?: throw DefinitiveAccountIdentityException(
                "The authenticated account has no stable identity.",
            )
        if (expectedAccountId != null && verifiedAccountId != expectedAccountId) {
            throw DefinitiveAccountIdentityException(
                "Refreshed credentials do not belong to the stored account.",
            )
        }
        if (binding.accountId != verifiedAccountId) {
            throw DefinitiveAccountIdentityException(
                "Authentication token and verified profile belong to different accounts.",
            )
        }
        val previousSession = tokenStore.sessionIdentity()
        onBeforeAccountCommit(previousSession, verifiedAccountId)
        var committedSession: AccountSessionIdentity? = null
        return runCatching {
            AccountSessionTransitions.serialized {
                if (
                    !tokenStore.commitVerifiedSession(
                        verifiedAccountId,
                        access,
                        session.refresh,
                        binding.mobileDeviceId,
                    )
                ) {
                    error("Unable to persist the verified MEDTRACK session.")
                }
                committedSession = tokenStore.sessionIdentityFor(verifiedAccountId)
                    ?: error("Unable to bind the verified MEDTRACK session identity.")
                onAccountCommitted(verifiedAccountId)
            }
            verifiedProfile = profile
            profile
        }.getOrElse { failure ->
            clearSessionLocked(committedSession ?: previousSession)
            throw failure
        }
    }

    private fun handlePendingMobileApproval(
        username: String,
        existingCredential: MobileDeviceCredential?,
        body: LoginResponseDto?,
    ): Nothing {
        val pending = body
            ?: throw DefinitiveAccountIdentityException("Device approval returned no response body.")
        if (
            pending.deviceApprovalRequired != true ||
            pending.status != STATUS_PENDING ||
            !pending.access.isNullOrBlank() ||
            !pending.refresh.isNullOrBlank()
        ) {
            throw DefinitiveAccountIdentityException("Device approval returned a malformed pending response.")
        }
        val deviceId = try {
            UUID.fromString(pending.deviceId).toString()
        } catch (failure: RuntimeException) {
            throw DefinitiveAccountIdentityException("Device approval returned a malformed device identifier.", failure)
        }
        if (existingCredential != null) {
            if (deviceId != existingCredential.deviceId || !pending.deviceSecret.isNullOrBlank()) {
                throw DefinitiveAccountIdentityException("Pending approval does not match this Android credential.")
            }
        } else {
            val secret = pending.deviceSecret?.takeIf { it.isNotBlank() }
                ?: throw DefinitiveAccountIdentityException("Device approval returned no one-time secret.")
            if (!mobileDeviceCredentials.save(username, MobileDeviceCredential(deviceId, secret))) {
                throw DefinitiveAccountIdentityException("Unable to store the mobile-device credential securely.")
            }
        }
        throw MobileDeviceApprovalPendingException(deviceId)
    }

    private suspend fun clearSessionLocked(sessionIdentity: AccountSessionIdentity?) {
        verifiedProfile = null
        try {
            onSessionCleared(sessionIdentity)
        } finally {
            if (sessionIdentity == null) {
                tokenStore.clear()
            } else {
                tokenStore.clearForIdentity(sessionIdentity)
            }
        }
    }

    private companion object {
        const val STATUS_PENDING = "PENDING"
    }
}
