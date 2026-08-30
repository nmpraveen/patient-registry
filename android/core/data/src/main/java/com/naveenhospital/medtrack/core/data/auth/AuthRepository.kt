package com.naveenhospital.medtrack.core.data.auth

import com.naveenhospital.medtrack.core.network.api.MedtrackApi
import com.naveenhospital.medtrack.core.network.model.AuthSessionDto
import com.naveenhospital.medtrack.core.network.model.LoginRequestDto
import com.naveenhospital.medtrack.core.network.model.RefreshTokenRequestDto
import com.naveenhospital.medtrack.core.network.model.UserProfileDto
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock

/**
 * Commits a session only after a candidate token succeeds at /me and yields a stable
 * server account ID. Candidate credentials never enter the shared authenticated client.
 */
class AuthRepository(
    private val anonymousApi: MedtrackApi,
    private val verificationApiForAccessToken: (String) -> MedtrackApi,
    private val apiForAccount: (String) -> MedtrackApi,
    private val tokenStore: TokenStore,
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
        val session = anonymousApi.login(LoginRequestDto(username = username, password = password))
        verifyAndCommit(session = session, expectedAccountId = null)
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
                verifyAndCommit(session = session, expectedAccountId = expectedAccountId),
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
    ): UserProfileDto {
        val access = session.access.takeIf { it.isNotBlank() }
            ?: throw DefinitiveAccountIdentityException("Authentication returned no access token.")
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
        val previousSession = tokenStore.sessionIdentity()
        onBeforeAccountCommit(previousSession, verifiedAccountId)
        var committedSession: AccountSessionIdentity? = null
        return runCatching {
            AccountSessionTransitions.serialized {
                if (!tokenStore.commitVerifiedSession(verifiedAccountId, access, session.refresh)) {
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
}
