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
    private val onBeforeAccountCommit: suspend (previousAccountId: String?, newAccountId: String) -> Unit = { _, _ -> },
    private val onAccountCommitted: suspend (accountId: String) -> Unit = {},
    private val onSessionCleared: suspend (accountId: String?) -> Unit = {},
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
        val accountId = tokenStore.accountId() ?: error("No verified MEDTRACK account is active.")
        verifiedProfile?.takeIf { it.id.toString() == accountId }?.let { return it }
        return transitionMutex.withLock {
            verifiedProfile?.takeIf { it.id.toString() == accountId } ?: run {
                val profile = runCatching { apiForAccount(accountId).me() }
                    .getOrElse { failure ->
                        if (failure.isDefinitiveAccountAuthFailure()) {
                            clearSessionLocked(accountId)
                        }
                        throw failure
                    }
                if (profile.id.toString() != accountId) {
                    clearSessionLocked(accountId)
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
        val expectedAccountId = tokenStore.accountId() ?: return@withLock SessionRestoreResult.NoSession
        verifiedProfile?.takeIf {
            it.id.toString() == expectedAccountId && tokenStore.accessTokenFor(expectedAccountId) != null
        }?.let { return@withLock SessionRestoreResult.Verified(it) }
        val refresh = tokenStore.refreshTokenFor(expectedAccountId) ?: run {
            clearSessionLocked(expectedAccountId)
            return@withLock SessionRestoreResult.NoSession
        }
        try {
            val session = anonymousApi.refresh(RefreshTokenRequestDto(refresh = refresh))
            SessionRestoreResult.Verified(
                verifyAndCommit(session = session, expectedAccountId = expectedAccountId),
            )
        } catch (failure: Throwable) {
            if (failure.isDefinitiveAccountAuthFailure()) {
                clearSessionLocked(expectedAccountId)
                SessionRestoreResult.NoSession
            } else {
                SessionRestoreResult.Retryable(failure)
            }
        }
    }

    suspend fun logout(deviceToken: String? = null) = transitionMutex.withLock {
        val accountId = tokenStore.accountId()
        val refresh = accountId?.let(tokenStore::refreshTokenFor)
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
        clearSessionLocked(accountId)
    }

    suspend fun abandonSession() = transitionMutex.withLock {
        clearSessionLocked(tokenStore.accountId())
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
        val previousAccountId = tokenStore.accountId()
        onBeforeAccountCommit(previousAccountId, verifiedAccountId)
        if (!tokenStore.commitVerifiedSession(verifiedAccountId, access, session.refresh)) {
            clearSessionLocked(previousAccountId)
            error("Unable to persist the verified MEDTRACK session.")
        }
        return runCatching {
            onAccountCommitted(verifiedAccountId)
            verifiedProfile = profile
            profile
        }.getOrElse { failure ->
            clearSessionLocked(verifiedAccountId)
            throw failure
        }
    }

    private suspend fun clearSessionLocked(accountId: String?) {
        verifiedProfile = null
        try {
            onSessionCleared(accountId)
        } finally {
            if (accountId == null) tokenStore.clear() else tokenStore.clearForAccount(accountId)
        }
    }
}
