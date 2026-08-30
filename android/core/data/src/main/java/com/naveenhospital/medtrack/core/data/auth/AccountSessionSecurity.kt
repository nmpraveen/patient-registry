package com.naveenhospital.medtrack.core.data.auth

import android.content.Context
import com.naveenhospital.medtrack.core.data.local.MedtrackDatabase
import com.naveenhospital.medtrack.core.data.sync.MedtrackSyncWorker
import com.naveenhospital.medtrack.core.network.model.requireSessionBinding
import com.squareup.moshi.JsonDataException
import java.io.IOException
import java.util.concurrent.CopyOnWriteArraySet
import retrofit2.HttpException
import kotlinx.coroutines.NonCancellable
import kotlinx.coroutines.withContext
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock

sealed interface SessionRestoreResult {
    data class Verified(val profile: com.naveenhospital.medtrack.core.network.model.UserProfileDto) : SessionRestoreResult
    data class Retryable(val cause: Throwable) : SessionRestoreResult
    data object NoSession : SessionRestoreResult
}

internal class DefinitiveAccountIdentityException(
    message: String,
    cause: Throwable? = null,
) : IllegalStateException(message, cause)

fun Throwable.isDefinitiveAccountAuthFailure(): Boolean =
    when (this) {
        is DefinitiveAccountIdentityException -> true
        is JsonDataException -> true
        is HttpException -> code() in setOf(400, 401, 403)
        is IOException -> false
        else -> false
    }

sealed interface AccountSessionRefreshResult {
    data object Verified : AccountSessionRefreshResult
    data object StaleAccount : AccountSessionRefreshResult
    data class Retryable(val cause: Throwable) : AccountSessionRefreshResult
    data class DefinitiveFailure(val cause: Throwable) : AccountSessionRefreshResult
}

suspend fun refreshAndVerifyAccountSession(
    expectedSession: AccountSessionIdentity,
    tokenStore: TokenStore,
    refreshSession: suspend (String) -> com.naveenhospital.medtrack.core.network.model.AuthSessionDto,
    verifyProfile: suspend (String) -> com.naveenhospital.medtrack.core.network.model.UserProfileDto,
): AccountSessionRefreshResult {
    if (!tokenStore.isCurrent(expectedSession)) return AccountSessionRefreshResult.StaleAccount
    val refreshToken = tokenStore.refreshTokenFor(expectedSession)
        ?: return AccountSessionRefreshResult.DefinitiveFailure(
            DefinitiveAccountIdentityException("The verified account has no refresh credential."),
        )
    val session = try {
        refreshSession(refreshToken)
    } catch (failure: Throwable) {
        if (!tokenStore.isCurrent(expectedSession)) return AccountSessionRefreshResult.StaleAccount
        return if (failure.isDefinitiveAccountAuthFailure()) {
            AccountSessionRefreshResult.DefinitiveFailure(failure)
        } else {
            AccountSessionRefreshResult.Retryable(failure)
        }
    }
    if (!tokenStore.isCurrent(expectedSession)) return AccountSessionRefreshResult.StaleAccount
    try {
        session.requireSessionBinding(expectedSession.accountId, expectedSession.mobileDeviceId)
    } catch (failure: IllegalArgumentException) {
        return AccountSessionRefreshResult.DefinitiveFailure(
            DefinitiveAccountIdentityException("Authentication returned malformed account credentials.", failure),
        )
    }
    val access = session.access.takeIf { it.isNotBlank() }
        ?: return AccountSessionRefreshResult.DefinitiveFailure(
            DefinitiveAccountIdentityException("Authentication returned no access token."),
        )
    val profile = try {
        verifyProfile(access)
    } catch (failure: Throwable) {
        if (!tokenStore.isCurrent(expectedSession)) return AccountSessionRefreshResult.StaleAccount
        return if (failure.isDefinitiveAccountAuthFailure()) {
            AccountSessionRefreshResult.DefinitiveFailure(failure)
        } else {
            AccountSessionRefreshResult.Retryable(failure)
        }
    }
    if (!tokenStore.isCurrent(expectedSession)) return AccountSessionRefreshResult.StaleAccount
    if (profile.id.toString() != expectedSession.accountId) {
        return AccountSessionRefreshResult.DefinitiveFailure(
            DefinitiveAccountIdentityException(
                "Refreshed credentials do not belong to the stored account.",
            ),
        )
    }
    return if (tokenStore.updateSessionForIdentity(expectedSession, access, session.refresh)) {
        AccountSessionRefreshResult.Verified
    } else {
        AccountSessionRefreshResult.StaleAccount
    }
}

internal object AccountSessionTransitions {
    private val mutex = Mutex()

    suspend fun <T> serialized(block: suspend () -> T): T = mutex.withLock { block() }
}

/**
 * Process-local visibility notification paired with the cross-process Room generation
 * tombstone. Deleting owner rows also empties active Room flows in another process.
 */
object AccountVisibilityInvalidations {
    private val listeners = CopyOnWriteArraySet<(String) -> Unit>()

    fun register(listener: (String) -> Unit) {
        listeners += listener
    }

    fun unregister(listener: (String) -> Unit) {
        listeners -= listener
    }

    internal fun deactivate(ownerAccountId: String) {
        listeners.forEach { listener -> listener(ownerAccountId) }
    }
}

/**
 * The sole destructive account invalidation path used by UI auth, WorkManager, and push.
 * It is idempotent. Room's lifecycle generation makes revocation and purge visible across
 * processes before any later account-bound commit is allowed.
 */
class AccountSessionInvalidator(
    private val database: MedtrackDatabase,
    private val tokenStore: TokenStore,
    private val lockStore: LockStore,
    private val cancelAccountWork: suspend (String) -> Unit,
) {
    constructor(context: Context) : this(
        database = MedtrackDatabase.build(context.applicationContext),
        tokenStore = TokenStore(context.applicationContext),
        lockStore = LockStore(context.applicationContext),
        cancelAccountWork = { accountId ->
            MedtrackSyncWorker.cancelForAccount(context.applicationContext, accountId)
        },
    )

    constructor(
        context: Context,
        database: MedtrackDatabase,
        tokenStore: TokenStore,
        lockStore: LockStore,
    ) : this(
        database = database,
        tokenStore = tokenStore,
        lockStore = lockStore,
        cancelAccountWork = { accountId ->
            MedtrackSyncWorker.cancelForAccount(context.applicationContext, accountId)
        },
    )

    suspend fun invalidate(
        expectedSession: AccountSessionIdentity?,
        expectedGeneration: Long? = null,
    ): Boolean = AccountSessionTransitions.serialized {
        invalidateLocked(expectedSession, expectedGeneration, requireCurrent = expectedSession != null)
    }

    suspend fun invalidateIfCurrent(
        expectedSession: AccountSessionIdentity,
        expectedGeneration: Long? = null,
    ): Boolean = AccountSessionTransitions.serialized {
        invalidateLocked(expectedSession, expectedGeneration, requireCurrent = true)
    }

    private suspend fun invalidateLocked(
        expectedSession: AccountSessionIdentity?,
        expectedGeneration: Long?,
        requireCurrent: Boolean,
    ): Boolean = withContext(NonCancellable) {
        var firstFailure: Throwable? = null
        fun recordFailure(failure: Throwable) {
            if (firstFailure == null) {
                firstFailure = failure
            } else if (firstFailure !== failure) {
                firstFailure?.addSuppressed(failure)
            }
        }
        suspend fun attempt(block: suspend () -> Unit) {
            try {
                block()
            } catch (failure: Throwable) {
                recordFailure(failure)
            }
        }

        if (expectedSession == null) {
            attempt { tokenStore.clear() }
            attempt { lockStore.deactivate() }
            firstFailure?.let { throw it }
            return@withContext true
        }
        if (requireCurrent && !tokenStore.isCurrent(expectedSession)) {
            return@withContext false
        }

        val accountId = expectedSession.accountId
        attempt { cancelAccountWork(accountId) }
        val purged = try {
            database.invalidateAndClearAccountData(accountId, expectedGeneration)
        } catch (failure: Throwable) {
            recordFailure(failure)
            false
        }
        if (purged) {
            attempt { AccountVisibilityInvalidations.deactivate(accountId) }
            // Catch a one-time enqueue that raced the first cancellation while an
            // already-started account commit was draining before the purge transaction.
            attempt { cancelAccountWork(accountId) }
            attempt { lockStore.clearAccount(accountId) }
            attempt { tokenStore.clearForIdentity(expectedSession) }
        } else {
            // A newer activation won the Room compare-and-set. Its visibility, rows,
            // lock, work, and credentials belong to a different session incarnation.
            return@withContext false
        }
        firstFailure?.let { throw it }
        true
    }
}
